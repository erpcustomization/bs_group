"""Daily project emails, isolated from the existing evening Teams dispatcher."""
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from html import escape
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import getdate, strip_html
from bsgroup.project_schedule import profile, calendar_plan, task_rows, is_on_hold, TERMINAL
from bsgroup.project_support_access import TECHNICAL_ROLES
from bsgroup.hr_email import site_profile

TZ = ZoneInfo('Asia/Dubai')
METHOD = 'bsgroup.project_daily_emails.run'
CRON = '*/5 9-10,17-19 * * *'
SETTINGS = 'BS Project Schedule Settings'
FLAG = 'custom_bs_daily_project_emails'
ANCHOR = 'custom_bs_daily_email_start'
MANI = 'manikandan@bitssecureit.com'
SLOTS = {'tasks': time(9), 'projects': time(10), 'reminder': time(17, 30),
         'status': time(18, 10), 'timesheets': time(19)}
LABELS = {'tasks': "Today's project tasks", 'projects': 'Open project status',
          'reminder': "Please update today's project work", 'status': 'Daily work entry status',
          'timesheets': 'Daily individual timesheet report'}


def due(now, anchor):
    if now.date() < getdate(anchor):
        return []
    return [kind for kind, at in SLOTS.items()
            if datetime.combine(now.date(), at, TZ) <= now
            < datetime.combine(now.date(), at, TZ) + timedelta(minutes=30)]


def key(user, kind, day):
    return 'project-mail-' + sha256(f'{user}|{kind}|{day}'.encode()).hexdigest()[:28]


def recipients(user, kind):
    return ([MANI], [] if user == MANI else [user]) if kind == 'timesheets' else ([user], [])


def roster(day):
    result = []
    for employee in profile().employees():
        user = employee.user_id
        if not user or user in ('Administrator', 'Guest', 'erp@bitssecureit.com'):
            continue
        roles = set(frappe.get_roles(user))
        assigned = frappe.db.exists('ToDo', {'allocated_to': user, 'reference_type': 'Task', 'status': 'Open'})
        if not (roles & TECHNICAL_ROLES or assigned):
            continue
        plan = calendar_plan(employee, day)
        result.append(dict(employee=employee, user=user, name=employee.employee_name,
                           reason=plan['reason'], shift=plan['shift']))
    return result


def permitted(doctype, name, user):
    return bool(name and frappe.has_permission(doctype, 'read', doc=frappe.get_doc(doctype, name), user=user))


def schedule_rows(person, day, active_only=True):
    """Read the dated scheduler evidence; never generate or modify Teams schedules."""
    user = person['user']
    rows, seen = [], set()
    for row in frappe.get_all('Tech Task Scheduler List', filters={'resource': user, 'date': day},
            fields=['parent', 'project', 'task', 'activity_details', 'status'], order_by='creation asc'):
        pair = (row.project, row.task)
        if not row.task or not row.project or pair in seen:
            continue
        parent = frappe.db.get_value('Tech Task Scheduler', row.parent, ['docstatus', 'creation'], as_dict=True)
        # Morning copies the previous evening's schedule, not later manual additions.
        if not parent or parent.docstatus == 2 or (active_only and getdate(parent.creation) >= day):
            continue
        task, project = frappe.get_doc('Task', row.task), frappe.get_doc('Project', row.project)
        if project.company != person['employee'].company or project.get('custom_bs_archived'):
            continue
        if task.project != project.name or not permitted('Project', project.name, user) or not permitted('Task', task.name, user):
            continue
        if active_only and (task.status in TERMINAL or project.status in TERMINAL
                            or is_on_hold(task.status) or is_on_hold(project.status)):
            continue
        if row.status == 'Cancelled':
            continue
        seen.add(pair)
        rows.append(dict(project=project.name, project_title=project.project_name,
            task=task.name, task_title=task.subject, activity_details=strip_html(row.activity_details or task.subject),
            status=task.status, due_date=str(task.exp_end_date or '')))
    return rows


