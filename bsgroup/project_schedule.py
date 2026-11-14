"""Project Plan -> existing Tech Task Scheduler -> private evening Teams summary.

Opt-in per site. No browser webhook or manual group route is used by this job.
An outbound attempt is reserved and committed before HTTP; uncertain attempts
are deliberately not retried automatically (Power Automate may have accepted it).
"""
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
from html import escape
from urllib.parse import urlparse

import frappe
from frappe.utils import getdate, strip_html

SETTINGS = 'BS Project Schedule Settings'
DELIVERY = 'BS Project Schedule Delivery'
METHOD = 'bsgroup.project_schedule.run'
TERMINAL = {'Completed', 'Closed', 'Cancelled', 'Template'}


def identity(*parts):
    return sha256('|'.join(map(str, parts)).encode()).hexdigest()[:32]


def profile():
    from bsgroup.hr_email import site_profile
    p = site_profile()
    if not p:
        return None
    from bsgroup import oman_attendance_email, uae_attendance_email
    return oman_attendance_email if p['region'] == 'Oman' else uae_attendance_email


def eligible_task(task, day):
    return (task.status not in TERMINAL and not task.get('is_template')
            and bool(task.exp_start_date) and getdate(task.exp_start_date) <= day)


def calendar_plan(employee, day):
    # Reuse HR's assigned/default shift, employment dates, holiday calendar,
    # calendar coverage and approved leave checks. WFH/on-duty still need tasks.
    result = profile().plan(employee, day)
    if result['reason'] == 'Approved on-duty / work-from-home arrangement':
        result['reason'] = ''
    return result


def task_rows(user, day, company):
    assignments = frappe.get_all('ToDo', filters={'reference_type': 'Task',
        'allocated_to': user, 'status': 'Open'}, fields=['reference_name'])
    result = []
    for name in sorted({a.reference_name for a in assignments if a.reference_name}):
        task = frappe.get_doc('Task', name)
        if not task.project or not eligible_task(task, day):
            continue
        project = frappe.get_doc('Project', task.project)
        if project.company != company or project.status in TERMINAL:
            continue
        if not (frappe.has_permission('Project', 'read', doc=project, user=user)
                and frappe.has_permission('Task', 'read', doc=task, user=user)):
            continue
        result.append(dict(date=str(day), category='Project', category_doctype='Project',
            category_name=project.name, project=project.name, task=task.name,
            resource=user, status='Overdue' if task.exp_end_date and getdate(task.exp_end_date) < day else 'Scheduled',
            activity_details=strip_html(task.description or task.subject or ''),
            task_title=task.subject or task.name, project_title=project.project_name,
            due_date=str(task.exp_end_date or '')))
    return result


def candidates(day, settings, sent_day=None):
    result = []
    for employee in profile().employees():
        plan = calendar_plan(employee, day)
        if sent_day and not settings.send_on_holiday_eve and not plan['reason']:
            today = calendar_plan(employee, sent_day)
            if today['reason']:
                plan['reason'] = 'No evening send: ' + today['reason']
        rows = task_rows(employee.user_id, day, employee.company) if not plan['reason'] else []
        result.append(dict(employee=employee.name, employee_name=employee.employee_name,
            user=employee.user_id, shift=plan['shift'], reason=plan['reason'], rows=rows))
    return result


