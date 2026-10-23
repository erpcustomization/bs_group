"""Additive schema for DCS quotation source mapping. Existing records are not rewritten.

Legacy quotations keep an empty mapping and are judged by the pre-mapping rule,
so no historical draft or submitted quotation is invalidated by this patch.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    for doctype in ("deal_cost_item", "additional_charges_item"):
        frappe.reload_doc("bs_group", "doctype", doctype)
    create_custom_fields({
        "Quotation Item": [
            {"fieldname": "custom_dcs_source_rows", "label": "DCS Source Rows", "fieldtype": "Small Text",
             "insert_after": "custom_selling_rate", "read_only": 1, "print_hide": 1, "report_hide": 1,
             "in_list_view": 0,
             "description": "DCS rows presented by this line. Set at generation or with Map DCS Rows; validated by the server."},
        ],
        "Quotation": [
            {"fieldname": "custom_dcs_alignment", "label": "DCS Alignment", "fieldtype": "Data",
             "insert_after": "custom_dcs_superseded_revision", "read_only": 1, "print_hide": 1, "no_copy": 1,
             "description": "Server-derived difference from the current DCS position, recorded at the last draft save."},
        ],
    }, update=True)
    frappe.clear_cache(doctype="Quotation")