def work_rows(person, day, for_manager=False):
    rows = []
    user = person['user']
    # user/employee defines whose work this is; creation by a manager is not attribution.
    names = frappe.get_all('Timesheet', filters={'docstatus': ['!=', 2],
        'company': person['employee'].company}, or_filters={'user': user, 'employee': person['employee'].name}, pluck='name')
    for name in names:
        sheet = frappe.get_doc('Timesheet', name)
        if sheet.user and sheet.user != user:
            continue
        for line in sheet.time_logs:
            stamp = line.get('custom_bs_work_date') or sheet.get('custom_date') or line.from_time
            if not stamp or getdate(stamp) != day or not line.project:
                continue
            if not permitted('Project', line.project, user):
                continue
            if for_manager and not permitted('Project', line.project, MANI):
                continue
            rows.append(dict(project=line.project, task=line.task or '',
                work=strip_html(line.description or '').strip(), hours=line.hours or 0,
                timesheet=name, line=line.name, entry=line.get('custom_bs_work_entry'),
                state='Submitted' if sheet.docstatus == 1 else 'Draft'))
    # A legacy duplicate must not be counted twice; separate genuine entries stay separate.
    unique = {}
    for row in rows:
        unique.setdefault(row['entry'] or row['line'], row)
    return list(unique.values())


def entry_status(tasks, work):
    recorded = {(r['project'], r['task']) for r in work if r['work']}
    return [dict(r, entry_status='Recorded' if (r['project'], r['task']) in recorded else 'Not recorded') for r in tasks]


def projects(person):
    result = []
    for name in frappe.get_all('Project', filters={'company': person['employee'].company,
            'status': ['not in', sorted(TERMINAL)]}, pluck='name'):
        p = frappe.get_doc('Project', name)
        if p.get('custom_bs_archived') or not permitted('Project', name, person['user']):
            continue
        result.append(dict(project=name, title=p.project_name, status=p.status,
            progress=p.percent_complete or 0, end=str(p.expected_end_date or 'Not set')))
    return result


def table(headings, rows):
    if not rows:
        return '<p>No matching records for this date.</p>'
    cells = lambda values, tag: ''.join(f'<{tag} style="padding:10px;border-bottom:1px solid #dbe5f1;text-align:left">{escape(str(v or "—"))}</{tag}>' for v in values)
    return '<table style="width:100%;border-collapse:collapse"><thead style="background:#edf3fc"><tr>' + cells(headings, 'th') + '</tr></thead><tbody>' + ''.join('<tr>' + cells(row, 'td') + '</tr>' for row in rows) + '</tbody></table>'


