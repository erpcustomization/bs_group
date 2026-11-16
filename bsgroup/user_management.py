"""User administration with narrowly scoped, native permission-checked edits."""
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
ADMIN_ROLE = "BS User Administrator"
PROTECTED_ROLES = {"System Manager", ADMIN_ROLE, "Administrator", "BS Procurement Approver"}


def delegated():
    return frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles()


def can_open():
    return frappe.session.user != "Guest" and bool({"System Manager", ADMIN_ROLE} & set(frappe.get_roles()))


def target_editable(doc):
    return not delegated() or (doc.name not in ("Administrator", "Guest", "mohan@bitssecureit.com", frappe.session.user)
        and not PROTECTED_ROLES.intersection(frappe.get_roles(doc.name)))


def check_target(doc, action="write"):
    if delegated():
        if action != "read" and not target_editable(doc):
            frappe.throw("Administrator, approval-owner and your own account are protected. Ask a System Manager.", frappe.PermissionError)
    else:
        doc.check_permission(action)


def save_target(doc):
    if delegated():
        doc.save(ignore_permissions=True)  # Only the allowlisted console changes reach this boundary.
    else:
        doc.save()


def require_manager():
    frappe.only_for(["System Manager", ADMIN_ROLE])
    if not delegated() and not frappe.has_permission("User", "read"):
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
    query = frappe.get_all if delegated() else frappe.get_list
    rows = query("User", filters=filters, or_filters=or_filters,
        fields=["name", "first_name", "full_name", "enabled", "user_type", "last_login"],
        order_by="first_name asc, name asc", limit_start=start, limit_page_length=101)
    return {"rows": rows[:100], "has_more": len(rows) > 100,
            "can_create": delegated() or bool(frappe.has_permission("User", "create"))}


@frappe.whitelist()
def details(user):
    require_manager()
    doc = frappe.get_doc("User", user)
    check_target(doc, "read")
    roles = sorted(set(frappe.get_roles(user)))
    result = {"name": doc.name, "first_name": doc.first_name,
        "middle_name": doc.get("middle_name"), "last_name": doc.get("last_name"),
        "modified": str(doc.get("modified") or ""),
        "assigned_roles": sorted({r.role for r in doc.get("roles", [])}),
        "full_name": doc.full_name, "enabled": doc.enabled, "user_type": doc.user_type,
        "last_login": doc.last_login, "roles": roles,
        "role_profiles": [r.role_profile for r in doc.get("role_profiles", [])],
        "role_profile": doc.get("role_profile_name"), "module_profile": doc.get("module_profile"),
        "blocked_modules": [r.module for r in doc.get("block_modules", [])],
        "can_write": target_editable(doc) if delegated() else bool(frappe.has_permission("User", "write", doc=doc)),
        "restrictions": [], "employees": [], "modules": [], "history": []}
    if frappe.has_permission("Employee", "read"):
        result["employees"] = frappe.get_list("Employee", filters={"user_id": user},
            fields=["name", "employee_name", "company", "department", "status"], limit_page_length=100)
    if frappe.has_permission("User Permission", "read"):
        result["restrictions"] = frappe.get_list("User Permission", filters={"user": user},
            fields=["name", "allow", "for_value", "applicable_for", "apply_to_all_doctypes"],
            limit_page_length=500)
    result["can_manage_restrictions"] = not delegated() and bool(frappe.has_permission("User Permission", "create"))
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
    from bsgroup.user_module_access import public_details
    result["module_access"] = public_details(doc)
    return result


@frappe.whitelist()
def search_roles(search=""):
    require_manager()
    if delegated():
        frappe.throw("Use the module permission controls; technical roles are managed by System Managers.", frappe.PermissionError)
    if not frappe.has_permission("User", "write"):
        frappe.throw(_("User write access is required."), frappe.PermissionError)
    term = str(search or "").strip()[:120]
    if not term:
        return []
    return frappe.get_list("Role", filters={"disabled": 0,
        "name": ["not in", ["All", "Guest", "Administrator", "Desk User"]]},
        or_filters=[["name", "like", "%" + term + "%"]],
        fields=["name"], order_by="name asc", limit_page_length=20)


