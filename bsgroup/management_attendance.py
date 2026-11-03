"""Company-scoped employee headcounts for the chairman's daily dashboard."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import frappe
from bsgroup.attendance_widget import shift_bounds

TZ = ZoneInfo('Asia/Dubai')


def classify(start, now, first, last_out, holiday=False, leave=0, duty=0):
    if holiday:
        return 'off'
    if leave == 1:
        return 'leave'
    if duty == 1:
        return 'on_duty'
    if leave or duty:
        return 'partial_day'
    if not start:
        return 'unconfigured'
    if not first:
        return 'not_started' if now < start else 'no_checkin'
    if first <= start:
        return 'on_time'
    return 'late' if last_out and last_out > first else 'pending_checkout'


def overview(day):
    if frappe.session.user not in {'mohan@bitssecureit.com', 'Administrator'}:
        frappe.throw('This employee overview is available to Mohan only.', frappe.PermissionError)
    # The chairman requested aggregate employee attendance. His employee-level
    # self-service restriction must not narrow the company headcount to himself.
    # Resolve readable companies first; return only names and punch times for
    # the requested headcount drilldown, never full HR documents or leave reasons.
    companies = frappe.get_list('Company', pluck='name', limit_page_length=0)
    totals = dict(on_time=0, late=0, pending_checkout=0, no_checkin=0,
                  leave=0, on_duty=0, off=0, not_started=0, partial_day=0, unconfigured=0)
    details = {key:[] for key in totals}
    if not companies:
        return dict(total=0, totals=totals, details=details, day=str(day))
    employees = frappe.get_all('Employee', filters={'company':['in',companies]},
        fields=['name','employee_name','status','date_of_joining','relieving_date','default_shift','holiday_list'],
        limit_page_length=0)
    employees = [e for e in employees
        if (not e.date_of_joining or frappe.utils.getdate(e.date_of_joining) <= day)
        and (not e.relieving_date or frappe.utils.getdate(e.relieving_date) >= day)
        and (e.status == 'Active' or bool(e.relieving_date))]
    names = [e.name for e in employees]
    if not names:
        return dict(total=0, totals=totals, details=details, day=str(day))
    now = datetime.now(TZ)
    site = ZoneInfo(frappe.utils.get_system_timezone())
    lower = datetime.combine(day, time(), TZ)
    upper = lower + timedelta(days=1)
    logs = frappe.get_all('Employee Checkin', filters=[['employee','in',names],
        ['time','>=',lower.astimezone(site).replace(tzinfo=None)],
        ['time','<',upper.astimezone(site).replace(tzinfo=None)]],
        fields=['employee','time','log_type'], order_by='time asc', limit_page_length=0)
    punches = {}
    for log in logs:
        stamp = frappe.utils.get_datetime(log.time).replace(tzinfo=site).astimezone(TZ)
        if stamp <= now:
            punches.setdefault(log.employee, []).append((stamp,log.log_type))
    assignments = frappe.get_all('Shift Assignment', filters=[['employee','in',names],
        ['docstatus','=',1],['status','=','Active'],['start_date','<=',day]],
        fields=['employee','shift_type','end_date'],order_by='start_date desc, creation desc',limit_page_length=0)
    assigned = {}
    for row in assignments:
        if row.employee not in assigned and (not row.end_date or frappe.utils.getdate(row.end_date)>=day):
            assigned[row.employee] = row.shift_type
    shift_names = {assigned.get(e.name) or e.default_shift for e in employees} - {None,''}
    shifts = {name:frappe.get_doc('Shift Type',name) for name in shift_names}
    lists = {e.holiday_list for e in employees} | {s.holiday_list for s in shifts.values()}
    lists -= {None,''}
    off_lists = set(frappe.get_all('Holiday', filters={'parent':['in',list(lists)],
        'parenttype':'Holiday List','holiday_date':day},pluck='parent',limit_page_length=0)) if lists else set()
    overlap = [['employee','in',names],['docstatus','=',1],['from_date','<=',day],['to_date','>=',day]]
    leaves = frappe.get_all('Leave Application',filters=overlap+[['status','=','Approved']],
        fields=['employee','half_day','half_day_date'],limit_page_length=0)
    duty = frappe.get_all('Attendance Request',filters=overlap+[['reason','in',['On Duty','Work From Home']]],
        fields=['employee','half_day','half_day_date'],limit_page_length=0)

    def portions(rows):
        result = {}
        for row in rows:
            half = row.half_day and (not row.half_day_date or frappe.utils.getdate(row.half_day_date)==day)
            result[row.employee] = max(result.get(row.employee,0), .5 if half else 1)
        return result

    leave_by_employee, duty_by_employee = portions(leaves), portions(duty)
    for employee in employees:
        shift = shifts.get(assigned.get(employee.name) or employee.default_shift)
        start = shift_bounds(day,shift)[0] if shift else None
        holiday_list = (shift.holiday_list if shift else None) or employee.holiday_list
        employee_logs = punches.get(employee.name,[])
        first = next((stamp for stamp,kind in employee_logs if kind=='IN'),None)
        last_out = next((stamp for stamp,kind in reversed(employee_logs) if kind=='OUT'),None)
        status = classify(start,now,first,last_out,holiday_list in off_lists,
                          leave_by_employee.get(employee.name,0),duty_by_employee.get(employee.name,0))
        totals[status] += 1
        label = f"{employee.employee_name or employee.name} ({employee.name})"
        if first:
            label += ' · IN ' + first.strftime('%I:%M %p')
        if last_out:
            label += ' · OUT ' + last_out.strftime('%I:%M %p')
        if start:
            label += ' · Shift starts ' + start.strftime('%I:%M %p')
        details[status].append(label)
    for rows in details.values():
        rows.sort(key=str.casefold)
    return dict(total=len(employees),totals=totals,details=details,day=str(day))
