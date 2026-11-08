"""HR management navigation and summaries, using existing document permissions.

No endpoint approves leave, changes attendance, issues warnings or offboards staff.
"""
import frappe
from frappe.utils import nowdate

HR_ROLES = {"HR User", "HR Manager", "System Manager"}
HR_ACCESS_ROLE = "BS HR Management"
HR_ACCESS_USER = "muskan@bitssecureit.com"
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


def can_manage():
    return frappe.session.user != "Guest" and (
        frappe.session.user in ("Administrator", HR_ACCESS_USER) or "System Manager" in frappe.get_roles())


def _guard():
    if not can_manage():
        frappe.throw("BS HR is available to Muskan and system administrators.", frappe.PermissionError)


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
        row["can_edit"] = frappe.has_permission("Employee", "write", doc=row.name)
        row["manager_outside_view"] = bool(row.get("reports_to") and row.reports_to not in visible)
        if row["manager_outside_view"]:
            row["reports_to"] = None
    return dict(employees=rows, can_create=frappe.has_permission("Employee", "create"),
                can_create_team=frappe.has_permission("Department", "create"),
                can_read_teams=frappe.has_permission("Department", "read"))


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


ACCESS_ADDITIONS = {
    "HR Warning": {"read": 1, "write": 1, "create": 1, "report": 1},
    "HR Service Request": {"read": 1, "write": 1, "create": 1, "report": 1},
    "Organization Document": {"read": 1, "write": 1, "create": 1, "report": 1},
    "Organization Document Category": {"read": 1, "select": 1},
}


@frappe.whitelist()
def muskan_access_review():
    frappe.only_for("System Manager")
    user = frappe.get_doc("User", HR_ACCESS_USER)
    return dict(user=user.name, full_name=user.full_name, roles=frappe.get_roles(user.name),
                additions=ACCESS_ADDITIONS,
                current=[dict(doctype=s[2], read=frappe.has_permission(s[2], "read", user=user.name),
                              write=frappe.has_permission(s[2], "write", user=user.name),
                              create=frappe.has_permission(s[2], "create", user=user.name)) for s in SECTIONS])


@frappe.whitelist(methods=["POST"])
def grant_muskan_access():
    """Explicit administrator action, called only after access confirmation."""
    frappe.only_for("System Manager")
    from frappe.permissions import setup_custom_perms
    user = frappe.get_doc("User", HR_ACCESS_USER)
    if not user.enabled:
        frappe.throw("Muskan's account is disabled. No access changes were made.")
    other_holders = frappe.get_all("Has Role", filters={"role": HR_ACCESS_ROLE, "parenttype": "User"}, pluck="parent")
    if any(u != HR_ACCESS_USER and "System Manager" not in frappe.get_roles(u) for u in other_holders):
        frappe.throw("The BS HR Management role is already used by another account. Review its scope before granting access.")
    if not frappe.db.exists("Role", HR_ACCESS_ROLE):
        frappe.get_doc(dict(doctype="Role", role_name=HR_ACCESS_ROLE, desk_access=1)).insert()
    for dt, values in ACCESS_ADDITIONS.items():
        setup_custom_perms(dt)
        name = frappe.db.get_value("Custom DocPerm", {"parent": dt, "role": HR_ACCESS_ROLE, "permlevel": 0, "if_owner": 0})
        rule = frappe.get_doc("Custom DocPerm", name) if name else frappe.get_doc(dict(
            doctype="Custom DocPerm", parent=dt, parenttype="DocType", parentfield="permissions",
            role=HR_ACCESS_ROLE, permlevel=0, if_owner=0))
        rule.update(values)
        rule.save()
        frappe.clear_cache(doctype=dt)
    if not frappe.db.exists("Role Profile", HR_ACCESS_ROLE):
        frappe.get_doc(dict(doctype="Role Profile", role_profile=HR_ACCESS_ROLE,
                            roles=[dict(role=HR_ACCESS_ROLE)])).insert()
    else:
        profile = frappe.get_doc("Role Profile", HR_ACCESS_ROLE)
        if {r.role for r in profile.roles} != {HR_ACCESS_ROLE}:
            frappe.throw("The BS HR Management profile has unexpected roles. Review it before proceeding.")
    # Preserve the existing HR profile and every existing role.
    if user.meta.has_field("role_profiles") and user.get("role_profiles"):
        if not any(r.role_profile == HR_ACCESS_ROLE for r in user.role_profiles):
            user.append("role_profiles", {"role_profile": HR_ACCESS_ROLE})
    elif not any(r.role == HR_ACCESS_ROLE for r in user.roles):
        user.append("roles", {"role": HR_ACCESS_ROLE})
    user.save()
    user.add_comment("Info", "BS HR Management access added for confidential HR registers and organization policies. Existing HR roles, company restrictions and approvals retained.")
    frappe.clear_cache(user=user.name)
    return {"user": user.name, "role": HR_ACCESS_ROLE}