def sync_schedule(project, user, day, rows):
    """One native scheduler per project/user/day, one row per task. No submit."""
    key = identity(project, user, day)
    existing = frappe.db.get_value('Tech Task Scheduler', {'custom_bs_auto_key': key}, 'name')
    # A manager may already have scheduled a task manually for this date.
    # Reuse that evidence instead of adding a second task/user/date entry.
    manual = set()
    for item in frappe.get_all('Tech Task Scheduler List', filters={
            'project': project, 'resource': user, 'date': day,
            'status': ['not in', ['Cancelled', 'Completed']]}, fields=['task', 'parent']):
        parent = frappe.db.get_value('Tech Task Scheduler', item.parent,
            ['docstatus', 'custom_bs_auto_key'], as_dict=True)
        if parent and parent.docstatus != 2 and not parent.custom_bs_auto_key:
            manual.add(item.task)
    rows = [row for row in rows if row['task'] not in manual]
    if not rows and not existing:
        return None
    doc = frappe.get_doc('Tech Task Scheduler', existing) if existing else frappe.new_doc('Tech Task Scheduler')
    doc.custom_bs_auto_key = key
    doc.custom_bs_auto_date = day
    doc.custom_bs_auto_user = user
    doc.custom_bs_auto_project = project
    fields = ('date', 'category', 'category_doctype', 'category_name', 'project', 'task',
              'resource', 'status', 'activity_details')
    old = {r.task: r for r in doc.get('tech_task_scheduler_list', [])}
    retained = []
    for row in rows:
        item = old.get(row['task'])
        if item is None:
            item = doc.append('tech_task_scheduler_list', {})
        item.update({f: row[f] for f in fields})
        retained.append(item)
    doc.set('tech_task_scheduler_list', retained)
    doc.flags.bs_auto_schedule = True
    doc.save(ignore_permissions=True)
    return doc.name


def message(employee, day, rows, region):
    lines = [f'<p>Hello {escape(employee)},</p>',
        f'<p><b>These are the tasks scheduled for tomorrow ({day:%d %B %Y}) — {region}.</b></p>',
        '<ul>']
    for row in rows:
        lines.append('<li><b>' + escape(row['project_title']) + '</b>: '
            + escape(row['task_title']) + ' (' + escape(row['task']) + ')'
            + (' — due ' + escape(row['due_date']) if row['due_date'] else '')
            + (' — <b>Overdue</b>' if row['status'] == 'Overdue' else '') + '</li>')
    lines.extend(['</ul>', '<p>Please update your daily work and task status in the project’s Project Plan.</p>'])
    return ''.join(lines)


def validate_endpoint(url):
    p = urlparse(url or '')
    host = p.hostname or ''
    if (p.scheme != 'https' or p.username or p.password or p.port not in (None, 443)
            or not host.endswith(('.environment.api.powerplatform.com', '.logic.azure.com'))
            or '/workflows/' not in p.path):
        frappe.throw('Use the HTTPS endpoint of the verified Microsoft individual Teams flow.')


def dispatch(settings, candidate, day, rows, test=False):
    key = identity(('TEST:' if test else '') + frappe.local.site, candidate['user'], day)
    if frappe.db.exists(DELIVERY, key):
        return 'Already reserved'
    body = message(candidate['employee_name'], day, rows, profile().COMPANY.rsplit(' - ', 1)[-1])
    if test:
        body = '<p><b>TEST ONLY — private project schedule delivery and duplicate protection.</b></p>' + body
    if len(body.encode('utf-8')) > 24000:
        frappe.throw('Teams summary exceeds 24 KB; review the flow before sending.')
    url = settings.get_password('individual_webhook')
    validate_endpoint(url)
    log = frappe.get_doc(dict(doctype=DELIVERY, recipient=candidate['user'],
        schedule_date=day, task_count=len(rows), status='Reserved',
        detail='Reserved before HTTP. A reserved or uncertain attempt is never automatically resent.'))
    try:
        log.insert(ignore_permissions=True, set_name=key)
        frappe.db.commit()
    except frappe.DuplicateEntryError:
        frappe.db.rollback()
        return 'Already reserved'
    import requests
    try:
        response = requests.post(url, json={'allocated_to': candidate['user'], 'message': body,
            'idempotency_key': key, 'schedule_date': str(day)}, timeout=(10, 30), allow_redirects=False)
        status = 'Accepted' if 200 <= response.status_code < 300 else 'Failed'
        detail = f'HTTP {response.status_code}. Accepted means flow accepted, not confirmed Teams delivery.'
    except requests.RequestException:
        status, detail = 'Uncertain', 'No reliable HTTP response. Check Power Automate history before any manual resend.'
    frappe.db.set_value(DELIVERY, key, dict(status=status, detail=detail))
    frappe.db.commit()
    return status


