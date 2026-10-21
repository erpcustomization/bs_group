"""Require PO evidence for Won quotations and restore missing DCS metadata."""
import json
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    ensure_schema()
    repair_missing_links()


def ensure_schema():
    from bsgroup.patches.v0_1.dcs_procurement import execute as po_fields
    po_fields()
    create_custom_fields({"Quotation": [
        {"fieldname": "custom_deal_cost_sheet", "label": "Deal Cost Sheet",
         "fieldtype": "Link", "options": "Deal Cost Sheet", "read_only": 1,
         "allow_on_submit": 1, "no_copy": 1, "print_hide": 1,
         "insert_after": "custom_customer_po_section"},
    ]}, update=True)
    # A saved field-order override otherwise leaves new fields under Connections.
    fields = ["custom_customer_po_section", "custom_deal_cost_sheet",
              "custom_dcs_revision_reference", "custom_dcs_superseded_revision",
              "custom_customer_po_reference", "custom_customer_po",
              "custom_bsp_material_request", "custom_purchase_request"]
    for row in frappe.get_all("Property Setter", filters={"doc_type": "Quotation", "property": "field_order"}, fields=["name", "value"]):
        order = json.loads(row.value or "[]")
        if "custom_pipeline_stage" not in order:
            continue
        order = [f for f in order if f not in fields]
        at = order.index("custom_pipeline_stage") + 1
        order[at:at] = [f for f in fields if frappe.get_meta("Quotation").has_field(f)]
        frappe.db.set_value("Property Setter", row.name, "value", json.dumps(order))
    frappe.clear_cache(doctype="Quotation")


def repair_missing_links():
    """Recover only an unambiguous, exact matching reverse link; never reprice."""
    from bsgroup.dcs.quotation_control import validate_position
    from bsgroup.dcs.governance import record_governance_event
    results = {"repaired": [], "skipped": []}
    for row in frappe.get_all("Deal Cost Sheet", filters={"docstatus": 1,
            "custom_quotation": ["is", "set"]}, fields=["name", "custom_quotation"]):
        if not frappe.db.exists("Quotation", row.custom_quotation):
            continue
        q = frappe.get_doc("Quotation", row.custom_quotation, for_update=True)
        if q.get("custom_deal_cost_sheet") or q.docstatus == 2:
            continue
        candidates = frappe.get_all("Deal Cost Sheet", filters={"docstatus": 1,
            "custom_quotation": q.name}, pluck="name")
        if len(candidates) != 1:
            results["skipped"].append(q.name)
            continue
        sheet = frappe.get_doc("Deal Cost Sheet", row.name, for_update=True)
        try:
            validate_position(sheet, q)
        except frappe.ValidationError:
            results["skipped"].append(q.name)
            continue
        values = {"custom_deal_cost_sheet": sheet.name,
                  "custom_dcs_revision_reference": sheet.custom_revision_reference}
        changes = [{"dt": "Quotation", "dn": q.name, "field": k,
                    "old": q.get(k), "new": v} for k, v in values.items()]
        frappe.db.set_value("Quotation", q.name, values)
        record_governance_event(sheet.name, "DCS_QUOTATION_LINK_RECOVERED",
            action_label="Restore matching quotation DCS link", source_endpoint="quotation_won_requirements",
            reason="Recovered from the unique current DCS quotation reference after validating identity, revision and all item quantities/rates. Status and commercial amounts were not changed.",
            revision_no=sheet.custom_dcs_revision_no, revision_reference=sheet.custom_revision_reference,
            changes=changes)
        results["repaired"].append(q.name)
    return results
