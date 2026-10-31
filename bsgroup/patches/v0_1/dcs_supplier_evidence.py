"""Add multi-file supplier cost evidence in Costing, optional until submit."""
import json
import frappe
from bsgroup.patches.v0_1.dcs_compact_crm import set_presentation


def execute():
    frappe.reload_doc("bs_group", "doctype", "dcs_supplier_quotation")
    frappe.reload_doc("bs_group", "doctype", "deal_cost_sheet")
    order = [f.fieldname for f in frappe.get_meta("Deal Cost Sheet").fields]
    for field in ("supplier_quotation_section", "supplier_quotations"):
        if field in order:
            order.remove(field)
    index = order.index("section_break_jbpa")
    order[index:index] = ["supplier_quotation_section", "supplier_quotations"]
    set_presentation(None, "field_order", json.dumps(order), "Data", for_doctype=True)
    frappe.clear_cache(doctype="Deal Cost Sheet")