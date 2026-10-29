"""Opportunity qualification rules shared by forms, conversions and imports."""
import frappe
from frappe import _
from frappe.utils import cint, flt

FIELDS = ("custom_business_type", "custom_service_type", "custom_service_survey", "custom_service_details", "custom_installation_type", "custom_camera_count", "custom_site_survey_needed")
ADDITIONAL_SOLUTIONS = ("Networking & Security", "Structured Cabling & Fiber", "Unified Communications & Intercom", "IT Infrastructure - Multi Solution")
SERVICE_TYPES = ("CCTV", "3CX", "ELV", *ADDITIONAL_SOLUTIONS)
INSTALLATION_TYPES = ("CCTV", "3CX", "Networking", "Other", *ADDITIONAL_SOLUTIONS)


def no_presales(doc):
    return doc.get("custom_business_type") == "Supply" or not cint(doc.get("custom_presales_required"))


def validate(doc, method=None):
    if doc.is_new() and not (doc.get("custom_enquiry") or "").strip():
        frappe.throw(_("Enter the customer Enquiry before creating the Opportunity. For a Lead conversion, complete the Lead Requirement first."))
    kind = doc.get("custom_business_type")
    if not kind and doc.is_new() and doc.opportunity_from == "Lead" and doc.flags.get("deferred_lead_intake"):
        # A Lead status change creates an Open Opportunity before qualification.
        # Do not invent a business type or dispatch any survey/presales work.
        doc.custom_presales_required = 0
        doc.custom_elv_site_survey_required = 0
        doc.custom_technical_site_survey_required = 0
        return
    # Historical records remain editable without inventing their classification.
    if not kind and not doc.is_new():
        return
    if kind not in ("Supply", "Service", "Supply and Installation"):
        frappe.throw(_("Choose Supply, Service or Supply and Installation."))
    if kind in ("Service", "Supply and Installation"):
        if doc.get("custom_presales_support") not in ("Yes", "No"):
            frappe.throw(_("Choose Yes or No for Presales Support Required."))
        doc.custom_presales_required = int(doc.custom_presales_support == "Yes")
    if kind == "Service":
        if doc.get("custom_service_type") not in SERVICE_TYPES:
            frappe.throw(_("Choose a Service Type."))
    if kind in ("Service", "Supply and Installation"):
        if doc.get("custom_service_survey") not in ("Site Survey by ELV", "Site Survey by Technical Team", "No Site Survey Required"):
            frappe.throw(_("Choose the Site Survey Requirement."))
        if doc.get("custom_service_survey") == "No Site Survey Required" and not (doc.get("custom_enquiry") or "").strip():
            frappe.throw(_("Enter the customer Enquiry before creating the Deal Cost Sheet."))
    if kind == "Supply and Installation":
        if doc.get("custom_installation_type") not in INSTALLATION_TYPES:
            frappe.throw(_("Choose an Installation Type."))
        if doc.custom_installation_type == "CCTV":
            count = flt(doc.get("custom_camera_count"))
            if count <= 0 or count != int(count):
                frappe.throw(_("Enter a positive whole number of cameras."))
    before = doc.get_doc_before_save()
    if doc.get("custom_site_survey_request") or (before and before.get("custom_site_survey_request")):
        if before and any(doc.get(f) != before.get(f) for f in FIELDS):
            frappe.throw(_("Survey routing has already started. The Opportunity classification cannot be changed."))
    if kind == "Supply":
        if not doc.is_new() and frappe.db.exists("Presales Request", {"opportunity": doc.name, "status": ["!=", "Cancelled"], "docstatus": ["<", 2]}):
            frappe.throw(_("An active Presales Request already exists. Resolve it before changing to a category that does not require presales."))
        if any(cint(doc.get(f)) for f in ("custom_presales_required", "custom_elv_site_survey_required", "custom_technical_site_survey_required")):
            frappe.throw(_("Presales support and site survey are not available for Supply. Proceed to the Deal Cost Sheet."))
    if kind in ("Service", "Supply and Installation"):
        doc.custom_elv_site_survey_required = int(doc.custom_service_survey == "Site Survey by ELV")
        doc.custom_technical_site_survey_required = int(doc.custom_service_survey == "Site Survey by Technical Team")
    if kind != "Service":
        doc.custom_service_type = None
    if kind == "Supply":
        doc.custom_service_survey = None
        doc.custom_service_details = None
    if kind != "Supply and Installation":
        doc.custom_installation_type = None
    if kind != "Supply and Installation" or doc.custom_installation_type != "CCTV":
        doc.custom_camera_count = 0
        doc.custom_site_survey_needed = None
    elif cint(doc.custom_camera_count) < 30:
        doc.custom_site_survey_needed = None
    validate_survey_steps(doc, before)


