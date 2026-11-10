"""Project-owned activity navigation; native record permissions and workflows apply."""
import json
from importlib.util import find_spec
import frappe
from frappe import _


SECTIONS = {
    "tasks": ("Tasks", "Task", "project"),
    "timesheets": ("Timesheets", "Timesheet", None),
    "scheduler": ("Tech Task Scheduler", "Tech Task Scheduler", None),
    "expenses": ("Expenses", "Expense Claim", "project"),
    "advances": ("Advance", "Employee Advance", "custom_project"),
    "labor": ("Labour Approval", "Labor Preapproval", "reference"),
}
MODULE_TITLES = {"BS Supply Projects", "BS ELV Projects", "BS Infra Projects", "BS 3CX Projects"}


def install():
    """Add an activity tab and remove only the old generic project navigation."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    meta = frappe.get_meta("Project")
    definitions = [
        dict(fieldname="custom_bs_project_activities", label="Project Activities", fieldtype="Tab Break",
             insert_after=meta.fields[-1].fieldname),
        dict(fieldname="custom_bs_project_workspace", label="Project Activities", fieldtype="HTML",
             insert_after="custom_bs_project_activities"),
    ]
    missing = []
    for definition in definitions:
        existing = meta.get_field(definition["fieldname"])
        if existing and existing.fieldtype != definition["fieldtype"]:
            frappe.throw(_("Project activity field has an incompatible type: {0}").format(definition["fieldname"]))
        if not existing:
            missing.append(definition)
    if missing:
        create_custom_fields({"Project": missing}, update=False)
    if frappe.db.exists("DocType", "Sidebar") and frappe.db.exists("Sidebar", "BS Group"):
        sidebar = frappe.get_doc("Sidebar", "BS Group")
        retained, group = [], None
        for row in sidebar.items:
            if row.type == "Section Break":
                group = row.label
            remove = False
            if group in MODULE_TITLES and row.type == "Link" and row.link_to == "bs-project-modules":
                try:
                    options = json.loads(row.route_options or "{}")
                except (ValueError, TypeError):
                    options = {}
                remove = options.get("bs_section") in SECTIONS
            if group == "BS Project" and row.type == "Link" and row.link_type == "DocType":
                remove = row.link_to in {"Task", "Timesheet", "Tech Task Scheduler"}
            if not remove:
                retained.append(row)
        if len(retained) != len(sidebar.items):
            sidebar.set("items", retained)
            previous = frappe.flags.in_migrate
            try:
                frappe.flags.in_migrate = True
                sidebar.save()
            finally:
                frappe.flags.in_migrate = previous
    frappe.clear_cache(doctype="Project")
    frappe.clear_cache()
    return {"installed": True}


@frappe.whitelist(methods=["POST"])
def setup():
    frappe.only_for("System Manager")
    return install()


def own_employee(company):
    rows = frappe.get_all("Employee", filters={"user_id": frappe.session.user, "status": "Active", "company": company},
                          fields=["name"], limit_page_length=2)
    return rows[0].name if len(rows) == 1 else None


@frappe.whitelist()
def context(project, section="tasks"):
    if section not in SECTIONS:
        frappe.throw(_("Choose a valid project activity."))
    if not project:
        frappe.throw(_("Open a project first."))
    doc = frappe.get_doc("Project", project)
    doc.check_permission("read")
    title, doctype, field = SECTIONS[section]
    result = dict(project=doc.name, project_name=doc.project_name, company=doc.company, title=title,
                  doctype=doctype, rows=[], available=False, can_create=False, defaults={}, child=None, problem=None)
    if not frappe.db.exists("DocType", doctype):
        result["problem"] = _("This activity is not installed on this site.")
        return result
    meta = frappe.get_meta(doctype)
    if field and not meta.has_field(field):
        result["problem"] = _("The project link for this activity has not been configured.")
        return result
    result["available"] = bool(frappe.has_permission(doctype, "read"))
    result["can_create"] = bool(frappe.has_permission(doctype, "create") and doc.status != "Cancelled")
    result["defaults"] = {field: doc.name} if field else {}
    if meta.has_field("company"):
        result["defaults"]["company"] = doc.company
    filters = {field: doc.name} if field else []
    if section == "labor":
        filters["source"] = "Project"
        result["defaults"].update(source="Project", cost_center=doc.get("cost_center") or frappe.db.get_value("Company", doc.company, "cost_center"))
    elif section == "timesheets":
        filters = [["Timesheet Detail", "project", "=", doc.name]]
        result["child"] = dict(field="time_logs", values={"project": doc.name})
    elif section == "scheduler":
        filters = [["Tech Task Scheduler List", "project", "=", doc.name]]
        result["child"] = dict(field="tech_task_scheduler_list", values={"project": doc.name, "category": "Project",
                                  "category_doctype": "Project", "category_name": doc.name})
    if section in {"expenses", "advances", "timesheets"}:
        employee = own_employee(doc.company)
        if employee:
            result["defaults"]["employee"] = employee
        if section in {"expenses", "advances"} and not employee:
            result.update(can_create=False, problem=_("Your login must be linked to one active Employee in this project's company to create a request."))

    # Reuse the existing site's stronger project request controls where deployed.
    controlled = None
    if section in {"expenses", "advances", "labor"}:
        module = "bsgroup.project_expenses" if section == "expenses" else "bsgroup.project_requests"
        if find_spec(module) is not None:
            handler = frappe.get_attr(module + ".context")
            controlled = handler(project) if section == "expenses" else handler(project, "advance" if section == "advances" else "labor")
    if controlled is not None:
        result.update(can_create=controlled["can_create"], problem=controlled.get("problem"))
        if section == "expenses":
            result["defaults"].update(employee=controlled["employee"], expense_approver=controlled["expense_approver"])
            result["rows"] = controlled["claims"]
        else:
            result["defaults"] = controlled["defaults"]
            result["rows"] = controlled["records"]
    elif result["available"]:
        fields = ["name", "modified", "docstatus"] + [name for name in
                  ("subject", "employee_name", "status", "workflow_state", "task") if meta.has_field(name)]
        result["rows"] = frappe.get_list(doctype, filters=filters, fields=fields, distinct=True,
                                        order_by="creation desc", limit_page_length=100)
    return result
