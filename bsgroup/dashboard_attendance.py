"""Own-employee daily check-in summary; no attendance records are modified."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
import frappe


def summarize(logs, now):
    start = datetime.combine(now.date(), time(9), now.tzinfo)
    end = datetime.combine(now.date(), time(18), now.tzinfo)
    first = None
    active = None
    last_out = None
    seconds = 0
    unknown = False
    for log in sorted(logs, key=lambda r: r['time']):
        stamp = log['time']
        if stamp > now or stamp.date() != now.date():
            continue
        kind = log.get('log_type')
        if kind == 'IN':
            first = first or stamp
            if active is None:
                active = stamp
        elif kind == 'OUT':
            last_out = stamp
            if active is not None:
                seconds += max(0, (min(stamp, end) - max(active, start)).total_seconds())
                active = None
        else:
            unknown = True
    if active is not None:
        seconds += max(0, (min(now, end) - max(active, start)).total_seconds())
    remaining = max(0, int((end - max(now, start)).total_seconds() // 60))
    return dict(date=str(now.date()), wrap_up_due=time(17,30) <= now.time().replace(tzinfo=None) < time(18), check_in=first.strftime('%I:%M %p') if first else None,
                check_out=last_out.strftime('%I:%M %p') if last_out else None,
                late_minutes=max(0, int((first-start).total_seconds() // 60)) if first else None,
                worked_minutes=int(seconds // 60), remaining_minutes=remaining,
                available_minutes=max(0, int((end-max(first,start)).total_seconds() // 60)) if first else None,
                projected_minutes=int(seconds // 60)+remaining if active is not None else None,
                checked_in=active is not None and now < end, unknown_logs=unknown,
                state='checked_in' if active is not None and now < end else 'checked_out' if first else 'no_checkin')


@frappe.whitelist()
def today():
    # Never accept employee/user from the client. Employee Checkin access remains
    # narrow even when the user cannot browse the HR module.
    employees = frappe.get_all('Employee', filters={'user_id':frappe.session.user,'status':'Active'},
                                fields=['name'], limit_page_length=2)
    if len(employees) != 1:
        result = summarize([], datetime.now(ZoneInfo('Asia/Dubai')))
        result['state'] = 'unlinked' if not employees else 'ambiguous'
        return result
    dubai = ZoneInfo('Asia/Dubai')
    site = ZoneInfo(frappe.utils.get_system_timezone())
    now = datetime.now(dubai)
    midnight = datetime.combine(now.date(), time(), dubai)
    lower = midnight.astimezone(site).replace(tzinfo=None)
    upper = (midnight+timedelta(days=1)).astimezone(site).replace(tzinfo=None)
    rows = frappe.get_all('Employee Checkin', filters=[['employee','=',employees[0].name],
        ['time','>=',lower],['time','<',upper]], fields=['time','log_type'], order_by='time asc', limit_page_length=0)
    logs = [dict(time=frappe.utils.get_datetime(row.time).replace(tzinfo=site).astimezone(dubai),log_type=row.log_type) for row in rows]
    return summarize(logs, now)


@frappe.whitelist(methods=['POST'])
def wrap_up_reminder():
    """One in-app reminder per checked-in user/day while their ERP is open."""
    import hashlib
    now = datetime.now(ZoneInfo('Asia/Dubai'))
    if not time(17,30) <= now.time().replace(tzinfo=None) < time(18):
        return dict(due=False)
    attendance = today()
    if not attendance.get('checked_in'):
        return dict(due=False)
    key = 'wrapup-' + hashlib.sha256((frappe.session.user + str(now.date())).encode()).hexdigest()[:24]
    if not frappe.db.exists('Notification Log', key):
        doc = frappe.get_doc(dict(doctype='Notification Log', name=key, type='Alert',
            for_user=frappe.session.user, from_user=frappe.session.user,
            subject='Time to wrap up — your workday ends at 6 PM',
            email_content='Please finish your priority tasks, update their status, and prepare to wrap up by 6:00 PM.'))
        doc.db_insert(ignore_if_duplicate=True)
        frappe.publish_realtime('notification', user=frappe.session.user, after_commit=True)
    return dict(due=True, date=str(now.date()))
