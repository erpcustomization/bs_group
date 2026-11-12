"""Individual weekly attendance summaries, explicitly enabled per regional site.

Read-only attendance analysis; no attendance, payroll or disciplinary decisions.
Each employee/week reservation and dedicated HR email queue commit atomically.
"""
from datetime import date, datetime, time, timedelta
from email.utils import formataddr
from hashlib import sha256
from html import escape
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

import frappe
from frappe.utils import get_datetime, getdate
from bsgroup.hr_email import configured_account

TZ = ZoneInfo('Asia/Dubai')
METHOD = 'bsgroup.weekly_attendance_email.send_summaries'
ENABLED = 'custom_bs_weekly_attendance_email'
HR_CC = 'muskan@bitssecureit.com'
CRON = '2 9 * * 5'
START_DATE = date(2026, 11, 13)
THRESHOLD = 3
EXCLUDED_USERS = {'mohan@bitssecureit.com'}


def site_profile():
    # Older Oman installations have the dedicated HR sender but predate the
    # shared regional helper. Do not replace their working mail configuration.
    identities = {urlparse(frappe.conf.get('host_name') or '').hostname,
                  getattr(frappe.local, 'site', None)}
    if identities & {'erp-om.bitssecureit.com', 'erp-om.k.frappe.cloud'}:
        return dict(region='Oman', email='hr-notifications-om@bitssecureit.com', sender_name='HR Oman')
    if identities & {'erp.bitssecureit.com', 'erp-bitssecureit.u.frappe.cloud'}:
        return dict(region='UAE', email='hr-notifications-ae@bitssecureit.com', sender_name='HR UAE')
    return None


def configure_hooks(hooks):
    cron = hooks.setdefault('scheduler_events', {}).setdefault('cron', {})
    prior = cron.get(CRON, [])
    methods = [prior] if isinstance(prior, str) else list(prior)
    if METHOD not in methods:
        methods.append(METHOD)
    cron[CRON] = methods


def region_module():
    profile = site_profile()
    if not profile:
        frappe.throw('Weekly attendance emails are available only on Oman and UAE sites.')
    if profile['region'] == 'Oman':
        from bsgroup import oman_attendance_email as module
    else:
        from bsgroup import uae_attendance_email as module
    return module


def reporting_period(friday):
    friday = getdate(friday)
    if friday.weekday() != 4:
        raise ValueError('The reporting date must be a Friday.')
    return friday - timedelta(days=7), friday - timedelta(days=1)


def next_run(now):
    day = now.date() + timedelta(days=(4 - now.weekday()) % 7)
    if day == now.date() and now.time().replace(tzinfo=None) >= time(9, 2):
        day += timedelta(days=7)
    return max(START_DATE, day)


def is_due(now):
    return (now.date() >= START_DATE and now.weekday() == 4
            and time(9, 2) <= now.time().replace(tzinfo=None) < time(12))


def weekly_key(employee, friday):
    return 'weekly-attendance-' + sha256(f'{employee}:{friday}'.encode()).hexdigest()[:28]


def local_stamp(value):
    stamp = get_datetime(value)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=ZoneInfo(frappe.utils.get_system_timezone()))
    return stamp.astimezone(TZ)


def day_result(start, end, punches, corrected_in=None, corrected_out=None):
    """Classify reliable evidence; a day with two issues still counts once."""
    ordered = sorted(punches, key=lambda p: p[0])
    first = next((stamp for stamp, kind in ordered if kind == 'IN'), None)
    last_out = next((stamp for stamp, kind in reversed(ordered) if kind == 'OUT'), None)
    active = False
    ambiguous = any(kind not in ('IN', 'OUT') for _, kind in ordered)
    for _, kind in ordered:
        if kind == 'IN':
            active = True
        elif kind == 'OUT':
            active = False
    if corrected_in:
        first = corrected_in
    if corrected_out:
        last_out = corrected_out
        active = False
    if last_out and (not first or last_out < first):
        ambiguous = True
    late = bool(first and first > start and not ambiguous)
    missing = bool(first and (not last_out or active) and not ambiguous)
    remarks = []
    if late:
        remarks.append('Late check-in')
    if missing:
        remarks.append('Missing check-out')
    if ambiguous:
        remarks.append('Incomplete / ambiguous record — HR review needed')
    if not remarks:
        remarks.append('On time' if first else 'No check-in recorded — not counted as late')
    return dict(start=start, end=end, first=first, out=last_out, late=late,
                missing=missing, affected=late or missing, remark='; '.join(remarks))


