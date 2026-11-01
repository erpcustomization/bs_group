"""Read-only, session-owned dashboard attendance. HR policy is never modified."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import frappe

DUBAI = ZoneInfo('Asia/Dubai')
DASHBOARD_SHIFTS = {'General - UAE', 'Enterprise Sales Shift', 'Presales'}


def shift_bounds(day, shift):
    def at(value):
        return datetime.combine(day, time(), DUBAI) + frappe.utils.to_timedelta(value)
    start = at(shift.start_time)
    end = at(shift.end_time)
    if shift.name in DASHBOARD_SHIFTS:
        start = datetime.combine(day, time(9), DUBAI)
        end = datetime.combine(day, time(18), DUBAI)
    elif end <= start:
        end += timedelta(days=1)
    return start, end


@frappe.whitelist()
def get_today_status():
    if frappe.session.user == 'Guest':
        frappe.throw('Sign in to view attendance', frappe.PermissionError)
    now = datetime.now(DUBAI)
    key = 'bs-attendance-v2:' + frappe.session.user + ':' + str(now.date())
    cached = frappe.cache.get_value(key)
    if cached is not None:
        return cached
    result = _status(now)
    frappe.cache.set_value(key, result, expires_in_sec=300)
    return result


def _status(now, user=None):
    # get_all intentionally bypasses HR permissions ONLY after session ownership
    # is resolved. No employee or user argument is accepted from the browser.
    employees = frappe.get_all('Employee', filters={
        'user_id': user or frappe.session.user, 'status': 'Active'},
        fields=['name', 'default_shift', 'holiday_list'], limit_page_length=2)
    if len(employees) != 1:
        return {'visible': False}
    employee = employees[0]
    day = now.date()
    assignments = frappe.get_all('Shift Assignment', filters={
        'employee': employee.name, 'docstatus': 1, 'status': 'Active',
        'start_date': ['<=', day]},
        or_filters=[['end_date', 'is', 'not set'], ['end_date', '>=', day]],
        fields=['shift_type'], order_by='start_date desc, creation desc', limit_page_length=1)
    shift_name = assignments[0].shift_type if assignments else employee.default_shift
    if not shift_name:
        return {'visible': False}
    shift = frappe.get_doc('Shift Type', shift_name)
    start, end = shift_bounds(day, shift)
    site = ZoneInfo(frappe.utils.get_system_timezone())
    lower = datetime.combine(day, time(), DUBAI)
    upper = max(lower + timedelta(days=1), end)
    logs = frappe.get_all('Employee Checkin', filters=[
        ['employee', '=', employee.name],
        ['time', '>=', lower.astimezone(site).replace(tzinfo=None)],
        ['time', '<', upper.astimezone(site).replace(tzinfo=None)]],
        fields=['time', 'log_type'], order_by='time asc', limit_page_length=0)
    first = last_out = active = None
    worked = 0
    for log in logs:
        stamp = frappe.utils.get_datetime(log.time).replace(tzinfo=site).astimezone(DUBAI)
        if stamp > now:
            continue
        if log.log_type == 'IN':
            first = first or stamp
            active = active or stamp
        elif log.log_type == 'OUT':
            last_out = stamp
            if active:
                worked += max(0, (stamp - active).total_seconds())
                active = None
    if active:
        worked += max(0, (now - active).total_seconds())
    holiday_list = shift.holiday_list or employee.holiday_list
    holiday = frappe.db.get_value('Holiday', {
        'parent': holiday_list, 'parenttype': 'Holiday List', 'holiday_date': day},
        'description') if holiday_list else None
    leave = frappe.db.exists('Leave Application', {
        'employee': employee.name, 'docstatus': 1, 'status': 'Approved',
        'from_date': ['<=', day], 'to_date': ['>=', day]})
    requests = frappe.get_all('Attendance Request', filters={
        'employee': employee.name, 'docstatus': 1, 'from_date': ['<=', day],
        'to_date': ['>=', day], 'reason': ['in', ['On Duty', 'Work From Home']]},
        fields=['reason'], limit_page_length=1)
    iso = lambda value: value.isoformat() if value else None
    return dict(visible=True, date=str(day), server_now=iso(now),
        shift_start=iso(start), shift_end=iso(end), grace_min=0,
        first_in=iso(first), last_out=iso(last_out), checked_in=bool(active),
        active_since=iso(active), worked_minutes=int(worked // 60),
        late_minutes=max(0, int((first-start).total_seconds() // 60)) if first else 0,
        early_exit_minutes=max(0, int((end-last_out).total_seconds() // 60)) if last_out and not active else 0,
        is_holiday=holiday is not None, holiday_name=holiday or '',
        on_leave=bool(leave), on_duty=bool(requests),
        duty_type=requests[0].reason if requests else None,
        lunch_start=iso(datetime.combine(day, time(12,30), DUBAI)),
        lunch_end=iso(datetime.combine(day, time(13), DUBAI)),
        wrapup_start=iso(end-timedelta(minutes=30)))
