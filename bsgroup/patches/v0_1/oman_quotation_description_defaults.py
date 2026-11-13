"""Default new Oman quotation rows to costing; preserve saved row choices."""
import frappe


def execute():
    from bsgroup.oman_quotation_flow import OMAN_SITES, enabled
    if getattr(frappe.local, "site", None) not in OMAN_SITES or not enabled():
        return
    for fieldname, default in (("custom_oman_use_costing_description", "1"),
                               ("custom_oman_use_co_description", "0")):
        name = "Quotation Item-" + fieldname
        if frappe.db.exists("Custom Field", name):
            field = frappe.get_doc("Custom Field", name)
            if str(field.default or "0") != default:
                field.default = default
                field.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Quotation Item")
