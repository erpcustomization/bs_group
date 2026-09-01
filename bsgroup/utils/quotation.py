import frappe
from frappe.utils import today
from erpnext.crm.doctype.opportunity.opportunity import make_quotation as _make_quotation


@frappe.whitelist()
def make_quotation(source_name, target_doc=None):
	quotation = _make_quotation(source_name, target_doc)

	opportunity = frappe.db.get_value(
		"Opportunity",
		source_name,
		["opportunity_from", "custom_contact_person_name", "custom_organization_name"],
		as_dict=True,
	)

	if opportunity:
		display_name = opportunity.custom_contact_person_name or ""
		quotation.custom_contact_person_name = display_name
		quotation.custom_organization_name = opportunity.custom_organization_name or ""
		if opportunity.opportunity_from == "Lead" and display_name:
			quotation.customer_name = display_name

	return quotation


LOST_REASON_STAGES = ("Lost", "Cancelled")


def validate_pipeline_stage(doc, method=None):
	"""Enforce mandatory Lost/Cancelled reason and stamp Won/Lost dates.
	Server-side guard - the popup on the form is the primary UX, this makes
	the rule hold for API/bench updates too, not just the form."""
	if doc.custom_pipeline_stage in LOST_REASON_STAGES and not doc.custom_lost_reason:
		frappe.throw(
			f"Reason is mandatory when Pipeline Stage is '{doc.custom_pipeline_stage}'",
			title="Reason Required",
		)

	if doc.custom_pipeline_stage == "Won" and not doc.custom_won_date:
		doc.custom_won_date = today()

	if doc.custom_pipeline_stage == "Lost" and not doc.custom_lost_date:
		doc.custom_lost_date = today()


def sync_pipeline_result(doc, method=None):
	"""Push Won/Lost result onto the linked Opportunity and any Presales
	Request against that Opportunity, so the outcome is visible there too."""
	if doc.custom_pipeline_stage not in ("Won", "Lost") or not doc.opportunity:
		return

	if doc.custom_pipeline_stage == "Won":
		outcome_date = doc.custom_won_date
		presales_status = "Won"
	else:
		outcome_date = doc.custom_lost_date
		presales_status = "Lost"

	frappe.db.set_value(
		"Opportunity",
		doc.opportunity,
		{
			"custom_quotation_outcome": doc.custom_pipeline_stage,
			"custom_quotation_outcome_date": outcome_date,
			"custom_quotation_lost_reason": doc.custom_lost_reason if doc.custom_pipeline_stage == "Lost" else "",
		},
	)

	presales_requests = frappe.get_all(
		"Presales Request",
		filters={"opportunity": doc.opportunity, "docstatus": ("!=", 2)},
		pluck="name",
	)
	for pr in presales_requests:
		frappe.db.set_value("Presales Request", pr, "status", presales_status)