def run():
    p = profile()
    if not p:
        return
    settings = frappe.get_single(SETTINGS)
    now = datetime.now(p.TZ)
    if not evening_due(now, settings):
        return
    day = now.date() + timedelta(days=1)
    # Avoid concurrent row refreshes; delivery primary key also protects HTTP
    # if a worker dies or the Redis lease is lost.
    lock = frappe.cache.lock('bs-project-schedule:' + frappe.local.site, timeout=7200, blocking_timeout=0)
    if not lock.acquire(blocking=False):
        return
    try:
        for candidate in candidates(day, settings, sent_day=now.date()):
            key = identity(frappe.local.site, candidate['user'], day)
            if candidate['reason'] or not candidate['rows'] or frappe.db.exists(DELIVERY, key):
                continue
            try:
                grouped = defaultdict(list)
                for row in candidate['rows']:
                    grouped[row['project']].append(row)
                for project, rows in grouped.items():
                    sync_schedule(project, candidate['user'], day, rows)
                dispatch(settings, candidate, day, candidate['rows'])
            except Exception as exc:
                frappe.db.rollback()
                # Never include the HTTP URL, response body or credentials.
                frappe.log_error(title='Automatic project schedule needs review',
                    message=f'Employee {candidate["employee"]}; task date {day}; error type {type(exc).__name__}. Check schedule settings and delivery history.')
    finally:
        lock.release()


def evening_due(now, settings):
    return bool(settings.enabled and settings.private_delivery_verified and now.hour == 18
        and settings.start_date and now.date() >= getdate(settings.start_date))


def guard_generated(doc, method=None):
    old_key = frappe.db.get_value('Tech Task Scheduler', doc.name, 'custom_bs_auto_key') if not doc.is_new() else None
    if (old_key or doc.get('custom_bs_auto_key')) and not doc.flags.bs_auto_schedule:
        frappe.throw('This schedule is generated from the Project Plan. Edit the task in that project instead.')


def project_entries(project):
    frappe.get_doc('Project', project).check_permission('read')
    schedules = frappe.get_all('Tech Task Scheduler',
        filters={'custom_bs_auto_project': project, 'docstatus': ['!=', 2]},
        fields=['name', 'custom_bs_auto_user', 'custom_bs_auto_date'],
        order_by='custom_bs_auto_date desc', limit_page_length=100)
    result = []
    for parent in schedules:
        doc = frappe.get_doc('Tech Task Scheduler', parent.name)
        if parent.custom_bs_auto_user != frappe.session.user and not frappe.has_permission('Tech Task Scheduler', 'read', doc=doc):
            continue
        for row in doc.tech_task_scheduler_list:
            if row.project != project or not row.task:
                continue
            task = frappe.get_doc('Task', row.task)
            if not frappe.has_permission('Task', 'read', doc=task):
                continue
            result.append(dict(scheduler=doc.name, date=str(row.date), user=row.resource,
                employee=frappe.get_cached_value('User', row.resource, 'full_name') or row.resource,
                task=row.task, title=task.subject, status=row.status, work=row.activity_details))
    return result


def install():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({'Tech Task Scheduler': [
        dict(fieldname='custom_bs_auto_key', label='Automatic Schedule Key', fieldtype='Data', unique=1, read_only=1, hidden=1, no_copy=1),
        dict(fieldname='custom_bs_auto_date', label='Automatic Schedule Date', fieldtype='Date', read_only=1, no_copy=1),
        dict(fieldname='custom_bs_auto_user', label='Scheduled Employee Login', fieldtype='Link', options='User', read_only=1, no_copy=1),
        dict(fieldname='custom_bs_auto_project', label='Scheduled Project', fieldtype='Link', options='Project', read_only=1, no_copy=1),
    ]}, update=True)


