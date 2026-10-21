"""Additive schema only; no changes to historical deals or quotations."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    frappe.reload_doc("bs_group","doctype","dcs_purchase_request")
    create_custom_fields({"Quotation":[
        {"fieldname":"custom_customer_po_section","label":"Customer PO & Procurement","fieldtype":"Section Break","insert_after":"custom_pipeline_stage","allow_on_submit":1},
        {"fieldname":"custom_customer_po_reference","label":"Customer PO Reference","fieldtype":"Data","insert_after":"custom_customer_po_section","allow_on_submit":1,
         "mandatory_depends_on":"eval:doc.custom_pipeline_stage == 'Won'"},
        {"fieldname":"custom_customer_po","label":"Customer PO","fieldtype":"Attach","insert_after":"custom_customer_po_reference","allow_on_submit":1,
         "mandatory_depends_on":"eval:doc.custom_pipeline_stage == 'Won'"},
        {"fieldname":"custom_purchase_request","label":"Purchase Request","fieldtype":"Link","options":"DCS Purchase Request","insert_after":"custom_customer_po","allow_on_submit":1,"read_only":1,"no_copy":1},
    ]},update=True)
    frappe.clear_cache(doctype="Quotation")
