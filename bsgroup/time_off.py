"""Dashboard time-off requests. Uses standard HRMS applications and approvals."""
import re
from datetime import timedelta
import frappe
from frappe.utils import getdate, flt
from bsgroup.dashboard_leave import dubai_today, has_records

ANNUAL = 'Annual Vacation'
SICK = 'Sick Leave'
UNPAID = 'Leave Without Pay'
CATEGORIES = ('Annual Leave', 'Sick Leave', 'Emergency Leave')


def own_employee():
    if frappe.session.user == 'Guest':
        frappe.throw('Please sign in.', frappe.PermissionError)
    rows = frappe.get_all('Employee', filters={'user_id': frappe.session.user, 'status': 'Active'},
                          fields=['name', 'employee_name', 'company'], limit_page_length=2)
    if len(rows) != 1:
        frappe.throw('Please ask HR to link your login to one active Employee record.')
    employee = rows[0]
    doc = frappe.new_doc('Leave Application')
    doc.employee, doc.company = employee.name, employee.company
    doc.check_permission('create')
    return employee


def dates(start, end):
    start, end = getdate(start), getdate(end)
    if start < getdate(dubai_today()):
        frappe.throw('Past dates are locked. Please contact HR for an approved correction.')
    if end < start or (end - start).days > 366:
        frappe.throw('Choose a valid date range of up to one year.')
    return start, end


def annual_available(employee, date):
    from hrms.hr.doctype.leave_application.leave_application import get_leave_details
    details = get_leave_details(employee, str(date))
    allocation = details.get('leave_allocation', {}).get(ANNUAL, {})
    remaining = flt(allocation.get('remaining_leaves'))
    pending = flt(allocation.get('leaves_pending_approval'))
    return max(0, remaining - pending), remaining, pending, details.get('leave_approver')


def split_emergency(day_rows):
    """Pure planner: date, annual charge, unpaid charge, available, allocation key.

    Consume annual balance in date order. HRMS supports full and half days.
    Keep each allocation separate so the native allocation checks remain intact.
    """
    parts, used = [], {}
    for day, annual_days, unpaid_days, available, key in day_rows:
        available = max(0, available - used.get(key, 0))
        paid = min(annual_days, available)
        if paid and abs(paid * 2 - round(paid * 2)) > .00001:
            raise ValueError('Your balance contains a fraction smaller than half a day. Please ask HR to review this split.')
        used[key] = used.get(key, 0) + paid
        if paid:
            parts.append(dict(leave_type=ANNUAL, from_date=str(day), to_date=str(day),
                              days=paid, half_day=int(paid == .5), half_day_date=str(day) if paid == .5 else None,
                              allocation=key))
        unpaid = unpaid_days if not paid else max(0, unpaid_days - paid)
        if available > 0 and annual_days == 0:
            unpaid = 0  # A holiday within the paid portion is not unpaid leave.
        if unpaid:
            parts.append(dict(leave_type=UNPAID, from_date=str(day), to_date=str(day),
                              days=unpaid, half_day=int(unpaid == .5), half_day_date=str(day) if unpaid == .5 else None,
                              allocation='unpaid'))
    # Merge adjacent full days; keep half days separate for native overlap checks.
    merged = []
    for part in parts:
        previous = merged[-1] if merged else None
        if (previous and not previous['half_day'] and not part['half_day']
                and previous['leave_type'] == part['leave_type'] and previous['allocation'] == part['allocation']
                and getdate(previous['to_date']) + timedelta(days=1) == getdate(part['from_date'])):
            previous['to_date'] = part['to_date']
            previous['days'] += part['days']
        else:
            merged.append(part.copy())
    return merged