def compose(person, day, kind):
    user = person['user']
    to, cc = recipients(user, kind)
    content = ''
    count = 0
    if kind == 'tasks':
        rows = schedule_rows(person, day)
        count = len(rows)
        content = '<p>Your project tasks for today, from the saved previous-evening scheduler. Tasks now on hold, completed or no longer accessible are excluded.</p>'
        content += table(['Project', 'Task', 'Work scheduled', 'Due date'],
            [(r['project_title'], r['task_title'], r['activity_details'], r['due_date']) for r in rows])
    elif kind == 'projects':
        rows = projects(person)
        count = len(rows)
        content = '<p>Current open projects and AMCs you have permission to view.</p>'
        content += table(['Project', 'Status', 'Progress', 'Expected end'],
            [(r['title'], r['status'], f"{r['progress']}%", r['end']) for r in rows])
    elif kind == 'reminder':
        content = "<p>Please record today's work against the relevant task in each project's <b>Project Plan → Enter today's task</b>. Your saved work should appear in that project's Timesheets tab.</p><p>Record the actual work performed and update the task status accurately. If you already entered today's work, please review it for completeness.</p>"
    else:
        work = work_rows(person, day, for_manager=kind == 'timesheets')
        tasks = schedule_rows(person, day, active_only=False)
        tasks += task_rows(user, day, person['employee'].company)
        tasks = list({(r['project'], r['task']): r for r in tasks}.values())
        if kind == 'timesheets':
            tasks = [r for r in tasks if permitted('Project', r['project'], MANI)]
        statuses = entry_status(tasks, work)
        count = len(work)
        content = f'<p>Work-entry review for <b>{escape(person["name"])}</b> on {day:%d %b %Y}. Recorded: {sum(r["entry_status"] == "Recorded" for r in statuses)} scheduled/assigned tasks; not recorded: {sum(r["entry_status"] == "Not recorded" for r in statuses)}.</p>'
        content += table(['Project', 'Task', "Today's work entry"],
            [(r['project_title'], r['task_title'], r['entry_status']) for r in statuses])
        content += '<h3>Saved timesheet entries</h3>' + table(['Project', 'Task', 'Work done', 'Hours recorded', 'Timesheet'],
            [(r['project'], r['task'], r['work'], str(r['hours']), f"{r['timesheet']} ({r['state']})") for r in work])
        content += '<p>A recorded work entry does not mean the task is completed or the timesheet approved. Zero recorded hours are not estimated. Missing work entries are not an attendance or payroll determination.</p>'
    region = site_profile()['region']
    subject = f'[{region}] {LABELS[kind]} — {person["name"]} — {day:%d %b %Y}'
    greeting = f'Dear Mani,<br>Individual report: {escape(person["name"])}' if kind == 'timesheets' else f'Dear {escape(person["name"])},'
    body = '<div style="font-family:Arial,sans-serif;color:#173452;max-width:1000px;margin:auto"><h2 style="background:#143766;color:white;padding:20px;border-radius:10px">' + escape(LABELS[kind]) + f'</h2><p>{greeting}</p>' + content + '<p>Regards,<br><b>BITS Secure IT</b></p></div>'
    return dict(to=to, cc=cc, subject=subject, body=body, record_count=count)


def queue_one(person, day, kind):
    marker = key(person['user'], kind, day)
    if frappe.db.exists('Notification Log', marker):
        return False
    if calendar_plan(person['employee'], day)['reason']:
        return False
    if kind == 'timesheets' and not frappe.db.get_value('User', MANI, 'enabled'):
        frappe.throw('Manikandan has no enabled recipient account.')
    message = compose(person, day, kind)
    frappe.db.savepoint('project_daily_mail')
    try:
        frappe.get_doc(dict(doctype='Notification Log', name=marker, type='Alert',
            for_user=person['user'], from_user='Administrator', subject=message['subject'],
            email_content=message['body'], document_type='Employee', document_name=person['employee'].name)).db_insert()
        queued = frappe.sendmail(recipients=message['to'], cc=message['cc'], subject=message['subject'],
            message=message['body'], expose_recipients='header', delayed=True, now=False,
            message_id=f'<{marker}@bitssecureit.com>', add_unsubscribe_link=False, is_notification=True,
            reference_doctype='Employee', reference_name=person['employee'].name)
        if not queued:
            frappe.throw('No email queue entry was created.')
        frappe.db.commit()
        return True
    except frappe.DuplicateEntryError:
        frappe.db.rollback(save_point='project_daily_mail')
        return False
    except Exception:
        frappe.db.rollback(save_point='project_daily_mail')
        raise


def run():
    if not site_profile() or not frappe.get_meta(SETTINGS).has_field(FLAG) or not frappe.db.get_single_value(SETTINGS, FLAG):
        return 0
    now = datetime.now(TZ)
    anchor = frappe.db.get_single_value(SETTINGS, ANCHOR)
    if not anchor or str(anchor) == '0001-01-01':
        return 0
    kinds = due(now, anchor)
    if not kinds:
        return 0
    sent = 0
    for person in roster(now.date()):
        if person['reason']:
            continue
        for kind in kinds:
            try:
                sent += int(queue_one(person, now.date(), kind))
            except Exception:
                frappe.log_error(title='Daily project email failed', message=frappe.get_traceback())
    return sent


def install():
    if not site_profile():
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({SETTINGS: [dict(fieldname=FLAG, label='Five daily project email schedules', fieldtype='Check', default='0'),
        dict(fieldname=ANCHOR, label='Daily project emails enabled from', fieldtype='Date')]}, update=False)
    from frappe.core.doctype.scheduled_job_type.scheduled_job_type import insert_single_event
    insert_single_event('Cron', METHOD, CRON)


