"""Apply the approved Compact CRM layout using supported DocType metadata."""
import json
import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

PRESENTATION_PROPERTIES = {
    "section_break_giph": ("label",),
    "section_break_jbpa": ("label",),
    "section_break_dsjr": ("label", "collapsible", "collapsible_depends_on"),
    "custom_deal_status_section": ("label",),
    "party_type": ("description",),
    "organisation_name": ("description",),
    "customer": ("description",),
    "custom_deal_status": ("description",),
    "get_data": ("label",),
    "apply_exclude_to_all_items": ("label",),
}

def set_presentation(field, prop, value, kind, for_doctype=False):
    filters={"doc_type":"Deal Cost Sheet","property":prop}
    if not for_doctype:
        filters["field_name"]=field
    existing=frappe.get_all("Property Setter",filters=filters,pluck="name")
    if existing:
        # Updating a value needs no delete/reinsert or background link cleanup.
        for name in existing:
            frappe.db.set_value("Property Setter",name,{"value":str(value),"property_type":kind})
    else:
        make_property_setter("Deal Cost Sheet",field,prop,value,kind,
            for_doctype=for_doctype,validate_fields_for_doctype=False)


RETIRED_CLIENT_SCRIPTS = {
    "Deal cost sheet - Theme - Highlights": "__liteThemeInstalled",
    "DCS Quick Add Items": "dcsQuickAddButton",
    "Deal Cost Sheet AI Assistant": "dcs_ai_run_full_check",
}


def execute():
    path=frappe.get_app_path("bsgroup","bs_group","doctype","deal_cost_sheet","deal_cost_sheet.json")
    with open(path) as source:
        definition=json.load(source)
    frappe.reload_doc("bs_group","doctype","deal_cost_sheet")
    # Explicit setters also override old site customisations of field order/labels.
    set_presentation(None,"field_order",json.dumps(definition["field_order"]),"Data",for_doctype=True)
    fields={field["fieldname"]:field for field in definition["fields"]}
    for name,properties in PRESENTATION_PROPERTIES.items():
        for prop in properties:
            value=fields[name].get(prop,"")
            kind="Check" if prop=="collapsible" else "Data"
            set_presentation(name,prop,value,kind)
    for name,marker in RETIRED_CLIENT_SCRIPTS.items():
        if not frappe.db.exists("Client Script",name):
            continue
        script=frappe.get_doc("Client Script",name)
        if script.dt != "Deal Cost Sheet" or marker not in (script.script or ""):
            frappe.throw("Review the changed legacy Client Script before retiring it: "+name)
        if script.enabled:
            script.enabled=0
            script.save(ignore_permissions=True)
            script.add_comment("Info","Retired by the approved Compact CRM layout. The app owns this behaviour; source is retained for rollback.")
    frappe.clear_cache(doctype="Deal Cost Sheet")
