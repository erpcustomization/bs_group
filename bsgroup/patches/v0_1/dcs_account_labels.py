"""Clarify account selection without changing stored links or permissions."""
import frappe
from bsgroup.patches.v0_1.dcs_compact_crm import set_presentation


def execute():
    frappe.reload_doc("bs_group", "doctype", "deal_cost_sheet")
    for name, prop, value, kind in (
        ("party_type", "label", "Account Type", "Data"),
        ("party", "label", "Account", "Data"),
        ("customer", "hidden", 1, "Check"),
        ("organisation_name", "depends_on",
         "eval:doc.organisation_name && doc.organisation_name !== doc.party", "Data"),
    ):
        set_presentation(name, prop, value, kind)
    frappe.clear_cache(doctype="Deal Cost Sheet")