@frappe.whitelist()
def preview(day=None):
    frappe.only_for('System Manager')
    if not profile():
        frappe.throw('This feature is available only on the Oman and UAE sites.')
    day = getdate(day) if day else datetime.now(profile().TZ).date() + timedelta(days=1)
    return candidates(day, frappe.get_single(SETTINGS), sent_day=day - timedelta(days=1))


@frappe.whitelist(methods=['POST'])
def selftest():
    """Exercise native inserts twice on a labelled test project, then roll back.

    Never invokes dispatch/HTTP, modifies a Task, or persists a test schedule.
    """
    frappe.only_for('System Manager')
    if not profile():
        frappe.throw('This test is available only on the Oman and UAE sites.')
    project = task = None
    for candidate in frappe.get_all('Project', filters={'project_name':['like','TEST%']},
            fields=['name','project_name'], order_by='creation desc'):
        task = frappe.db.get_value('Task', {'project':candidate.name}, 'name')
        if task:
            project = candidate
            break
    if not project:
        frappe.throw('A labelled TEST project with a linked task is required for this check.')
    day = datetime.now(profile().TZ).date() + timedelta(days=1)
    row = dict(date=str(day),category='Project',category_doctype='Project',category_name=project.name,
        project=project.name,task=task,resource=frappe.session.user,status='Scheduled',activity_details='TEST ONLY — rolled back')
    frappe.db.savepoint('bs_schedule_selftest')
    try:
        first = sync_schedule(project.name, frappe.session.user, day, [row])
        second = sync_schedule(project.name, frappe.session.user, day, [row])
        if not first or first != second:
            frappe.throw('Test fixture already has a manual schedule, or scheduler identity changed.')
        doc = frappe.get_doc('Tech Task Scheduler', second)
        count = sum(r.task == task for r in doc.tech_task_scheduler_list)
        if count != 1:
            frappe.throw('Duplicate task rows detected.')
        return dict(success=True, project=project.name, scheduler=first, task=task,
            rows_after_two_runs=count, persisted=False, teams_messages_sent=0)
    finally:
        frappe.db.rollback(save_point='bs_schedule_selftest')


@frappe.whitelist(methods=['POST'])
def test_delivery():
    """A labelled, sample-only test to Mohan; repeated requests cannot resend.

    Separate reservation namespace never consumes his real daily notification.
    This explicitly sends once, unlike the rollback-only scheduler self-test.
    """
    frappe.only_for('System Manager')
    if frappe.session.user != 'mohan@bitssecureit.com' or not profile():
        frappe.throw('The delivery test must be run by Mohan on Oman or UAE.')
    day = datetime.now(profile().TZ).date() + timedelta(days=1)
    candidate = dict(user=frappe.session.user, employee_name='Mohan')
    rows = [dict(project_title='TEST ONLY — ' + profile().COMPANY, task='TEST-DELIVERY',
        task_title='Verify one private Teams message; no real work assigned',
        due_date=str(day), status='Scheduled')]
    settings = frappe.get_single(SETTINGS)
    first = dispatch(settings, candidate, day, rows, test=True)
    second = dispatch(settings, candidate, day, rows, test=True)
    return dict(first=first, repeated=second, recipient=frappe.session.user,
        delivery=identity('TEST:' + frappe.local.site, frappe.session.user, day))


def configure_hooks(hooks):
    hooks.setdefault('after_migrate', []).append('bsgroup.project_schedule.install')
    hooks.setdefault('scheduler_events', {}).setdefault('cron', {}).setdefault('* * * * *', []).append(METHOD)
    events = hooks.setdefault('doc_events', {}).setdefault('Tech Task Scheduler', {})
    for event in ('validate', 'before_submit', 'before_cancel', 'on_trash'):
        old = events.get(event, [])
        events[event] = ([old] if isinstance(old, str) else list(old)) + ['bsgroup.project_schedule.guard_generated']