def read_day(employee, day, now, module):
    scheduled = module.plan(employee, day)
    base = dict(day=day, start=scheduled['start'], end=scheduled['end'], first=None,
                out=None, late=False, missing=False, affected=False,
                excluded=bool(scheduled['reason']), remark=scheduled['reason'])
    if base['excluded']:
        return base
    start, end = scheduled['start'], scheduled['end']
    if end > now:
        base.update(excluded=True, remark='Shift has not finished at the reporting time')
        return base
    # Midpoints between adjacent shifts support early arrivals and overnight
    # check-outs without borrowing a normal following day's check-in.
    margin = max(timedelta(), (timedelta(days=1) - (end - start)) / 2)
    lower, upper = start - margin, end + margin
    site_tz = ZoneInfo(frappe.utils.get_system_timezone())
    db_stamp = lambda x: x.astimezone(site_tz).replace(tzinfo=None)
    logs = frappe.get_all('Employee Checkin', filters=[
        ['employee', '=', employee.name], ['time', '>=', db_stamp(lower)],
        ['time', '<', db_stamp(min(upper, now))], ['skip_auto_attendance', '=', 0]],
        fields=['time', 'log_type', 'shift_start'], order_by='time asc, creation asc, name asc',
        limit_page_length=0)
    punches = [(local_stamp(log.time), log.log_type) for log in logs
               if not log.shift_start or local_stamp(log.shift_start) == start]
    attendance = frappe.get_all('Attendance', filters={'employee': employee.name,
        'attendance_date': day, 'docstatus': 1},
        fields=['name', 'in_time', 'out_time', 'attendance_request', 'status'], limit_page_length=0)
    if len(attendance) > 1:
        base.update(excluded=True, remark='Multiple submitted attendance records — HR review needed')
        return base
    corrected_in = corrected_out = None
    if attendance:
        row = attendance[0]
        if row.status in ('On Leave', 'Half Day', 'Work From Home'):
            base.update(excluded=True, remark='Approved attendance arrangement')
            return base
        if row.attendance_request:
            # An approved correction supersedes raw punches. Without corrected
            # times, do not send a warning based on missing/uncorrected punches.
            if not row.in_time or not row.out_time:
                base.update(excluded=True, remark='Approved attendance correction')
                return base
            corrected_in, corrected_out = local_stamp(row.in_time), local_stamp(row.out_time)
        elif not punches:
            corrected_in = local_stamp(row.in_time) if row.in_time else None
            corrected_out = local_stamp(row.out_time) if row.out_time else None
    base.update(day_result(start, end, punches, corrected_in, corrected_out))
    return base


def recipients(employee):
    user = employee.user_id
    if not user or user in ('Administrator', 'Guest') or not frappe.db.get_value('User', user, 'enabled'):
        return [], 'No enabled employee email'
    if not frappe.db.get_value('User', HR_CC, 'enabled'):
        return [], 'Muskan HR user is not enabled'
    manager_id = frappe.db.get_value('Employee', employee.name, 'reports_to')
    if not manager_id:
        return [], 'Reporting manager is not assigned'
    manager = frappe.db.get_value('Employee', manager_id, ['user_id', 'status'], as_dict=True)
    if (not manager or manager.status != 'Active' or not manager.user_id
            or not frappe.db.get_value('User', manager.user_id, 'enabled')
            or not frappe.utils.validate_email_address(manager.user_id)):
        return [], 'Reporting manager has no enabled email'
    if manager.user_id == user:
        return [], 'Employee is assigned as their own reporting manager'
    return sorted({manager.user_id, HR_CC} - {user}), ''


def report(employee, friday, now=None):
    start, end = reporting_period(friday)
    observed = now or datetime.now(TZ)
    module = region_module()
    excluded = employee.user_id in EXCLUDED_USERS
    rows = [] if excluded else [read_day(employee, start + timedelta(days=i), observed, module) for i in range(7)]
    cc, hold = ([], '') if excluded else recipients(employee)
    count = sum(int(row['affected']) for row in rows)
    return dict(employee=employee.name, name=employee.employee_name, to=employee.user_id,
        cc=cc, hold=hold, excluded=excluded, friday=friday, start=start, end=end, rows=rows, affected=count,
        late=sum(int(r['late']) for r in rows), missing=sum(int(r['missing']) for r in rows),
        qualifies=count >= THRESHOLD, eligible=count >= THRESHOLD and not hold)


def subject(summary):
    return (f'Action Required: Weekly Attendance Summary | '
            f'{summary["start"]:%d %b} – {summary["end"]:%d %b %Y}')


