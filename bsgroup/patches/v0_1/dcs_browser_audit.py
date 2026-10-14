"""Repair DCS browser-test schema and management cards without editing deal history."""
import json
import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import COPY_RESET_FIELDS

def execute():
    frappe.reload_doc("bs_group", "doctype", "deal_cost_sheet")
    frappe.reload_doc("bs_group", "doctype", "deal_cost_resource")
    make_property_setter("Deal Cost Sheet", "organisation_name", "reqd", 0, "Check", validate_fields_for_doctype=False)
    for field in COPY_RESET_FIELDS:
        if frappe.get_meta("Deal Cost Sheet").get_field(field):
            make_property_setter("Deal Cost Sheet", field, "no_copy", 1, "Check", validate_fields_for_doctype=False)
    repair_cards()
    frappe.clear_cache(doctype="Deal Cost Sheet")

def repair_cards():
    for name in ("Open DCS Handover Blockers", "DCS Awarded Pending Delivery Release", "DCS PO Reconciliation Mismatch"):
        if not frappe.db.exists("Number Card", name):
            continue
        card = frappe.get_doc("Number Card", name)
        dt = card.document_type
        filters = []
        for row in json.loads(card.filters_json or "[]"):
            row = ([dt] + row) if len(row) == 3 else row
            # Preserve business criteria; replace incomplete test exclusions and draft eligibility.
            if row[1] == "docstatus" or (row[2].lower() == "not like" and "ZZ" in str(row[3]).upper()):
                continue
            filters.append(row)
        if dt == "Deal Cost Sheet":
            filters.append([dt, "docstatus", "=", 1])
            key = "name"
        else:
            key = "dcs"
        filters.extend([[dt, key, "not like", "%ZZTEST%"], [dt, key, "not like", "%ZZ-TEST%"]])
        card.filters_json = json.dumps(filters)
        card.save(ignore_permissions=True)
    for name in frappe.get_all("Number Card", filters={"document_type":"Deal Cost Sheet"}, pluck="name"):
        card=frappe.get_doc("Number Card", name)
        filters=json.loads(card.filters_json or "[]")
        if any("Endorsed - Pending MD" in str(row) or "Endorsed – Pending MD" in str(row) for row in filters):
            card.label="DCS Pending Manager Approval"
            card.filters_json=json.dumps([
                ["Deal Cost Sheet","docstatus","=",1],
                ["Deal Cost Sheet","custom_approval_state","=","Pending Manager"],
                ["Deal Cost Sheet","name","not like","%ZZTEST%"],
                ["Deal Cost Sheet","name","not like","%ZZ-TEST%"],
            ])
            card.save(ignore_permissions=True)
