"""Additive schema for DCS quotation source mapping, plus server-owned legacy evidence.

Quotations already submitted (docstatus 1) and linked to a DCS without any row
mapping when this patch runs are recorded in ``custom_dcs_legacy_basis``. Only
those records keep the pre-mapping Sales Order rule; nothing else (drafts, copies,
amendments, new quotations, or a mapping removed later) can obtain it. Figures,
statuses and lines of existing records are not changed.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import now

LEGACY_BASIS = "Submitted before DCS row mapping; recorded by migration on {0}"


def execute():
    for doctype in ("deal_cost_item", "additional_charges_item"):
        frappe.reload_doc("bs_group", "doctype", doctype)
    create_custom_fields({
        "Quotation Item": [
            {"fieldname": "custom_dcs_source_rows", "label": "DCS Source Rows", "fieldtype": "Small Text",
             "insert_after": "custom_selling_rate", "read_only": 1, "print_hide": 1, "report_hide": 1,
             "description": "DCS rows presented by this line. Set at generation or with Map DCS Rows; validated by the server."},
        ],
        "Quotation": [
            {"fieldname": "custom_dcs_alignment", "label": "DCS Alignment", "fieldtype": "Data",
             "insert_after": "custom_dcs_superseded_revision", "read_only": 1, "print_hide": 1, "no_copy": 1,
             "description": "Server-derived difference from the current DCS position, recorded at the last draft save."},
            {"fieldname": "custom_dcs_legacy_basis", "label": "DCS Legacy Basis", "fieldtype": "Data",
             "insert_after": "custom_dcs_alignment", "read_only": 1, "print_hide": 1, "no_copy": 1, "hidden": 1,
             "description": "Set only by migration for quotations submitted before DCS row mapping."},
        ],
    }, update=True)
    frappe.clear_cache(doctype="Quotation")
    mark_legacy_evidence()


def mark_legacy_evidence():
    """Idempotent: marks only submitted, DCS-linked, wholly unmapped quotations that are not yet marked."""
    # Customisations (custom/*.json) sync after patches: on a fresh site these columns do not exist
    # yet, and then no DCS-linked quotation can exist either.
    for doctype, column in (("Quotation", "custom_deal_cost_sheet"), ("Quotation", "custom_dcs_legacy_basis"),
            ("Quotation Item", "custom_dcs_source_rows")):
        if not frappe.db.has_column(doctype, column):
            return []
    names = frappe.db.sql_list("""
        SELECT q.name FROM `tabQuotation` q
        WHERE q.docstatus = 1 AND IFNULL(q.custom_deal_cost_sheet, '') != ''
          AND IFNULL(q.custom_dcs_legacy_basis, '') = ''
          AND NOT EXISTS (SELECT 1 FROM `tabQuotation Item` i WHERE i.parent = q.name
                          AND i.parenttype = 'Quotation' AND IFNULL(i.custom_dcs_source_rows, '') != '')""")
    basis = LEGACY_BASIS.format(now())
    for name in names:
        frappe.db.set_value("Quotation", name, "custom_dcs_legacy_basis", basis, update_modified=False)
    return names
