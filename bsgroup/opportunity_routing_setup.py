"""Independent survey and presales choices, preserving existing routing."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from bsgroup.site_survey import DEFERRED_FIELDS


@frappe.whitelist()
def execute():
    frappe.only_for("System Manager")
    routed = "eval:['Service','Supply and Installation'].includes(doc.custom_business_type)"
    create_custom_fields({"Opportunity": [dict(fieldname="custom_presales_support",
        label="Presales Support Required", fieldtype="Select", options="\nYes\nNo",
        insert_after="custom_service_survey", depends_on=routed, mandatory_depends_on=routed)]}, update=True)
    def set_property(doctype, field, key, value, kind="Data"):
        existing = frappe.db.get_value("Property Setter", {"doc_type": doctype, "field_name": field, "property": key}, "name")
        if existing:
            frappe.db.set_value("Property Setter", existing, {"value": str(value), "property_type": kind})
        else:
            make_property_setter(doctype, field, key, value, kind)
    def prop(field, key, value, kind="Data"):
        set_property("Opportunity", field, key, value, kind)
    for key in ("depends_on", "mandatory_depends_on"):
        prop("custom_service_survey", key, routed)
    prop("custom_service_survey", "insert_after", "custom_camera_count")
    for field in ("custom_presales_required", "custom_elv_site_survey_required", "custom_technical_site_survey_required", "custom_site_survey_needed"):
        prop(field, "hidden", 1, "Check")
        prop(field, "reqd", 0, "Check")
        prop(field, "mandatory_depends_on", "")
    for field, step in (("custom_survey_instructions", 0), ("custom_survey_location", 1), ("custom_survey_contact_name", 2), ("custom_survey_contact_phone", 2)):
        prop(field, "depends_on", "eval:(doc.custom_elv_site_survey_required || doc.custom_technical_site_survey_required)" + (f" && doc.custom_survey_step >= {step}" if step else ""))
    for field in DEFERRED_FIELDS:
        set_property("Presales Request", field, "reqd", 0, "Check")
        set_property("Presales Request", field, "mandatory_depends_on",
            "eval:doc.status !== 'Draft' && (!doc.custom_site_survey_request || !['Awaiting Site Survey Results','Site Survey Results Received','Cancelled','On Hold'].includes(doc.status))", "Data")
    # Preserve historical decisions without dispatching new work during migration.
    for row in frappe.get_all("Opportunity", fields=["name", "custom_business_type", "custom_presales_support", "custom_presales_required", "custom_service_survey", "custom_elv_site_survey_required", "custom_technical_site_survey_required"]):
        values = {}
        if not row.custom_presales_support:
            values["custom_presales_support"] = "Yes" if row.custom_presales_required else "No"
        if row.custom_business_type == "Supply and Installation" and not row.custom_service_survey:
            values["custom_service_survey"] = "Site Survey by ELV" if row.custom_elv_site_survey_required else "Site Survey by Technical Team" if row.custom_technical_site_survey_required else "No Site Survey Required"
        if values:
            frappe.db.set_value("Opportunity", row.name, values, update_modified=False)
    frappe.clear_cache(doctype="Opportunity")
    frappe.clear_cache(doctype="Presales Request")
    return "Independent survey and presales choices configured"
