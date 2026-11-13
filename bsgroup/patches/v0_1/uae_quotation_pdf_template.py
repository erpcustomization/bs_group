"""Remember the chosen PDF template for the UAE quotation workflow."""
import frappe


def execute():
    from bsgroup.oman_quotation_flow import uae, template_selection_enabled, PDF_TEMPLATE_FIELD
    if not uae() or not template_selection_enabled():
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Quotation": [dict(fieldname=PDF_TEMPLATE_FIELD,
        label="Last PDF Template", fieldtype="Data", insert_after="letter_head",
        read_only=1, hidden=1, print_hide=1, no_copy=1)]})