@frappe.whitelist(methods=["POST"])
def save_account(user, expected_modified, changes):
    require_manager()
    changes = frappe.parse_json(changes) if isinstance(changes, str) else changes
    allowed = {"first_name", "middle_name", "last_name", "enabled", "user_type", "roles"}
    if not isinstance(changes, dict) or set(changes) - allowed:
        frappe.throw(_("Unsupported account change."))
    doc = frappe.get_doc("User", user)
    check_target(doc)
    if delegated() and "roles" in changes:
        frappe.throw("Use the reviewed module permission controls.", frappe.PermissionError)
    if str(doc.modified) != str(expected_modified):
        frappe.throw(_("This account was updated elsewhere. Refresh before saving."))
    if "first_name" in changes and not str(changes["first_name"] or "").strip():
        frappe.throw(_("First Name is required."))
    if "enabled" in changes and changes["enabled"] not in (0, 1):
        frappe.throw(_("Invalid account status."))
    if "user_type" in changes and changes["user_type"] not in ("System User", "Website User"):
        frappe.throw(_("Invalid account type."))
    if "roles" in changes:
        if doc.get("role_profiles") or doc.get("role_profile_name"):
            frappe.throw(_("This account's roles are controlled by its existing role profile."))
        roles = changes["roles"]
        if not isinstance(roles, list) or any(not isinstance(r, str) for r in roles):
            frappe.throw(_("Invalid roles."))
        current = {r.role for r in doc.get("roles", [])}
        for role in set(roles) - current:
            if role in ("All", "Guest", "Administrator", "Desk User") or not frappe.db.exists(
                    "Role", {"name": role, "disabled": 0}):
                frappe.throw(_("Choose an enabled assignable role."))
        doc.set("roles", [r for r in doc.get("roles", []) if r.role in roles])
        for role in sorted(set(roles) - current):
            doc.append("roles", {"role": role})
    for field, value in changes.items():
        if field != "roles":
            doc.set(field, value.strip() if isinstance(value, str) else value)
    # Native User validation, field permissions, hooks, versioning and concurrency remain in force.
    # Do not replace profiles, restrictions, sharing, passwords or unspecified account settings.
    if changes:
        save_target(doc)
    return {"name": doc.name, "modified": str(doc.modified)}


def install():
    # Create an empty capability role: no generic User/Role/permission editor grants.
    if not frappe.db.exists("Role", ADMIN_ROLE):
        frappe.get_doc(dict(doctype="Role", role_name=ADMIN_ROLE, desk_access=1)).insert(ignore_permissions=True)
    if not frappe.db.exists("Role Profile", ADMIN_ROLE):
        frappe.get_doc(dict(doctype="Role Profile", role_profile=ADMIN_ROLE,
            roles=[dict(role=ADMIN_ROLE)])).insert(ignore_permissions=True)
    frappe.reload_doc("bs_group", "page", "bs_user_management", force=True)
    from bsgroup.user_module_access import install as install_module_grants
    install_module_grants()
    install_app_icon()
    frappe.clear_cache()


@frappe.whitelist(methods=["POST"])
def create_account(email, first_name, last_name="", enabled=1):
    require_manager()
    from frappe.utils import validate_email_address
    email = str(email or "").strip().lower()
    first_name = str(first_name or "").strip()
    if not first_name:
        frappe.throw("First Name is required.")
    validate_email_address(email, throw=True)
    if enabled not in (0, 1, "0", "1"):
        frappe.throw("Invalid account status.")
    if frappe.db.exists("User", email):
        frappe.throw("An account already exists for this email.")
    if not delegated() and not frappe.has_permission("User", "create"):
        frappe.throw("User creation access is required.", frappe.PermissionError)
    doc = frappe.get_doc(dict(doctype="User", email=email, first_name=first_name,
        last_name=str(last_name or "").strip(), enabled=int(enabled), user_type="System User",
        send_welcome_email=0, roles=[dict(role="Employee")]))
    doc.insert(ignore_permissions=delegated())
    doc.add_comment("Info", "Created through BS User Management. Module access must be reviewed separately.")
    return dict(name=doc.name)


def install_app_icon():
    """Publish only the manager-restricted shortcut, never alter account roles."""
    import json
    from pathlib import Path
    values = json.loads(Path(frappe.get_app_path("bsgroup", "desktop_icon", "bs_user_management.json")).read_text(encoding="utf-8"))
    if frappe.db.exists("Desktop Icon", values["name"]):
        doc = frappe.get_doc("Desktop Icon", values["name"])
        doc.update({k: v for k, v in values.items() if k not in ("doctype", "name", "roles")})
        doc.set("roles", values["roles"])
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc(values).insert(ignore_permissions=True)