def make_plan(employee, category, start, end):
    from hrms.hr.doctype.leave_application.leave_application import get_number_of_leave_days, get_leave_allocation_records
    if category not in CATEGORIES:
        frappe.throw('Choose Annual Leave, Sick Leave or Emergency Leave.')
    start, end = dates(start, end)
    available, remaining, pending, approver = annual_available(employee.name, start)
    if category != 'Emergency Leave':
        leave_type = ANNUAL if category == 'Annual Leave' else SICK
        days = flt(get_number_of_leave_days(employee.name, leave_type, str(start), str(end)))
        parts = [dict(leave_type=leave_type, from_date=str(start), to_date=str(end), days=days, half_day=0)]
    else:
        if not frappe.db.get_value('Leave Type', UNPAID, 'is_lwp'):
            frappe.throw('HR must configure Leave Without Pay before emergency requests can be processed.')
        rows, seen_balances = [], {}
        day = start
        while day <= end:
            allocations = get_leave_allocation_records(employee.name, str(day), ANNUAL)
            allocation = allocations.get(ANNUAL, {})
            key = str(allocation.get('name') or (str(allocation.get('from_date')) + ':' + str(allocation.get('to_date'))))
            # Include date in the balance lookup to respect carry-forward expiry.
            balance = annual_available(employee.name, day)[0]
            if key in seen_balances and abs(seen_balances[key] - balance) > .00001:
                frappe.throw('This request spans an annual balance expiry/change. Please apply separately on each side of that date, or ask HR to review it.')
            seen_balances[key] = balance
            rows.append((day,
                flt(get_number_of_leave_days(employee.name, ANNUAL, str(day), str(day))),
                flt(get_number_of_leave_days(employee.name, UNPAID, str(day), str(day))), balance, key))
            day += timedelta(days=1)
        try:
            parts = split_emergency(rows)
        except ValueError as exc:
            frappe.throw(str(exc))
    if not parts or sum(p['days'] for p in parts) <= 0:
        frappe.throw('The selected dates contain no leave days under your HR holiday calendar.')
    return dict(parts=parts, annual_available=available, annual_balance=remaining, pending_annual=pending,
                annual_days=sum(p['days'] for p in parts if p['leave_type'] == ANNUAL),
                unpaid_days=sum(p['days'] for p in parts if p['leave_type'] == UNPAID),
                total_days=sum(p['days'] for p in parts), leave_approver=approver,
                certificate_required=category == 'Sick Leave' and sum(p['days'] for p in parts) > 1)


@frappe.whitelist()
def preview(category='Annual Leave', from_date=None, to_date=None):
    employee = own_employee()
    start = from_date or dubai_today()
    result = make_plan(employee, category, start, to_date or start)
    result.update(employee_name=employee.employee_name, today=dubai_today())
    return result


@frappe.whitelist(methods=['POST'])
def apply(category, from_date, to_date, request_id, expected_plan, reason='', contact_name='', contact_phone='', certificate=None):
    employee = own_employee()
    if not re.fullmatch(r'[a-zA-Z0-9-]{16,64}', request_id or ''):
        frappe.throw('Please reopen Time Off and try again.')
    # Row lock serializes dashboard applications for this employee until commit.
    frappe.db.sql('select name from `tabEmployee` where name=%s for update', employee.name)
    existing = frappe.get_list('Leave Application', filters={'employee': employee.name, 'custom_time_off_reference': request_id}, pluck='name')
    if existing:
        return {'names': existing}
    if has_records(employee.name, from_date, to_date):
        frappe.throw('These dates already have attendance or leave records. Please contact HR for an approved correction.')
    plan = make_plan(employee, category, from_date, to_date)
    if frappe.parse_json(expected_plan) != plan['parts']:
        frappe.throw('Your balance or leave calculation changed. Reopen Time Off to review the updated paid/unpaid split.')
    if category == 'Annual Leave' and plan['total_days'] > plan['annual_available']:
        frappe.throw('The requested annual leave exceeds your available balance after pending requests.')
    if category == 'Emergency Leave' and (not contact_name.strip() or not contact_phone.strip() or not reason.strip()):
        frappe.throw('Enter the emergency reason, contact name and phone number.')
    if plan['certificate_required'] and not certificate:
        frappe.throw('Please attach a medical certificate for sick leave exceeding one day.')
    if certificate and category != 'Sick Leave':
        certificate = None
    if certificate:
        files = frappe.get_all('File', filters={'file_url': certificate, 'owner': frappe.session.user, 'is_private': 1}, pluck='name', limit_page_length=1)
        if not files:
            frappe.throw('Upload your medical certificate as a private attachment.', frappe.PermissionError)
        if frappe.db.get_value('File', files[0], 'attached_to_name'):
            frappe.throw('Please upload a new certificate copy for this request; existing document attachments are preserved.')
    names = []
    for part in plan['parts']:
        doc = frappe.new_doc('Leave Application')
        doc.update(dict(employee=employee.name, company=employee.company, leave_type=part['leave_type'],
            from_date=part['from_date'], to_date=part['to_date'], half_day=part['half_day'],
            half_day_date=part.get('half_day_date'), status='Open', leave_approver=plan['leave_approver'],
            description=reason, custom_time_off_category=category, custom_time_off_reference=request_id,
            custom_emergency_contact_name=contact_name.strip() if category == 'Emergency Leave' else '',
            custom_emergency_contact_phone=contact_phone.strip() if category == 'Emergency Leave' else '',
            custom_medical_certificate=certificate if category == 'Sick Leave' else None))
        # Only the paired parts generated in this server transaction may overlap.
        doc.flags.time_off_siblings = names[:]
        doc.flags.time_off_request = True
        doc.insert()
        names.append(doc.name)
        if certificate and category == 'Sick Leave':
            attachment = frappe.get_doc('File', files[0])
            attachment.attached_to_doctype = 'Leave Application'
            attachment.attached_to_name = doc.name
            attachment.attached_to_field = 'custom_medical_certificate'
            attachment.save()
    return {'names': names, 'annual_days': plan['annual_days'], 'unpaid_days': plan['unpaid_days']}
