"""Read-only early checkout indicator for the company dashboard."""
from datetime import date, datetime, time, timedelta
from math import ceil
from zoneinfo import ZoneInfo

import frappe


def scheduled_bounds(day, shift, tz):
    """Use the actual assigned shift, including overnight shifts, without overrides."""
    midnight = datetime.combine(day, time(), tz)
    start = midnight + frappe.utils.to_timedelta(shift.start_time)
    end = midnight + frappe.utils.to_timedelta(shift.end_time)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def early_departure(logs, start, end, now, before_minutes=0, after_minutes=0):
    """Latest completed departure; a subsequent IN clears the early-out indicator."""
    midnight = datetime.combine(start.date(), time(), start.tzinfo)
    overnight = end.date() > start.date()
    lower = start - timedelta(minutes=before_minutes) if overnight else midnight
    upper = max(midnight + timedelta(days=1), end + timedelta(minutes=after_minutes))
    first = last_out = None
    active = False
    for stamp, kind in sorted(logs, key=lambda row: row[0]):
        if stamp < lower or stamp > upper or stamp > now:
            continue
        if kind == 'IN':
            first = first or stamp
            active = True
        elif kind == 'OUT' and first and stamp > first:
            last_out = stamp
            active = False
    if not first or active or not last_out or last_out >= end:
        return None
    return dict(first_in=first, checkout=last_out,
                minutes_early=ceil((end - last_out).total_seconds() / 60))


@frappe.whitelist()
def summary(day=None):
    # Same company overview access boundary as management_attendance.overview.
    if frappe.session.user not in {'mohan@bitssecureit.com', 'Administrator'}:
        frappe.throw('You do not have access to the company attendance overview.', frappe.PermissionError)
    tz = ZoneInfo(frappe.utils.get_system_timezone())
    now = datetime.now(tz)
    try:
        selected = date.fromisoformat(day) if day else now.date()
    except (TypeError, ValueError):
        frappe.throw('Choose a valid reporting date.')
    if selected > now.date():
        frappe.throw('Choose today or an earlier date.')
    result = dict(day=str(selected), count=0, details=[])
    companies = frappe.get_list('Company', pluck='name', limit_page_length=0)
    if not companies:
        return result
    employees = frappe.get_all('Employee', filters={'company': ['in', companies]},
        fields=['name', 'employee_name', 'status', 'date_of_joining', 'relieving_date',
                'default_shift', 'holiday_list'], limit_page_length=0)
    employees = [e for e in employees
        if (not e.date_of_joining or frappe.utils.getdate(e.date_of_joining) <= selected)
        and (not e.relieving_date or frappe.utils.getdate(e.relieving_date) >= selected)
        and (e.status == 'Active' or bool(e.relieving_date))]
    names = [e.name for e in employees]
    if not names:
        return result
    assignments = frappe.get_all('Shift Assignment', filters=[['employee', 'in', names],
        ['docstatus', '=', 1], ['status', '=', 'Active'], ['start_date', '<=', selected]],
        fields=['employee', 'shift_type', 'end_date'],
        order_by='start_date desc, creation desc', limit_page_length=0)
    assigned = {}
    for row in assignments:
        if row.employee not in assigned and (not row.end_date or frappe.utils.getdate(row.end_date) >= selected):
            assigned[row.employee] = row.shift_type
    shift_names = {assigned.get(e.name) or e.default_shift for e in employees} - {None, ''}
    shifts = {name: frappe.get_doc('Shift Type', name) for name in shift_names}
    lists = ({e.holiday_list for e in employees} | {s.holiday_list for s in shifts.values()}) - {None, ''}
    off = set(frappe.get_all('Holiday', filters={'parent': ['in', list(lists)],
        'parenttype': 'Holiday List', 'holiday_date': selected},
        pluck='parent', limit_page_length=0)) if lists else set()
    overlap = [['employee', 'in', names], ['docstatus', '=', 1],
               ['from_date', '<=', selected], ['to_date', '>=', selected]]
    excused = set(frappe.get_all('Leave Application', filters=overlap + [['status', '=', 'Approved']],
        pluck='employee', limit_page_length=0))
    excused.update(frappe.get_all('Attendance Request',
        filters=overlap + [['reason', 'in', ['On Duty', 'Work From Home']]],
        pluck='employee', limit_page_length=0))
    windows = {}
    for employee in employees:
        shift = shifts.get(assigned.get(employee.name) or employee.default_shift)
        if not shift or employee.name in excused or (shift.holiday_list or employee.holiday_list) in off:
            continue
        start, end = scheduled_bounds(selected, shift, tz)
        before = max(0, float(shift.get('begin_check_in_before_shift_start_time') or 0))
        after = max(0, float(shift.get('allow_check_out_after_shift_end_time') or 0))
        windows[employee.name] = (shift, start, end, before, after)
    if not windows:
        return result
    midnight = datetime.combine(selected, time(), tz)
    lower = min([midnight] + [v[1] - timedelta(minutes=v[3]) for v in windows.values()])
    upper = max([midnight + timedelta(days=1)] + [v[2] + timedelta(minutes=v[4]) for v in windows.values()])
    logs = frappe.get_all('Employee Checkin', filters=[['employee', 'in', list(windows)],
        ['time', '>=', lower.replace(tzinfo=None)], ['time', '<=', upper.replace(tzinfo=None)]],
        fields=['employee', 'time', 'log_type'], order_by='time asc, creation asc, name asc', limit_page_length=0)
    punches = {}
    for log in logs:
        stamp = frappe.utils.get_datetime(log.time)
        stamp = stamp.replace(tzinfo=tz) if stamp.tzinfo is None else stamp.astimezone(tz)
        punches.setdefault(log.employee, []).append((stamp, log.log_type))
    for employee in employees:
        if employee.name not in windows:
            continue
        shift, start, end, before, after = windows[employee.name]
        early = early_departure(punches.get(employee.name, []), start, end, now, before, after)
        if early:
            result['details'].append(dict(employee=employee.name,
                employee_name=employee.employee_name or employee.name, shift=shift.name,
                checkin=early['first_in'].isoformat(), checkout=early['checkout'].isoformat(),
                shift_end=end.isoformat(), minutes_early=early['minutes_early']))
    result['details'].sort(key=lambda row: row['employee_name'].casefold())
    result['count'] = len(result['details'])
    return result
