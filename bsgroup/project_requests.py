"""Read-only entry points for the existing project advance and labour workflows."""
import frappe
from frappe import _
from bsgroup.project_expenses import own_employee, project_doc


KINDS = {
    "advance": ("Employee Advance", "custom_project", "advance_amount"),
    "labor": ("Labor Preapproval", "reference", "total_labor_cost"),
}


@frappe.whitelist()
def context(project, kind):
    if kind not in KINDS:
        frappe.throw(_("Choose Advance or Labour Approval."))
    doc = project_doc(project)
    doctype, project_field, amount_field = KINDS[kind]
    meta = frappe.get_meta(doctype)
    filters = {project_field: doc.name}
    defaults = {project_field: doc.name, "company": doc.company}
    problem = None
    if kind == "advance":
        employee = own_employee(doc.company)
        defaults["employee"] = employee
        if not employee:
            problem = _("Your login must be linked to one active Employee in this project's company to request an advance.")
        if not set(frappe.get_roles()) & {"Expense Approver", "System Manager", "Accounts Manager", "Accounts User", "HR Manager"}:
            filters["employee"] = employee or "__no_employee__"
    else:
        filters["source"] = "Project"
        defaults["source"] = "Project"
        defaults["cost_center"] = doc.get("cost_center") or frappe.db.get_value("Company", doc.company, "cost_center")
    can_create = bool(frappe.has_permission(doctype, "create") and not problem and doc.status != "Cancelled")
    if not frappe.has_permission(doctype, "create"):
        problem = _("Your existing access does not allow creating {0}. Contact the administrator.").format(doctype)
    elif doc.status == "Cancelled":
        problem = _("New requests cannot be raised against a cancelled project.")
    fields = ["name", "creation", "docstatus", amount_field]
    fields += [field for field in ("workflow_state", "status", "currency", "employee_name", "task") if meta.has_field(field)]
    # get_list retains role, document and company restrictions. No sharing or permission writes.
    records = frappe.get_list(doctype, filters=filters, fields=fields, order_by="creation desc",
                              page_length=100) if frappe.has_permission(doctype, "read") else []
    return {"doctype": doctype, "project": doc.name, "project_name": doc.project_name,
            "company": doc.company, "currency": frappe.db.get_value("Company", doc.company, "default_currency"),
            "records": records, "amount_field": amount_field, "defaults": defaults,
            "can_create": can_create, "problem": problem}
