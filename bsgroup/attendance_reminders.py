"""One morning in-app reminder per employee/day; no email or HR changes."""
from datetime import datetime, time
from zoneinfo import ZoneInfo
import hashlib
import frappe

METHOD = 'bsgroup.attendance_reminders.send_morning_reminders'


def needs_reminder(status):
    return bool(status.get('visible') and not any(status.get(k) for k in
        ('first_in', 'is_holiday', 'on_leave', 'on_duty')) and
        datetime.fromisoformat(status['shift_start']).time() == time(9))


def send_morning_reminders():
    now = datetime.now(ZoneInfo('Asia/Dubai'))
    # A short retry window accommodates scheduler delays; the unique daily key
    # prevents repeated reminders. No late-night catch-up notifications.
    if not time(9, 1) <= now.time().replace(tzinfo=None) < time(9, 30):
        return 0
    from bsgroup.attendance_widget import _status
    employees = frappe.get_all('Employee', filters={
        'status': 'Active', 'company': 'Bits Secure IT Infrastructure LLC - AE'},
        fields=['user_id', 'date_of_joining', 'relieving_date'])
    sent = 0
    for employee in employees:
        user = employee.user_id
        if not user or not frappe.db.get_value('User', user, 'enabled'):
            continue
        if employee.date_of_joining and frappe.utils.getdate(employee.date_of_joining) > now.date():
            continue
        if employee.relieving_date and frappe.utils.getdate(employee.relieving_date) < now.date():
            continue
        key = 'morning-' + hashlib.sha256((user + str(now.date())).encode()).hexdigest()[:24]
        if frappe.db.exists('Notification Log', key) or not needs_reminder(_status(now, user=user)):
            continue
        message = 'Office hours start at 9 AM. You haven’t checked in yet. Please check in or apply for leave if you are away today.'
        doc = frappe.get_doc(dict(doctype='Notification Log', name=key, type='Alert',
            for_user=user, from_user='Administrator',
            subject='Your working hours have started. ' + message,
            email_content=message, link='/desk/bs-group/my-work-dashboard'))
        doc.db_insert(ignore_if_duplicate=True)
        frappe.publish_realtime('notification', user=user, after_commit=True)
        sent += 1
    return sent


@frappe.whitelist(methods=['POST'])
def install():
    if frappe.session.user != 'Administrator':
        frappe.throw('Only Administrator can configure attendance reminders.', frappe.PermissionError)
    from frappe.core.doctype.scheduled_job_type.scheduled_job_type import insert_single_event
    insert_single_event('Cron', METHOD, '* * * * *')
    return frappe.db.get_value('Scheduled Job Type', {'method': METHOD},
        ['name', 'stopped', 'cron_format'], as_dict=True)
