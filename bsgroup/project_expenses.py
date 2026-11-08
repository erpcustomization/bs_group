"""Project-bound claims; native HRMS permissions, sharing and accounting remain in charge."""
import frappe
from frappe import _


def project_doc(name):
    if not name:
        frappe.throw(_("Open the project you are working on and choose Expenses. A project is required."))
    project = frappe.get_doc("Project", name)
    project.check_permission("read")
    return project


def manager_for(project):
    manager = frappe.db.get_value("Employee", project.get("custom_project_manager"),
                                  ["user_id", "status"], as_dict=True) if project.get("custom_project_manager") else None
    if not manager or manager.status != "Active" or not manager.user_id:
        return None, _("An active Project Manager with an ERP login must be assigned before expenses can be raised.")
    user = manager.user_id
    if not frappe.db.get_value("User", user, "enabled"):
        return None, _("The Project Manager's ERP login is disabled. Ask the administrator to review the assignment.")
    if "Expense Approver" not in frappe.get_roles(user):
        return None, _("The assigned Project Manager does not have Expense Approver access. Ask the administrator to review it.")
    if not frappe.has_permission("Project", "read", doc=project, user=user):
        return None, _("The Project Manager cannot access this project. Ask the administrator to review the assignment.")
    return user, None


def own_employee(company):
    rows = frappe.get_all("Employee", filters={"user_id": frappe.session.user,
                         "status": "Active", "company": company}, fields=["name"], limit_page_length=2)
    return rows[0].name if len(rows) == 1 else None


@frappe.whitelist()
def context(project):
    """Read-only project panel; never bypass document or company permissions."""
    doc = project_doc(project)
    manager, problem = manager_for(doc)
    employee = own_employee(doc.company)
    can_create = bool(frappe.has_permission("Expense Claim", "create") and employee and manager
                      and doc.status != "Cancelled")
    if not employee:
        problem = _("Your login must be linked to one active Employee in this project's company to raise your expense claim.")
    elif not frappe.has_permission("Expense Claim", "create"):
        problem = _("Your existing access does not allow creating Expense Claims. Contact the administrator.")
    elif doc.status == "Cancelled":
        problem = _("Expenses cannot be raised against a cancelled project.")
    filters = {"project": doc.name}
    # Native permissions are still applied; this further limits ordinary employees to their own claims.
    reviewer = manager == frappe.session.user or bool(set(frappe.get_roles()) & {"System Manager", "Accounts Manager", "Accounts User", "HR Manager"})
    if not reviewer:
        filters["employee"] = employee or "__no_employee__"
    claims = frappe.get_list("Expense Claim", filters=filters,
        fields=["name", "employee_name", "posting_date", "workflow_state", "status", "total_claimed_amount"],
        order_by="creation desc", page_length=100) if frappe.has_permission("Expense Claim", "read") else []
    return {"project": doc.name, "project_name": doc.project_name, "company": doc.company,
            "employee": employee, "expense_approver": manager, "can_create": can_create,
            "problem": problem, "claims": claims,
            "currency": frappe.db.get_value("Company", doc.company, "default_currency")}


def validate(doc, method=None):
    old = doc.get_doc_before_save()
    # Retain the audit/accounting path of historic submitted and cancelled claims.
    if old and old.docstatus != 0:
        if doc.get("project") != old.get("project"):
            frappe.throw(_("The project on an existing expense claim cannot be changed."))
        return
    project = project_doc(doc.get("project"))
    if old and old.get("project") and old.project != project.name:
        frappe.throw(_("The project on an existing expense claim cannot be changed. Raise a separate claim from the correct project."))
    if project.status == "Cancelled":
        frappe.throw(_("Expenses cannot be raised against a cancelled project."))
    if doc.get("company") and doc.company != project.company:
        frappe.throw(_("The expense claim and project must belong to the same company."))
    doc.company = project.company
    if not doc.get("employee"):
        frappe.throw(_("An employee is required for this project expense claim."))
    employee = frappe.db.get_value("Employee", doc.employee, ["company", "user_id", "status"], as_dict=True)
    if not employee or employee.status != "Active" or employee.company != project.company:
        frappe.throw(_("Choose an active employee belonging to the project's company."))
    if not old and employee.user_id != frappe.session.user:
        frappe.throw(_("Create your own expense claim from the project you are working on."), frappe.PermissionError)
    if old and old.employee != doc.employee:
        frappe.throw(_("The employee on an existing expense claim cannot be changed."))
    manager, problem = manager_for(project)
    if problem:
        frappe.throw(problem)
    previous = (old.get("workflow_state") or "Draft") if old else "Draft"
    state = doc.get("workflow_state") or "Draft"
    if not old and (state != "Draft" or doc.docstatus != 0 or doc.get("approval_status") not in (None, "", "Draft")):
        frappe.throw(_("New project expenses must start as drafts and follow the existing approval process."))
    if previous == "Pending Approval" and state in ("Approved by the Manager", "Reject by the Manager"):
        if frappe.session.user != manager or employee.user_id == frappe.session.user:
            frappe.throw(_("Only the assigned Project Manager can review this claim. Self-approval is not allowed."), frappe.PermissionError)
    if state == "Pending Approval" and employee.user_id == manager:
        frappe.throw(_("You cannot approve your own expense. Ask the administrator to assign an independent Project Manager before sending this claim."))
    # Never trust a supplied approver or the employee's department-approver default.
    doc.expense_approver = manager
    if doc.get("task") and frappe.db.get_value("Task", doc.task, "project") != project.name:
        frappe.throw(_("The selected task must belong to this project."))
    for table in ("expenses", "taxes"):
        for row in doc.get(table) or []:
            if row.get("project") and row.project != project.name:
                frappe.throw(_("Every expense and tax row must belong to this project. Use a separate claim for another project."))
            row.project = project.name
    # Native workflow validation still checks allowed transitions/roles. Native HRMS on_update
    # shares with expense_approver; no new role, ignore_permissions, approval or payment bypass.

