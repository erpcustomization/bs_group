"""Idempotent, additive schema and navigation for survey intake."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from bsgroup.site_survey import WAITING, RECEIVED, DEFERRED_FIELDS


@frappe.whitelist(methods=["POST"])
def execute():
    frappe.only_for("System Manager")
    frappe.reload_doc("bs_group", "doctype", "site_survey_request", force=True)
    create_custom_fields({
        "Opportunity": [
            dict(fieldname="custom_business_type", label="Supply / Service", fieldtype="Select", options="\nSupply\nService\nSupply and Installation", insert_after="sales_stage", mandatory_depends_on="eval:doc.__islocal || doc.custom_business_type"),
            dict(fieldname="custom_service_type", label="Service Type", fieldtype="Select", options="\nAMC\nNew Service Opportunity", insert_after="custom_business_type", depends_on="eval:doc.custom_business_type === 'Service'", mandatory_depends_on="eval:doc.custom_business_type === 'Service'"),
            dict(fieldname="custom_installation_type", label="Installation Type", fieldtype="Select", options="\nCCTV\n3CX\nNetworking\nOther", insert_after="custom_service_type", depends_on="eval:doc.custom_business_type === 'Supply and Installation'", mandatory_depends_on="eval:doc.custom_business_type === 'Supply and Installation'"),
            dict(fieldname="custom_camera_count", label="Number of Cameras", fieldtype="Int", insert_after="custom_installation_type", depends_on="eval:doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV'", mandatory_depends_on="eval:doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV'"),
            dict(fieldname="custom_site_survey_needed", label="Site Survey Required?", fieldtype="Select", options="\nYes\nNo", insert_after="custom_camera_count", depends_on="eval:doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV' && doc.custom_camera_count >= 30", mandatory_depends_on="eval:doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV' && doc.custom_camera_count >= 30"),
            dict(fieldname="custom_elv_site_survey_required", label="ELV Site Survey Required", fieldtype="Check", default="0",
                 insert_after="custom_presales_required", depends_on="eval:doc.custom_presales_required"),
            dict(fieldname="custom_technical_site_survey_required", label="Technical Expertise and Site Survey Required", fieldtype="Check", default="0",
                 insert_after="custom_elv_site_survey_required", depends_on="eval:doc.custom_presales_required"),
            dict(fieldname="custom_site_survey_request", label="Projects — Site Survey Request", fieldtype="Link", options="Site Survey Request",
                 insert_after="custom_technical_site_survey_required", read_only=1, no_copy=1,
                 depends_on="eval:doc.custom_site_survey_request")],
        "Presales Request": [
            dict(fieldname="custom_site_survey_request", label="Site Survey Request", fieldtype="Link", options="Site Survey Request",
                 insert_after="site_visit", read_only=1, no_copy=1),
            dict(fieldname="custom_survey_results", label="Site Survey Results", fieldtype="Text Editor", read_only=1,
                 fetch_from="custom_site_survey_request.results", insert_after="custom_site_survey_request")]
    }, update=True)
    make_property_setter("Opportunity", "custom_presales_required", "label", "Presales Support Required", "Data")
    make_property_setter("Opportunity", "custom_presales_required", "insert_after", "custom_site_survey_needed", "Data")
    make_property_setter("Opportunity", "sales_stage", "reqd", 0, "Check")
    make_property_setter("Opportunity", "sales_stage", "hidden", 1, "Check")
    options = (frappe.get_meta("Presales Request").get_field("status").options or "").splitlines()
    for status in (WAITING, RECEIVED):
        if status not in options:
            options.append(status)
    make_property_setter("Presales Request", "status", "options", "\n".join(options), "Text")
    for field in DEFERRED_FIELDS:
        make_property_setter("Presales Request", field, "reqd", 0, "Check")
        make_property_setter("Presales Request", field, "mandatory_depends_on",
            "eval:!doc.custom_site_survey_request || !['Awaiting Site Survey Results','Site Survey Results Received','Cancelled','On Hold'].includes(doc.status)", "Data")
    ensure_navigation()
    frappe.clear_cache()
    return {"status": "ready", "doctype": "Site Survey Request"}


def ensure_navigation():
    # Update the current sidebar documents in place, preserving unrelated links.
    for doctype in ("Sidebar", "Workspace Sidebar", "Custom Sidebar"):
        if not frappe.db.exists("DocType", doctype):
            continue
        for name in frappe.get_all(doctype, pluck="name"):
            nav = frappe.get_doc(doctype, name)
            table = "sidebar_items" if doctype == "Custom Sidebar" else "items"
            rows = nav.get(table) or []
            project = next((r for r in rows if r.link_type == "DocType" and r.link_to == "Project"), None)
            if not project:
                continue
            row = next((r for r in rows if r.link_to == "Site Survey Request"), None)
            if row and rows.index(row) == rows.index(project) - 1 and row.child == project.child:
                continue
            if not row:
                row = nav.append(table, dict(type="Link", label="Site Survey Request", link_type="DocType",
                    link_to="Site Survey Request", icon="clipboard-list", child=project.child or 0,
                    indent=project.indent or 0, added=0))
            row.child = project.child or 0
            rows.remove(row)
            rows.insert(rows.index(project), row)
            for idx, item in enumerate(rows, 1):
                item.idx = idx
            previous = frappe.flags.in_migrate
            try:
                frappe.flags.in_migrate = True
                nav.save(ignore_permissions=True)
            finally:
                frappe.flags.in_migrate = previous
