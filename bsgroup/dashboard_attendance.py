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
    return dict(date=str(now.date()), check_in=first.strftime('%I:%M %p') if first else None,
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
        return dict(state='unlinked' if not employees else 'ambiguous')
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
