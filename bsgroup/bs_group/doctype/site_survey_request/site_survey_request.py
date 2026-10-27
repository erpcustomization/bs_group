import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, strip_html
from bsgroup.site_survey import WAITING, RECEIVED, request_details


class SiteSurveyRequest(Document):
    def validate(self):
        before = self.get_doc_before_save()
        if self.status in ("Requested", "Scheduled"):
            self.status = "Scheduled" if self.assigned_to and self.planned_date else "Requested"
        if before and self.opportunity != before.opportunity:
            frappe.throw(_("The linked Opportunity cannot be changed."))
        if before:
            for field in ("requested_by", "request_date", "presales_request"):
                if self.get(field) != before.get(field):
                    frappe.throw(_("The request origin and linked Presales Request cannot be changed."))
        opp = frappe.get_doc("Opportunity", self.opportunity)
        self.survey_request_details = (before.get("survey_request_details") if before else None) or request_details(opp)
        if self.is_new() and not self.flags.from_opportunity:
            frappe.throw(_("Request the site survey from the Opportunity."))
        for target, source in {
            "organization": "custom_organization_name", "title": "custom_subject", "company": "company",
            "opportunity_amount": "opportunity_amount", "currency": "currency", "salesperson": "opportunity_owner",
            "contact_email": "contact_email",
            "elv_required": "custom_elv_site_survey_required",
            "technical_required": "custom_technical_site_survey_required"}.items():
            self.set(target, opp.get(source))
        self.title = self.title or opp.title or opp.name
        if self.is_new():
            self.contact_person = opp.get("custom_survey_contact_name") or opp.get("custom_contact_person_name")
            self.contact_phone = opp.get("custom_survey_contact_phone") or opp.get("contact_mobile")
        self.salesperson_name = frappe.db.get_value("User", self.salesperson, "full_name") if self.salesperson else None
        if before and before.status in ("Completed", "Cancelled") and self.status != before.status:
            frappe.throw(_("A completed or cancelled survey cannot be reopened."))
        if self.status == "Completed":
            if not strip_html(self.results or "").strip():
                frappe.throw(_("Enter the site survey results before completing the request."))
            if before and before.status == "Completed":
                self.completed_on, self.completed_by = before.completed_on, before.completed_by
            else:
                self.completed_on = now_datetime()
                self.completed_by = frappe.session.user
        else:
            self.completed_on = self.completed_by = None

    def on_update(self):
        if self.status == "Completed" and self.presales_request:
            pre = frappe.get_doc("Presales Request", self.presales_request)
            if pre.custom_site_survey_request != self.name:
                frappe.throw(_("The Presales Request does not match this survey."))
            if pre.status == WAITING:
                pre.status = RECEIVED
                pre.save(ignore_permissions=True)

    def on_trash(self):
        frappe.throw(_("Cancel the Site Survey Request instead of deleting its history."))
