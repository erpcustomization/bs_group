"""Remember the template used for each Oman quotation's most recent PDF."""
import frappe


def execute():
    from bsgroup.oman_quotation_flow import OMAN_SITES, template_selection_enabled, PDF_TEMPLATE_FIELD
    if getattr(frappe.local, "site", None) not in OMAN_SITES or not template_selection_enabled():
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Quotation": [dict(fieldname=PDF_TEMPLATE_FIELD,
        label="Last PDF Template", fieldtype="Data", insert_after="letter_head",
        read_only=1, hidden=1, print_hide=1, no_copy=1)]})