def validate_survey_steps(doc, before=None):
    fields = ("custom_survey_instructions", "custom_survey_location", "custom_survey_contact_phone", "custom_survey_step", "custom_survey_contact_name")
    if doc.get("custom_site_survey_request") or (before and before.get("custom_site_survey_request")):
        if before and any(doc.get(f) != before.get(f) for f in fields):
            frappe.throw(_("The survey request has already been sent. Update its details in Projects."))
        return
    selected = any(cint(doc.get(f)) for f in ("custom_elv_site_survey_required", "custom_technical_site_survey_required"))
    if selected:
        required = (*fields[:3], "custom_survey_contact_name", "custom_enquiry")
        missing = [doc.meta.get_label(field) for field in required if not (doc.get(field) or "").strip()]
        if missing:
            frappe.throw(_("Complete all required site survey details before saving: {0}").format(", ".join(missing)))
        # A fully qualified save must dispatch the survey, including API saves.
        doc.custom_survey_step = 3
        if doc.get("custom_business_type") == "Service":
            doc.custom_service_details = doc.custom_survey_instructions
        return
    step = cint(doc.get("custom_survey_step")) if selected else 0
    if step not in (0, 1, 2, 3):
        frappe.throw(_("Invalid survey confirmation step."))
    for index, field in enumerate(fields[:3], 1):
        if step >= index and not (doc.get(field) or "").strip():
            frappe.throw(_("Complete {0} before confirming this step.").format(doc.meta.get_label(field)))
    if step == 3 and not (doc.get('custom_survey_contact_name') or '').strip():
        frappe.throw(_("Enter the contact person name before sending the survey request."))
    if before and selected:
        for index, field in enumerate(fields[:2]):
            if doc.get(field) != before.get(field) and cint(before.get("custom_survey_step")) > index and step > index + 1:
                step = index
                break
    doc.custom_survey_step = step
    if selected and doc.get("custom_business_type") == "Service":
        doc.custom_service_details = doc.get("custom_survey_instructions") or None


def guard_presales(doc, method=None):
    if doc.opportunity and (doc.is_new() or doc.has_value_changed("opportunity")):
        if no_presales(frappe.get_doc("Opportunity", doc.opportunity)):
            frappe.throw(_("This Opportunity proceeds directly to a Deal Cost Sheet; presales support is not required."))


@frappe.whitelist()
def create_supply_cost_sheet(opportunity):
    """Create one saved draft without navigating away from the Opportunity."""
    doc = frappe.get_doc("Opportunity", opportunity, for_update=True)
    doc.check_permission("write")
    if doc.get("custom_business_type") != "Supply":
        frappe.throw(_("This action is only available for Supply opportunities."))
    if flt(doc.get("opportunity_amount")) <= 0:
        frappe.throw(_("Enter an Opportunity Value greater than zero."))
    return create_cost_sheet(doc)


def create_cost_sheet(doc, *, ignore_permissions=False):
    existing = frappe.get_all("Deal Cost Sheet", filters={"opportunity": doc.name, "docstatus": ["<", 2]},
        fields=["name", "custom_record_authority"], order_by="creation desc")
    for row in existing:
        if row.custom_record_authority != "Superseded":
            if not ignore_permissions:
                frappe.get_doc("Deal Cost Sheet", row.name).check_permission("read")
            return {"name": row.name, "created": False}
    sheet = frappe.new_doc("Deal Cost Sheet")
    sheet.update({"opportunity": doc.name, "party_type": doc.opportunity_from,
        "party": doc.party_name, "organisation_name": doc.get("custom_organization_name"),
        "subject": doc.get("custom_subject") or doc.title, "company": doc.company,
        "currency": doc.currency})
    sheet.insert(ignore_permissions=ignore_permissions)
    return {"name": sheet.name, "created": True}


def create_no_survey_cost_sheet(doc, method=None):
    kind = doc.get("custom_business_type")
    direct = kind == "Supply" or (
        kind == "Service" and doc.get("custom_service_survey") == "No Site Survey Required"
    ) or (kind == "Supply and Installation" and not cint(doc.get("custom_presales_required")))
    if not direct:
        return
    if doc.get("custom_site_survey_request") or any(cint(doc.get(f)) for f in (
        "custom_presales_required", "custom_elv_site_survey_required", "custom_technical_site_survey_required"
    )):
        return
    if frappe.db.exists("Presales Request", {"opportunity": doc.name, "docstatus": ["<", 2], "status": ["!=", "Cancelled"]}):
        return
    if not (doc.get("custom_enquiry") or "").strip():
        frappe.throw(_("Enter the customer Enquiry before creating the Deal Cost Sheet."))
    # The save has already checked enquiry, service type and sales qualification.
    frappe.db.sql("SELECT name FROM `tabOpportunity` WHERE name=%s FOR UPDATE", doc.name)
    create_cost_sheet(doc)


@frappe.whitelist()
def setup_no_survey_details():
    frappe.only_for("System Manager")
    name = frappe.db.get_value("Custom Field", {"dt": "Opportunity", "fieldname": "custom_service_details"}, "name")
    if name:
        frappe.db.set_value("Custom Field", name, {"hidden": 1, "reqd": 0, "depends_on": "", "mandatory_depends_on": ""})
        frappe.clear_cache(doctype="Opportunity")
    return "Service Details hidden and optional"
