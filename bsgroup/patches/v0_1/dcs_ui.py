"""Apply the five-tab presentation without changing fields or permissions."""
import json
import frappe

def execute():
    path = frappe.get_app_path("bsgroup", "bs_group", "doctype", "deal_cost_sheet", "deal_cost_sheet.json")
    with open(path) as source:
        definition = json.load(source)
    order = definition["field_order"]
    name = frappe.db.get_value("Property Setter", {"doc_type":"Deal Cost Sheet", "property":"field_order"}, "name")
    if name:
        frappe.db.set_value("Property Setter", name, "value", json.dumps(order))
    labels = ["addtional_charges","section_break_giph","section_break_dsjr","section_break_jbpa",
              "section_break_ozlr","summary_section","commercial_summary_html","commercial_totals_section",
              "custom_living_dcs_section","custom_approved_position_section"]
    for field in definition["fields"]:
        if field["fieldname"] in labels:
            name = frappe.db.get_value("Property Setter",
                {"doc_type":"Deal Cost Sheet","field_name":field["fieldname"],"property":"label"}, "name")
            if name:
                frappe.db.set_value("Property Setter", name, "value", field.get("label") or "")
    frappe.clear_cache(doctype="Deal Cost Sheet")

    # These two complete renderers are ported into the app's DCS controller JS.
    # Preserve their stored source; only one renderer should execute on refresh.
    for name in ["Deal Cost Sheet - Living DCS Experience", "Deal Cost Sheet Summary Dashboard"]:
        if frappe.db.exists("Client Script", name):
            script = frappe.get_doc("Client Script", name)
            if script.enabled:
                script.enabled = 0
                script.save(ignore_permissions=True)
                script.add_comment("Info", "Retired by the DCS five-tab UI migration. Source retained for rollback; the app controller owns this interface.")
    frappe.clear_cache(doctype="Deal Cost Sheet")
