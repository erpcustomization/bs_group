"""Own-employee dashboard links into the standard HR leave process."""
import frappe
from frappe.utils import today
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


def dubai_today():
    return str(datetime.now(ZoneInfo('Asia/Dubai')).date())


def has_records(employee, start, end, exclude=None):
    start, end = frappe.utils.getdate(start), frappe.utils.getdate(end)
    site = ZoneInfo(frappe.utils.get_system_timezone())
    lower = datetime.combine(start, time(), ZoneInfo('Asia/Dubai')).astimezone(site).replace(tzinfo=None)
    upper = datetime.combine(end + timedelta(days=1), time(), ZoneInfo('Asia/Dubai')).astimezone(site).replace(tzinfo=None)
    if frappe.db.exists('Employee Checkin', [['employee', '=', employee], ['time', '>=', lower], ['time', '<', upper]]):
        return True
    if frappe.db.exists('Attendance', [['employee', '=', employee], ['docstatus', '<', 2], ['attendance_date', '>=', start], ['attendance_date', '<=', end]]):
        return True
    for dt in ('Leave Application', 'Attendance Request'):
        filters = [['employee', '=', employee], ['docstatus', '<', 2], ['from_date', '<=', end], ['to_date', '>=', start]]
        if dt == 'Leave Application':
            filters.append(['status', '!=', 'Rejected'])
            if exclude:
                filters.append(['name', '!=', exclude])
        if frappe.db.exists(dt, filters):
            return True
    return False


def validate_self_service(doc):
    if frappe.session.user == 'Administrator' or set(frappe.get_roles()) & {'HR User', 'HR Manager'}:
        return
    previous = doc.get_doc_before_save()
    fields = ('employee', 'from_date', 'to_date', 'leave_type', 'half_day', 'half_day_date', 'description')
    # Preserve the existing approval flow for requests already filed.
    if previous and all(previous.get(f) == doc.get(f) for f in fields):
        return
    if not doc.from_date or not doc.to_date or not doc.employee:
        return
    if frappe.utils.getdate(doc.from_date) < frappe.utils.getdate(dubai_today()) or (previous and frappe.utils.getdate(previous.from_date) < frappe.utils.getdate(dubai_today())):
        frappe.throw('Past dates are locked. Please contact HR for an approved correction.')
    if has_records(doc.employee, doc.from_date, doc.to_date, doc.name):
        frappe.throw('These dates already have attendance or leave records. Please contact HR for an approved correction.')


@frappe.whitelist()
def context():
    if frappe.session.user == 'Guest':
        frappe.throw('Please sign in.', frappe.PermissionError)
    employees = frappe.get_all('Employee',
        filters={'user_id': frappe.session.user, 'status': 'Active'},
        fields=['name', 'employee_name', 'company'], limit_page_length=2)
    if len(employees) != 1:
        return {'visible': False}
    employee = employees[0]
    draft = frappe.new_doc('Leave Application')
    draft.employee = employee.name
    draft.company = employee.company
    can_create = frappe.has_permission('Leave Application', 'create', doc=draft)
    requests = frappe.get_list('Leave Application',
        filters={'employee': employee.name, 'docstatus': ['<', 2],
                 'status': ['in', ['Open', 'Approved']]},
        fields=['name', 'from_date', 'to_date', 'leave_type', 'status', 'docstatus'],
        order_by='from_date desc', limit_page_length=0)
    current = dubai_today()
    return dict(visible=True, employee=employee.name, company=employee.company,
                can_create=bool(can_create), requests=requests, today=current,
                today_locked=has_records(employee.name, current, current))