@frappe.whitelist(methods=['POST'])
def enable():
    frappe.only_for('System Manager')
    if not site_profile():
        frappe.throw('Unsupported site.')
    install()
    frappe.db.set_single_value(SETTINGS, FLAG, 1)
    if str(frappe.db.get_single_value(SETTINGS, ANCHOR) or '') in ('', '0001-01-01'):
        frappe.db.set_single_value(SETTINGS, ANCHOR, datetime.now(TZ).date())
    return state()


def state():
    enabled = frappe.db.get_single_value(SETTINGS, FLAG) if frappe.get_meta(SETTINGS).has_field(FLAG) else False
    settings = frappe.get_single(SETTINGS)
    return dict(enabled=bool(enabled), region=site_profile()['region'],
        start=str(settings.get(ANCHOR) or ''), timezone='Asia/Dubai (UTC+4)',
        job=frappe.db.get_value('Scheduled Job Type', {'method': METHOD}, ['stopped', 'cron_format', 'last_execution'], as_dict=True),
        teams={field: settings.get(field) for field in ['enabled', 'private_delivery_verified', 'start_date', 'send_on_holiday_eve', 'oman_group_enabled', 'oman_group_verified', 'uae_group_enabled', 'uae_group_verified']})


@frappe.whitelist(methods=['GET'])
def preview(day=None):
    frappe.only_for('System Manager')
    day = getdate(day or datetime.now(TZ).date())
    people = roster(day)
    reports = []
    for person in people:
        if person['reason']:
            continue
        for kind in SLOTS:
            report = compose(person, day, kind)
            reports.append(dict(user=person['user'], kind=kind, time=str(SLOTS[kind]),
                to=report['to'], cc=report['cc'], records=report['record_count'], body_length=len(report['body']),
                already_queued=bool(frappe.db.exists('Notification Log', key(person['user'], kind, day)))))
    return dict(read_only=True, emails_sent=0, day=str(day), state=state(), reports=reports,
        skipped=[dict(user=p['user'], reason=p['reason']) for p in people if p['reason']])


@frappe.whitelist(methods=['GET'])
def page():
    frappe.only_for('System Manager')
    from frappe.sessions import get_csrf_token
    settings = state()
    html = f'<div style="max-width:1050px;margin:40px auto;font-family:Arial;color:#173452"><h1>{escape(settings["region"])} — Daily project emails</h1><p>Enabled: <b>{settings["enabled"]}</b> · From: {escape(settings["start"])} · UTC+4</p>'
    html += table(['Time', 'Email', 'Recipients'], [(str(at)[:5], LABELS[kind], 'Manikandan; employee in CC (one email per employee)' if kind == 'timesheets' else 'Each eligible employee separately; no CC') for kind, at in SLOTS.items()])
    html += '<p>HR holidays, weekly days off, approved leave and employment dates respected. Project access preserved. No attendance or timesheet records changed. Separate daily email keys prevent repeated scheduling. Existing 18:00 Teams automation unchanged.</p>'
    html += '<p>Scheduler: ' + escape(str(settings['job'])) + '</p><p>Existing Teams controls: ' + escape(str(settings['teams'])) + '</p>'
    html += '<form id="enable"><button style="padding:12px;background:#1646a0;color:white">Enable five daily email schedules</button></form><pre id="result"></pre></div><script>document.getElementById("enable").onsubmit=async function(e){e.preventDefault();const b=this.querySelector("button");b.disabled=true;try{const r=await fetch("/api/method/bsgroup.project_daily_emails.enable",{method:"POST",headers:{"X-Frappe-CSRF-Token":"TOKEN"}});document.getElementById("result").textContent=JSON.stringify(await r.json(),null,2);}finally{b.disabled=false;}};</script>'
    frappe.respond_as_web_page('Daily project emails', html.replace('TOKEN', escape(get_csrf_token(), quote=True)))
