"""Move the existing Subject field to the top of Costing; no business-data changes."""
import json
import frappe
from bsgroup.patches.v0_1.dcs_compact_crm import set_presentation


def execute():
    path = frappe.get_app_path("bsgroup", "bs_group", "doctype", "deal_cost_sheet", "deal_cost_sheet.json")
    with open(path) as source:
        definition = json.load(source)
    frappe.reload_doc("bs_group", "doctype", "deal_cost_sheet")
    set_presentation(None, "field_order", json.dumps(definition["field_order"]), "Data", for_doctype=True)
    frappe.clear_cache(doctype="Deal Cost Sheet")
