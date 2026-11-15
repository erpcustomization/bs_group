"""Read-only administration overview. All edits use native permission-checked forms."""
import frappe
from frappe import _

MODULES = {
    "Sales": ["Lead", "Opportunity", "Deal Cost Sheet", "Quotation"],
    "Projects": ["Project", "Task", "Timesheet", "Delivery Request"],
    "Procurement": ["Material Request", "Purchase Order"],
    "HR": ["Employee", "Leave Application", "Employee Checkin"],
    "Helpdesk": ["HD Ticket", "Issue"],
}
ACTIONS = ("read", "create", "write", "submit", "cancel", "share")


def require_manager():
    frappe.only_for("System Manager")
    if not frappe.has_permission("User", "read"):
        frappe.throw(_("User administration access is required."), frappe.PermissionError)


@frappe.whitelist()
def directory(search="", state="all", kind="all", start=0):
    require_manager()
    start = max(0, min(int(start or 0), 100000))
    filters = {"name": ["not in", ["Guest"]]}
    if state in ("active", "disabled"):
        filters["enabled"] = int(state == "active")
    if kind in ("System User", "Website User"):
        filters["user_type"] = kind
    term = str(search or "").strip()[:120]
    or_filters = [["User", f, "like", "%" + term + "%"]
                  for f in ("name", "first_name", "full_name")] if term else None
    rows = frappe.get_list("User", filters=filters, or_filters=or_filters,
        fields=["name", "first_name", "full_name", "enabled", "user_type", "last_login"],
        order_by="first_name asc, name asc", limit_start=start, limit_page_length=101)
    return {"rows": rows[:100], "has_more": len(rows) > 100,
            "can_create": bool(frappe.has_permission("User", "create"))}


@frappe.whitelist()
def details(user):
    require_manager()
    doc = frappe.get_doc("User", user)
    doc.check_permission("read")
    roles = sorted(set(frappe.get_roles(user)))
    result = {"name": doc.name, "first_name": doc.first_name,
        "full_name": doc.full_name, "enabled": doc.enabled, "user_type": doc.user_type,
        "last_login": doc.last_login, "roles": roles,
        "role_profiles": [r.role_profile for r in doc.get("role_profiles", [])],
        "role_profile": doc.get("role_profile_name"), "module_profile": doc.get("module_profile"),
        "blocked_modules": [r.module for r in doc.get("block_modules", [])],
        "can_write": bool(frappe.has_permission("User", "write", doc=doc)),
        "restrictions": [], "employees": [], "modules": [], "history": []}
    if frappe.has_permission("Employee", "read"):
        result["employees"] = frappe.get_list("Employee", filters={"user_id": user},
            fields=["name", "employee_name", "company", "department", "status"], limit_page_length=100)
    if frappe.has_permission("User Permission", "read"):
        result["restrictions"] = frappe.get_list("User Permission", filters={"user": user},
            fields=["name", "allow", "for_value", "applicable_for", "apply_to_all_doctypes"],
            limit_page_length=500)
    result["can_manage_restrictions"] = bool(frappe.has_permission("User Permission", "create"))
    # Deliberately show role grants, not an assertion that every record is accessible.
    # Owner conditions, field permission levels, hooks, shares and user permissions still apply.
    for title, doctypes in MODULES.items():
        rows = []
        for dt in doctypes:
            if not frappe.db.exists("DocType", dt):
                continue
            rules = [p for p in frappe.get_meta(dt).permissions if p.role in roles]
            rows.append({"doctype": dt, "actions": {a: any(p.get(a) and not p.permlevel for p in rules)
                         or user == "Administrator" for a in ACTIONS},
                         "owner_only": any(p.if_owner for p in rules)})
        result["modules"].append({"title": title, "rows": rows})
    if frappe.has_permission("Version", "read"):
        result["history"] = frappe.get_list("Version", filters={"ref_doctype": "User", "docname": user},
            fields=["name", "owner", "creation"], order_by="creation desc", limit_page_length=20)
    return result


def install():
    # No User, Has Role, User Permission, DocShare or Role records are changed here.
    frappe.reload_doc("bs_group", "page", "bs_user_management", force=True)
    frappe.clear_cache()