def email_body(summary, profile):
    rows = []
    clock = lambda v: v.strftime('%I:%M %p').lstrip('0') if v else 'Not recorded'
    for row in summary['rows']:
        if row['excluded']:
            continue
        shift = f'{clock(row["start"])} – {clock(row["end"])}'
        if row['end'].date() > row['start'].date():
            shift += ' (ends next day)'
        check_out = clock(row['out'])
        if row['missing'] and row['out']:
            check_out += ' (final check-out missing)'
        cells = [row['day'].strftime('%a, %d %b'), shift, clock(row['first']), check_out, row['remark']]
        rows.append('<tr>' + ''.join('<td style="border:1px solid #ddd;padding:8px">'
                    + escape(str(cell)) + '</td>' for cell in cells) + '</tr>')
    return (f'<p>Dear {escape(summary["name"])},</p>'
        f'<p>Your attendance records for <b>{summary["start"]:%d %B %Y} to '
        f'{summary["end"]:%d %B %Y}</b> show <b>{summary["affected"]} days with late check-ins '
        'and/or missing check-outs.</b></p>'
        '<p><b>This requires immediate improvement.</b> Repeated late arrivals and incomplete '
        'attendance records are not acceptable. You are expected to start work on time, '
        'work productively, and record your check-out at the end of your assigned shift.</p>'
        '<p>Your assigned shift and recorded attendance for each working day are shown below. '
        f'All times are in {escape(profile["region"])} local time (UTC+4).</p>'
        '<table style="border-collapse:collapse;width:100%"><thead><tr>'
        + ''.join('<th style="border:1px solid #ddd;padding:8px;text-align:left">' + name + '</th>'
                  for name in ('Date', 'Assigned shift', 'Check-in', 'Check-out', 'Attendance remark'))
        + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table>'
        f'<p><b>Weekly summary:</b> Late check-in: {summary["late"]} days; '
        f'missing check-out: {summary["missing"]} days; total affected days: {summary["affected"]}. '
        'A day with both issues is counted once.</p>'
        '<p><b>Please come on time, be productive, and leave on time.</b> Follow the start and end '
        'times of your assigned shift and record both check-in and check-out every working day.</p>'
        '<p>If any entry is incorrect or requires clarification, contact your reporting manager '
        'and HR promptly so the record can be reviewed.</p>'
        f'<p>Regards,<br>Human Resources — {escape(profile["region"])}<br>BITS Secure IT</p>')


def queue_one(employee, friday, now, account):
    if employee.user_id in EXCLUDED_USERS:
        return False
    key = weekly_key(employee.name, friday)
    if frappe.db.exists('Notification Log', key):
        return False
    summary = report(employee, friday, now)
    if not summary['qualifies']:
        return False
    if summary['hold']:
        frappe.log_error(title='Weekly attendance email held',
                         message=f'{employee.name}: {summary["hold"]}. No email was sent.')
        return False
    profile = site_profile()
    body = email_body(summary, profile)
    savepoint = 'weekly_attendance_email'
    frappe.db.savepoint(savepoint)
    try:
        frappe.get_doc(dict(doctype='Notification Log', name=key, type='Alert',
            for_user=employee.user_id, from_user='Administrator', subject=subject(summary),
            email_content=body, document_type='Employee', document_name=employee.name)).db_insert()
    except frappe.DuplicateEntryError:
        frappe.db.rollback(save_point=savepoint)
        return False
    try:
        queue = frappe.sendmail(recipients=[summary['to']], cc=summary['cc'], expose_recipients='header',
            sender=formataddr((profile['sender_name'], account.email_id)), reply_to=account.email_id,
            subject=subject(summary), message=body, reference_doctype='Employee',
            reference_name=employee.name, message_id=f'<{key}@bitssecureit.com>',
            delayed=True, now=False, add_unsubscribe_link=False, is_notification=True)
        if not queue or queue.email_account != account.name or profile['email'] not in queue.sender:
            frappe.throw('Weekly attendance summary must use the dedicated regional HR account.')
        return True
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def send_summaries():
    if not site_profile():
        return 0
    now = datetime.now(TZ)
    if not is_due(now) or not frappe.get_cached_doc('HR Settings').get(ENABLED):
        return 0
    account = configured_account()
    if not account:
        frappe.throw('The dedicated regional HR sender must be enabled.')
    sent = 0
    for employee in region_module().employees():
        try:
            sent += int(queue_one(employee, now.date(), now, account))
        except Exception:
            frappe.log_error(title='Weekly attendance email failed', message=frappe.get_traceback())
    return sent


def guard():
    frappe.only_for('System Manager')
    if not site_profile():
        frappe.throw('This setup is available only in Oman and UAE.')


