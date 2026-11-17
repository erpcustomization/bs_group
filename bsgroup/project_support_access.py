"""Additive technical navigation access; retain existing record restrictions."""
import frappe

ROLE = "BS Project Support Viewer"
TECHNICAL_ROLES = {
    "BS Projects Manager",
    "Projects User", "Projects Manager", "Project Manager", "Project Engineer",
    "Technical Engineer", "Technician", "BS Assigned Project Reader", "BS Project Full Access",
}
REPORTS = ("Task Summary Report", "Task Scheduler Report", "Tech Task Scheduler Report")


def sync_user(doc, method=None):
    if not frappe.db.exists("Role", ROLE):
        return
    roles = {row.role for row in doc.roles}
    eligible = bool(doc.enabled and doc.user_type == "System User" and roles & TECHNICAL_ROLES)
    if eligible and ROLE not in roles:
        doc.append("roles", {"role": ROLE})
    elif not eligible and ROLE in roles:
        doc.set("roles", [row for row in doc.roles if row.role != ROLE])


def limited_scheduler(user=None):
    """Existing scheduler readers keep their access; new viewers see only their own."""
    user = user or frappe.session.user
    if user == "Administrator":
        return False
    roles = set(frappe.get_roles(user))
    if ROLE not in roles:
        return False
    return not any(p.role != ROLE and p.role in roles and p.read and not p.if_owner
                   for p in frappe.get_meta("Tech Task Scheduler").permissions)


def scheduler_query(user=None):
    if not limited_scheduler(user):
        return ""
    who = frappe.db.escape(user or frappe.session.user)
    # A form exposes every child row. Do not expose a mixed-recipient form;
    # the row-level report still shows this user's entries from that schedule.
    return ("EXISTS (SELECT 1 FROM `tabTech Task Scheduler List` s WHERE "
            "s.parent=`tabTech Task Scheduler`.name AND s.parenttype='Tech Task Scheduler' "
            f"AND s.resource={who}) AND NOT EXISTS (SELECT 1 FROM `tabTech Task Scheduler List` s "
            "WHERE s.parent=`tabTech Task Scheduler`.name AND s.parenttype='Tech Task Scheduler' "
            f"AND COALESCE(s.resource,'')!={who})")


def scheduler_permission(doc, user=None, permission_type=None, ptype=None):
    if not limited_scheduler(user):
        return None
    rows = doc.get("tech_task_scheduler_list") or []
    user = user or frappe.session.user
    if not rows or any(row.resource != user for row in rows):
        return False
    return None


def install():
    from frappe.permissions import setup_custom_perms
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)
    for dt, grants in (("Site Survey Request", {"read": 1, "select": 1}),
                       ("Tech Task Scheduler", {"read": 1, "select": 1, "report": 1}),
                       ("Task", {"report": 1})):
        setup_custom_perms(dt)
        if not frappe.db.exists("Custom DocPerm", {"parent": dt, "role": ROLE, "permlevel": 0}):
            frappe.get_doc(dict(doctype="Custom DocPerm", parent=dt, parenttype="DocType",
                                parentfield="permissions", role=ROLE, permlevel=0, **grants)).insert(ignore_permissions=True)
        frappe.clear_cache(doctype=dt)
    for name in REPORTS:
        if not frappe.db.exists("Report", name):
            continue
        report = frappe.get_doc("Report", name)
        if ROLE not in {r.role for r in report.roles}:
            report.append("roles", {"role": ROLE})
            report.save(ignore_permissions=True)
    for name in frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"}, pluck="name"):
        doc = frappe.get_doc("User", name)
        before = [r.role for r in doc.roles]
        sync_user(doc)
        if before != [r.role for r in doc.roles]:
            doc.save(ignore_permissions=True)
    frappe.clear_cache()
