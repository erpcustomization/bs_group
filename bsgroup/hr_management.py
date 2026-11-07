"""HR management navigation and summaries, using existing document permissions.

No endpoint approves leave, changes attendance, issues warnings or offboards staff.
"""
import frappe
from frappe.utils import nowdate

HR_ROLES = {"HR User", "HR Manager", "System Manager"}
SECTIONS = (
    ("employees", "Employee Profiles", "Employee", "employee_name", "status", {"status": "Active"}),
    ("onboarding", "Onboarding", "Employee Onboarding", "employee_name", "boarding_status", {"docstatus": ["!=", 2]}),
    ("attendance", "Attendance", "Employee Checkin", "employee_name", "log_type", {}),
    ("leave", "Leave Approvals", "Leave Application", "employee_name", "status", {"status": "Open", "docstatus": ["!=", 2]}),
    ("policies", "Policies", "Organization Document", "document_title", "approval_status", {}),
    ("warnings", "Warnings", "HR Warning", "subject", "status", {}),
    ("exit", "Exit Interviews", "Exit Interview", "employee_name", "status", {"docstatus": ["!=", 2]}),
    ("offboarding", "Offboarding", "Employee Separation", "employee_name", "boarding_status", {"docstatus": ["!=", 2]}),
    ("requests", "HR Requests", "HR Service Request", "subject", "status", {}),
)


def _guard():
    if frappe.session.user == "Guest" or not HR_ROLES.intersection(frappe.get_roles()):
        frappe.throw("HR Management is available to existing HR administrators only.", frappe.PermissionError)


def _section(spec):
    key, label, dt, title, status, filters = spec
    result = dict(key=key, label=label, doctype=dt, available=False, rows=[], count=None)
    if not frappe.db.exists("DocType", dt):
        result["reason"] = "Setup pending"
        return result
    if not frappe.has_permission(dt, "read"):
        result["reason"] = "Restricted by your existing access"
        return result
    meta = frappe.get_meta(dt)
    fields = ["name", "modified", "docstatus"]
    for field in (title, status, "employee", "company", "time", "from_date", "to_date"):
        if meta.has_field(field) and field not in fields:
            fields.append(field)
    filters = dict(filters)
    if key == "attendance":
        filters["time"] = ["between", [nowdate() + " 00:00:00", nowdate() + " 23:59:59"]]
    # Native list permission filters apply to both totals and returned records.
    count = frappe.get_list(dt, filters=filters, fields=[{"COUNT": "name", "as": "total"}])[0].total
    rows = frappe.get_list(dt, filters=filters, fields=fields,
                           order_by="modified desc", limit_page_length=10)
    result.update(available=True, count=count, can_create=frappe.has_permission(dt, "create"),
                  filters=filters, title_field=title, status_field=status, rows=rows)
    return result


@frappe.whitelist()
def overview():
    _guard()
    sections = [_section(spec) for spec in SECTIONS]
    return dict(date=nowdate(), sections=sections,
                can_setup="System Manager" in frappe.get_roles(),
                setup_pending=any(s.get("reason") == "Setup pending" and s["key"] in ("warnings", "requests") for s in sections))


@frappe.whitelist()
def organization():
    """Read the recorded reporting lines without exposing inaccessible managers."""
    _guard()
    if not frappe.has_permission("Employee", "read"):
        frappe.throw("Employee records are restricted by your existing access.", frappe.PermissionError)
    rows = frappe.get_list("Employee", filters={"status": "Active"},
                           fields=["name", "employee_name", "designation", "department", "company", "reports_to"],
                           order_by="employee_name asc", limit_page_length=0)
    visible = {row.name for row in rows}
    for row in rows:
        row["manager_outside_view"] = bool(row.get("reports_to") and row.reports_to not in visible)
        if row["manager_outside_view"]:
            row["reports_to"] = None
    return dict(employees=rows)


@frappe.whitelist(methods=["POST"])
def setup_registers():
    """Install new empty registers. No user roles or existing permissions change."""
    frappe.only_for("System Manager")
    for name in ("hr_warning", "hr_service_request"):
        # Never overwrite a site's existing/custom record definition.
        dt = "HR Warning" if name == "hr_warning" else "HR Service Request"
        if not frappe.db.exists("DocType", dt):
            frappe.reload_doc("bs_group", "doctype", name, force=True)
    return dict(installed=True)
