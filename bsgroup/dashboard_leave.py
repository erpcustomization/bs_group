"""Own-employee dashboard links into the standard HR leave process."""
import frappe
from frappe.utils import today


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
    return dict(visible=True, employee=employee.name, company=employee.company,
                can_create=bool(can_create), requests=requests, today=today())
