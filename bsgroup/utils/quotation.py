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

# Stages a Quotation may only ever be submitted (docstatus 1) to reach -
# marking an unsent draft Won or Lost is a data-entry mistake, not a result.
SUBMITTED_ONLY_STAGES = ("Won", "Lost")

# Explicit transition map: {from_stage: {allowed to_stages}}. Anything not
# listed here (including any move FROM a terminal stage) is rejected unless
# the user holds a PIPELINE_REOPEN_ROLE.
PIPELINE_TRANSITIONS = {
	"Draft": {"Sent"},
	"Sent": {"Follow-up", "Won", "Lost", "Cancelled", "Expired"},
	"Follow-up": {"Won", "Lost", "Cancelled", "Expired"},
}
PIPELINE_TERMINAL_STAGES = ("Won", "Lost", "Cancelled", "Expired")
PIPELINE_REOPEN_ROLES = ("System Manager", "Sales Manager")

# Pipeline stage -> ERPNext core `status`. Only applied to submitted
# Quotations - a draft's status is managed by core itself (stays "Draft").
STATUS_BY_STAGE = {
	"Sent": "Open",
	"Follow-up": "Open",
	"Won": "Ordered",
	"Lost": "Lost",
	"Cancelled": "Cancelled",
	"Expired": "Expired",
}


def validate_pipeline_stage(doc, method=None):
	"""Enforce the pipeline transition map, mandatory Lost/Cancelled reason,
	and Won/Lost date maintenance. Server-side guard - the popup on the form
	is the primary UX, this makes the rule hold for API/bench updates too,
	not just the form."""
	stage = doc.custom_pipeline_stage
	previous_stage = _get_previous_pipeline_stage(doc)

	if previous_stage and previous_stage != stage:
		_validate_pipeline_transition(previous_stage, stage)

	if stage in SUBMITTED_ONLY_STAGES and doc.docstatus == 0:
		frappe.throw(
			f"Quotation must be submitted before Pipeline Stage can be set to '{stage}'",
			title="Not Submitted",
		)

	if stage in LOST_REASON_STAGES and not doc.custom_lost_reason:
		frappe.throw(
			f"Reason is mandatory when Pipeline Stage is '{stage}'",
			title="Reason Required",
		)

	# Date maintenance: the date always reflects the *current* stage, not
	# whichever stage happened to set it first - so re-entering Won after a
	# detour through Follow-up re-stamps today's date, and leaving Won/Lost
	# clears the date that no longer applies.
	if stage == "Won":
		doc.custom_won_date = today()
		doc.custom_lost_date = None
	elif stage in LOST_REASON_STAGES:
		doc.custom_lost_date = today()
		doc.custom_won_date = None
	else:
		doc.custom_won_date = None
		doc.custom_lost_date = None

	# The reason field is only meaningful while parked in Lost/Cancelled -
	# once the stage moves on, a stale reason would misrepresent the
	# eventual outcome (e.g. a quotation later Won still "explaining" why it
	# was lost).
	if stage not in LOST_REASON_STAGES:
		doc.custom_lost_reason = None


def _get_previous_pipeline_stage(doc):
	if doc.is_new():
		return None
	before_save = doc.get_doc_before_save()
	if before_save:
		return before_save.custom_pipeline_stage
	return frappe.db.get_value("Quotation", doc.name, "custom_pipeline_stage")


def _validate_pipeline_transition(previous_stage, stage):
	if _current_user_can_reopen():
		return

	if previous_stage in PIPELINE_TERMINAL_STAGES:
		frappe.throw(
			f"Pipeline Stage '{previous_stage}' is terminal and cannot move to '{stage}'. "
			"Only a Sales Manager / System Manager can reopen it.",
			title="Pipeline Stage Locked",
		)

	allowed = PIPELINE_TRANSITIONS.get(previous_stage, set())
	if stage not in allowed:
		frappe.throw(
			f"Cannot move Pipeline Stage from '{previous_stage}' to '{stage}'.",
			title="Invalid Pipeline Transition",
		)


def _current_user_can_reopen():
	return bool(set(frappe.get_roles()) & set(PIPELINE_REOPEN_ROLES))


def sync_pipeline_result(doc, method=None):
	"""Keep the core `status` field in step with the pipeline stage (only
	once submitted - a draft's status stays whatever core manages), and push
	Won/Lost result onto the linked Opportunity and any Presales Request
	against that Opportunity, so the outcome is visible there too."""
	if doc.docstatus == 1:
		status = STATUS_BY_STAGE.get(doc.custom_pipeline_stage)
		if status and doc.status != status:
			doc.db_set("status", status, update_modified=False)

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


def sync_expired_pipeline_stage():
	"""Daily scheduler task, run after core's own
	`erpnext.selling.doctype.quotation.quotation.set_expired_status`. Core
	flips `status` to Expired based on `valid_till` but never touches
	`custom_pipeline_stage`, so without this the two fields drift apart -
	a Quotation can sit at status Expired while its pipeline stage still
	reads Sent/Follow-up/Draft. Only moves stage for submitted Quotations
	already at Expired status and not already in a terminal pipeline stage,
	so it never overrides an explicit Won/Lost/Cancelled outcome."""
	names = frappe.get_all(
		"Quotation",
		filters={
			"docstatus": 1,
			"status": "Expired",
			"custom_pipeline_stage": ["not in", PIPELINE_TERMINAL_STAGES],
		},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Quotation", name, "custom_pipeline_stage", "Expired", update_modified=False)
