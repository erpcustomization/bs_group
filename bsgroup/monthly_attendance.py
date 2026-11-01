"""Own-user monthly attendance, read-only and capped at 09:00–18:00."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import frappe

TZ = ZoneInfo('Asia/Dubai')


def office_minutes(day, logs, now):
    start, end = (datetime.combine(day, time(h), TZ) for h in (9, 18))
    active = first = None
    seconds = 0
    for stamp, kind in sorted(logs):
        if stamp > now:
            continue
        if kind == 'IN':
            first = first or stamp
            active = active or stamp
        elif kind == 'OUT' and active:
            seconds += max(0, (min(stamp, end) - max(active, start)).total_seconds())
            active = None
    incomplete = bool(active and day < now.date())
    if active and day == now.date():
        seconds += max(0, (min(now, end) - max(active, start)).total_seconds())
    return int(seconds // 60), first, incomplete


@frappe.whitelist()
def get_month(month):
    if frappe.session.user == 'Guest':
        frappe.throw('Sign in to view attendance', frappe.PermissionError)
    try:
        start = date.fromisoformat(month + '-01')
    except (TypeError, ValueError):
        frappe.throw('Choose a valid month (YYYY-MM).')
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    now = datetime.now(TZ)
    key = 'bs-attendance-month-v1:' + frappe.session.user + ':' + month
    cached = frappe.cache.get_value(key)
    if cached is not None:
        return cached
    employees = frappe.get_all('Employee', filters={'user_id': frappe.session.user},
        fields=['name', 'default_shift', 'holiday_list', 'date_of_joining', 'relieving_date'], limit_page_length=2)
    if len(employees) != 1:
        return {'visible': False}
    emp = employees[0]
    site = ZoneInfo(frappe.utils.get_system_timezone())
    lower = datetime.combine(start, time(), TZ).astimezone(site).replace(tzinfo=None)
    upper = datetime.combine(end, time(), TZ).astimezone(site).replace(tzinfo=None)
    logs = frappe.get_all('Employee Checkin', filters=[['employee', '=', emp.name],
        ['time', '>=', lower], ['time', '<', upper]], fields=['time', 'log_type'], limit_page_length=0)
    by_day = {}
    for log in logs:
        stamp = frappe.utils.get_datetime(log.time).replace(tzinfo=site).astimezone(TZ)
        by_day.setdefault(stamp.date(), []).append((stamp, log.log_type))
    overlap = [['employee', '=', emp.name], ['docstatus', '=', 1],
               ['from_date', '<', end], ['to_date', '>=', start]]
    leaves = frappe.get_all('Leave Application', filters=overlap + [['status', '=', 'Approved']],
        fields=['from_date', 'to_date', 'half_day', 'half_day_date'], limit_page_length=0)
    duty = frappe.get_all('Attendance Request', filters=overlap + [['reason', 'in', ['On Duty', 'Work From Home']]],
        fields=['from_date', 'to_date', 'half_day', 'half_day_date'], limit_page_length=0)
    assignments = frappe.get_all('Shift Assignment', filters={'employee': emp.name, 'docstatus': 1,
        'status': 'Active', 'start_date': ['<', end]}, fields=['shift_type', 'start_date', 'end_date'],
        order_by='start_date desc, creation desc', limit_page_length=0)
    shifts = {}
    for name in {emp.default_shift} | {a.shift_type for a in assignments}:
        if name:
            shifts[name] = frappe.db.get_value('Shift Type', name, 'holiday_list')
    holidays = {}
    for name in set(shifts.values()) | {emp.holiday_list}:
        if name:
            holidays[name] = {frappe.utils.getdate(h.holiday_date): h.description for h in frappe.get_all(
                'Holiday', filters=[['parent', '=', name], ['parenttype', '=', 'Holiday List'],
                    ['holiday_date', '>=', start], ['holiday_date', '<', end]],
                fields=['holiday_date', 'description'], limit_page_length=0)}
    def portion(rows, day):
        result = 0
        for row in rows:
            if frappe.utils.getdate(row.from_date) <= day <= frappe.utils.getdate(row.to_date):
                half = row.half_day and row.half_day_date and frappe.utils.getdate(row.half_day_date) == day
                result = max(result, .5 if half else 1)
        return result
    totals = dict(on_time=0, late=0, working_minutes=0, leave=0, off=0, on_duty=0, no_checkin=0, incomplete=0)
    days = []
    day = start
    while day < end and day <= now.date():
        if ((emp.date_of_joining and day < frappe.utils.getdate(emp.date_of_joining)) or
                (emp.relieving_date and day > frappe.utils.getdate(emp.relieving_date))):
            day += timedelta(days=1)
            continue
        shift = next((a.shift_type for a in assignments if frappe.utils.getdate(a.start_date) <= day
            and (not a.end_date or frappe.utils.getdate(a.end_date) >= day)), emp.default_shift)
        holiday_list = shifts.get(shift) or emp.holiday_list
        holiday = holidays.get(holiday_list, {}).get(day)
        is_off = day in holidays.get(holiday_list, {})
        worked, first, incomplete = office_minutes(day, by_day.get(day, []), now)
        totals['working_minutes'] += worked
        totals['incomplete'] += int(incomplete)
        if is_off:
            status = 'off'
            totals['off'] += 1
        else:
            leave = portion(leaves, day)
            on_duty = min(1 - leave, portion(duty, day))
            totals['leave'] += leave
            totals['on_duty'] += on_duty
            remaining = 1 - leave - on_duty
            status = 'leave' if leave == 1 else 'on_duty' if on_duty == 1 else 'no_checkin'
            if remaining:
                status = ('late' if first > datetime.combine(day, time(9), TZ) else 'on_time') if first else 'no_checkin'
                totals[status] += remaining
        days.append(dict(date=str(day), status=status, working_minutes=worked,
            incomplete=incomplete, holiday=holiday or ''))
        day += timedelta(days=1)
    result = dict(visible=True, month=month, totals=totals, days=days,
        period='Month to date' if start <= now.date() < end else 'Full month',
        holiday_calendar_available=bool(any(holidays.values())))
    frappe.cache.set_value(key, result, expires_in_sec=300)
    return result