@frappe.whitelist(methods=['GET'])
def page():
    guard()
    from frappe.sessions import get_csrf_token
    now = datetime.now(TZ)
    friday = next_run(now)
    start, end = reporting_period(friday)
    profile = site_profile()
    account = configured_account()
    enabled = bool(frappe.get_cached_doc('HR Settings').get(ENABLED))
    job = frappe.db.get_value('Scheduled Job Type', {'method': METHOD},
        ['name', 'stopped', 'cron_format', 'last_execution'], as_dict=True)
    active = bool(job and not job.stopped and job.cron_format == CRON)
    rows = []
    for employee in region_module().employees():
        item = report(employee, friday, now)
        status = ('Excluded by request' if item['excluded'] else 'Ready to send' if item['eligible'] else
                  ('Held: ' + item['hold'] if item['qualifies'] else 'Below 3 affected days'))
        cells = [item['name'], item['to'] or '—', ', '.join(item['cc']) or item['hold'],
                 item['late'], item['missing'], item['affected'], status]
        detail = ('—' if item['excluded'] else
                  f'<details><summary>View individual email</summary>{email_body(item, profile)}</details>')
        rows.append('<tr>' + ''.join('<td>' + escape(str(c)) + '</td>' for c in cells)
                    + '<td>' + detail + '</td></tr>')
    token = escape(get_csrf_token(), quote=True)
    body = f'''<style>.error-page{{height:auto!important;display:block!important;padding:24px}}
    .error-page>div{{max-width:1400px;margin:auto}}.error-page .details{{text-align:left}}
    td,th{{padding:8px;border:1px solid #ddd}}table{{border-collapse:collapse;width:100%}}</style>
    <h2>Weekly attendance summaries — {escape(profile['region'])}</h2>
    <p><b>Status: {'Enabled' if enabled else 'Disabled'}</b> · Every Friday at 9:02 AM (UTC+4) · Starts 13 November 2026</p>
    <p>Sender: {escape(account.email_id) if account else 'HR sender unavailable'}<br>
    To: each qualifying employee separately. CC: their reporting manager and {HR_CC}.</p>
    <p>Threshold: 3 or more distinct affected days (late check-in or missing final check-out).
    Assigned shift times, no grace period. Holidays, approved leave and approved arrangements excluded.
    No recorded check-in alone is not classified as late. Missing managers hold the email for HR review.
    Mohan is excluded from these weekly emails.</p>
    <p>Scheduler: {'Active' if active else 'Not active'} · Last run: {escape(str(job.last_execution or 'Not yet') if job else 'Not yet')}.</p>
    <form method="post" action="/api/method/bsgroup.weekly_attendance_email.configure">
    <input type="hidden" name="csrf_token" value="{token}">
    <input type="hidden" name="enabled" value="{'0' if enabled else '1'}">
    <button class="btn btn-primary" type="submit">{'Pause weekly emails' if enabled else 'Enable weekly emails'}</button></form>
    <h3>Preview for Friday {friday:%d %B %Y}: {start:%d %B}–{end:%d %B %Y}</h3>
    <p>Read-only preview using records available now. This sends no emails. The finished week is recalculated at sending time.</p>
    <table><thead><tr><th>Employee</th><th>To</th><th>CC / hold</th><th>Late days</th>
    <th>Missing check-out days</th><th>Affected days</th><th>Status</th><th>Email</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table>
    <p><a href="/desk/hr-settings">HR Settings</a> · <a href="/desk/email-queue">Email delivery log</a></p>'''
    frappe.respond_as_web_page('Weekly Attendance Emails', body, indicator_color='green' if enabled else 'orange')


@frappe.whitelist(methods=['POST'])
def configure(enabled):
    guard()
    value = int(enabled)
    if value not in (0, 1):
        frappe.throw('Enabled must be 0 or 1.')
    if value:
        if not configured_account() or not frappe.db.get_value('User', HR_CC, 'enabled'):
            frappe.throw('The regional HR sender and Muskan HR user must be enabled first.')
        system = ZoneInfo(frappe.utils.get_system_timezone())
        if datetime.now(system).utcoffset() != timedelta(hours=4):
            frappe.throw('The site scheduler timezone must be UTC+4 for Friday 9:02 AM.')
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    if not frappe.get_meta('HR Settings').has_field(ENABLED):
        create_custom_fields({'HR Settings': [dict(fieldname=ENABLED,
            label='Weekly attendance summary emails', fieldtype='Check', default='0',
            insert_after='custom_bs_hr_email_enabled',
            description='Friday 09:02; 3+ affected days; individual employee, CC manager and Muskan. '
            '<a href="/api/method/bsgroup.weekly_attendance_email.page">View weekly schedule and previews</a>')]}, update=False)
    settings = frappe.get_doc('HR Settings')
    settings.set(ENABLED, value)
    settings.save()
    from frappe.core.doctype.scheduled_job_type.scheduled_job_type import insert_single_event
    insert_single_event('Cron', METHOD, CRON)
    job = frappe.get_doc('Scheduled Job Type', {'method': METHOD})
    job.stopped = 0
    job.save()
    frappe.clear_cache(doctype='HR Settings')
    frappe.local.response.update(type='redirect', location='/api/method/bsgroup.weekly_attendance_email.page')
