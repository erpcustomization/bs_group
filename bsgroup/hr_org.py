"""Organization editor using native Employee permissions, validation and audit."""
import frappe
from bsgroup.hr_management import _guard

FIELDS = ("first_name", "middle_name", "last_name", "designation", "department", "reports_to")


@frappe.whitelist()
def employee_details(employee):
    _guard()
    doc = frappe.get_doc("Employee", employee)
    doc.check_permission("read")
    doc.check_permission("write")
    return {**{key: doc.get(key) for key in FIELDS}, "name": doc.name,
            "employee_name": doc.employee_name, "company": doc.company, "modified": str(doc.modified)}


def _check_manager(employee, manager):
    """Lock the chain so concurrent moves cannot create circular reporting."""
    seen = {employee}
    current = manager
    first = True
    while current:
        if current in seen:
            frappe.throw("This reporting line would create a circular hierarchy. Choose another manager.")
        seen.add(current)
        doc = frappe.get_doc("Employee", current, for_update=True)
        if first:
            doc.check_permission("read")
            if doc.status != "Active":
                frappe.throw("Choose an active reporting manager.")
            first = False
        current = doc.reports_to


@frappe.whitelist(methods=["POST"])
def save_employee(employee, values, modified):
    _guard()
    values = frappe.parse_json(values)
    if not isinstance(values, dict) or not values or set(values) - set(FIELDS):
        frappe.throw("Only name, designation, department and reporting manager can be edited here.")
    if any(value is not None and (not isinstance(value, str) or len(value) > 140) for value in values.values()):
        frappe.throw("Enter valid employee details (up to 140 characters per field).")
    doc = frappe.get_doc("Employee", employee, for_update=True)
    doc.check_permission("read")
    doc.check_permission("write")
    if str(doc.modified) != str(modified):
        frappe.throw("This employee was updated by someone else. Refresh the chart and try again.")
    if doc.status != "Active":
        frappe.throw("This employee is no longer active. Open the HR profile to review it.")
    if "reports_to" in values and values["reports_to"] != doc.reports_to and values["reports_to"]:
        _check_manager(doc.name, values["reports_to"])
    for field, doctype in (("department", "Department"), ("designation", "Designation")):
        if values.get(field) and values[field] != doc.get(field):
            linked = frappe.get_doc(doctype, values[field])
            linked.check_permission("read")
            if field == "department" and linked.company and linked.company != doc.company:
                frappe.throw("Choose a department belonging to the employee’s company.")
    doc.update(values)
    # Native save retains field permissions, workflows, validation and Version history.
    doc.save()
    doc.add_comment("Info", "Employee profile updated from BS HR Organization Structure.")
    return {"name": doc.name, "employee_name": doc.employee_name}
