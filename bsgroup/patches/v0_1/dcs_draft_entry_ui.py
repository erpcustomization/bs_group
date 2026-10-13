"""Keep customer and scope entry before the draft commercial summary."""
import frappe

def execute():
    frappe.reload_doc("bs_group","doctype","deal_cost_sheet")
    from bsgroup.patches.v0_1.dcs_ui import execute as apply_layout
    apply_layout()
