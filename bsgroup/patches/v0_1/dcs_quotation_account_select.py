"""Let Sales Manager select account links required by standard quotation validation."""
import frappe


def execute():
    # Preserve existing site overrides. Explicit zeros prevent Custom DocPerm
    # defaults from accidentally granting document read access on a new rule.
    frappe.permissions.setup_custom_perms("Account")
    filters = {"parent": "Account", "role": "Sales Manager", "permlevel": 0, "if_owner": 0}
    name = frappe.db.get_value("Custom DocPerm", filters, "name")
    if name:
        frappe.db.set_value("Custom DocPerm", name, "select", 1)
    else:
        values = {key: 0 for key in ("read", "write", "create", "delete", "submit", "cancel",
                  "amend", "report", "export", "import", "print", "email", "share")}
        frappe.get_doc({"doctype": "Custom DocPerm", "parenttype": "DocType",
            "parentfield": "permissions", **filters, **values, "select": 1}).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Account")
