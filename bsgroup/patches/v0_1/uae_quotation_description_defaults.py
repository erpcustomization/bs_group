"""Use costing wording by default for new UAE quotation lines; preserve all rows."""
import frappe


def execute():
    from bsgroup.oman_quotation_flow import uae, enabled
    if not uae() or not enabled():
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
