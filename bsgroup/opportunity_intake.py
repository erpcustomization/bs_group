"""Opportunity qualification rules shared by forms, conversions and imports."""
import frappe
from frappe import _
from frappe.utils import cint, flt

FIELDS = ("custom_business_type", "custom_service_type", "custom_installation_type", "custom_camera_count", "custom_site_survey_needed")


def no_presales(doc):
    return doc.get("custom_business_type") == "Supply" or (
        doc.get("custom_business_type") == "Supply and Installation" and
        doc.get("custom_installation_type") == "CCTV" and 0 < cint(doc.get("custom_camera_count")) < 30)


def validate(doc, method=None):
    kind = doc.get("custom_business_type")
    # Historical records remain editable without inventing their classification.
    if not kind and not doc.is_new():
        return
    if kind not in ("Supply", "Service", "Supply and Installation"):
        frappe.throw(_("Choose Supply, Service or Supply and Installation."))
    if kind == "Service" and doc.get("custom_service_type") not in ("AMC", "New Service Opportunity"):
        frappe.throw(_("Choose AMC or New Service Opportunity."))
    if kind == "Supply and Installation":
        if doc.get("custom_installation_type") not in ("CCTV", "3CX", "Networking", "Other"):
            frappe.throw(_("Choose CCTV, 3CX, Networking or Other."))
        if doc.custom_installation_type == "CCTV":
            count = flt(doc.get("custom_camera_count"))
            if count <= 0 or count != int(count):
                frappe.throw(_("Enter a positive whole number of cameras."))
            if count >= 30 and doc.get("custom_site_survey_needed") not in ("Yes", "No"):
                frappe.throw(_("Choose whether a site survey is required."))
    before = doc.get_doc_before_save()
    if doc.get("custom_site_survey_request") or (before and before.get("custom_site_survey_request")):
        if before and any(doc.get(f) != before.get(f) for f in FIELDS):
            frappe.throw(_("Survey routing has already started. The Opportunity classification cannot be changed."))
    if no_presales(doc):
        if not doc.is_new() and frappe.db.exists("Presales Request", {"opportunity": doc.name, "status": ["!=", "Cancelled"], "docstatus": ["<", 2]}):
            frappe.throw(_("An active Presales Request already exists. Resolve it before changing to a category that does not require presales."))
        if any(cint(doc.get(f)) for f in ("custom_presales_required", "custom_elv_site_survey_required", "custom_technical_site_survey_required")):
            frappe.throw(_("Presales support and site survey are not available for Supply or CCTV with fewer than 30 cameras. Proceed to the Deal Cost Sheet."))
    if kind == "Supply and Installation" and doc.custom_installation_type == "CCTV" and cint(doc.custom_camera_count) >= 30:
        needed = int(doc.custom_site_survey_needed == "Yes")
        doc.custom_presales_required = needed
        doc.custom_elv_site_survey_required = needed
        doc.custom_technical_site_survey_required = 0
    if kind != "Service":
        doc.custom_service_type = None
    if kind != "Supply and Installation":
        doc.custom_installation_type = None
    if kind != "Supply and Installation" or doc.custom_installation_type != "CCTV":
        doc.custom_camera_count = 0
        doc.custom_site_survey_needed = None
    elif cint(doc.custom_camera_count) < 30:
        doc.custom_site_survey_needed = None


def guard_presales(doc, method=None):
    if doc.opportunity and (doc.is_new() or doc.has_value_changed("opportunity")):
        if no_presales(frappe.get_doc("Opportunity", doc.opportunity)):
            frappe.throw(_("This Opportunity proceeds directly to a Deal Cost Sheet; presales support is not required."))
