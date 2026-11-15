"""Account-link selection for Mithun's native expense entry, without ledger access."""
import frappe

USER = "mithun@bitssecureit.com"
ROLE = "BS Expense Account Selector"
DENIED = ("read", "write", "create", "delete", "submit", "cancel", "amend",
          "report", "export", "import", "print", "email", "share")


def install():
    from bsgroup.hr_email import site_profile
    profile = site_profile()
    if not profile or profile["region"] != "UAE" or not frappe.db.get_value("User", USER, "enabled"):
        return
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc(dict(doctype="Role", role_name=ROLE, desk_access=1)).insert(ignore_permissions=True)
    # Copy native rules first: adding a custom rule must not replace other roles.
    from frappe.permissions import setup_custom_perms
    setup_custom_perms("Account")
    filters = dict(parent="Account", role=ROLE, permlevel=0, if_owner=0)
    name = frappe.db.get_value("Custom DocPerm", filters, "name")
    rule = frappe.get_doc("Custom DocPerm", name) if name else frappe.get_doc(dict(
        doctype="Custom DocPerm", parenttype="DocType", parentfield="permissions", **filters))
    rule.update({**{key: 0 for key in DENIED}, "select": 1})
    rule.save(ignore_permissions=True)
    user = frappe.get_doc("User", USER)
    if ROLE not in [row.role for row in user.roles]:
        user.append("roles", dict(role=ROLE))
        user.save(ignore_permissions=True)
    # Company and Employee User Permissions remain unchanged and still apply.
    frappe.clear_cache(doctype="Account")
    frappe.clear_cache(user=USER)
