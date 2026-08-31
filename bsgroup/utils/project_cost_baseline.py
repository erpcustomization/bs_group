# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

"""Business logic for Project Cost Baseline.

Kept out of the DocType controller (project_cost_baseline.py) on purpose so the
controller stays a thin dispatcher and this module can be unit tested / reused
from other entry points (e.g. the Project on_update cost-overrun check, or a
future report) without instantiating a Document.
"""

import frappe
from frappe import _
from frappe.utils import flt


# ---------------------------------------------------------------------------
# Baseline creation / revision validation
# ---------------------------------------------------------------------------

def validate_dcs_belongs_to_project(doc):
	"""The selected DCS must belong to the same Project as the baseline."""
	if not doc.deal_cost_sheet or not doc.project:
		return

	dcs_project = frappe.db.get_value("Deal Cost Sheet", doc.deal_cost_sheet, "project")
	if dcs_project != doc.project:
		frappe.throw(
			_("Deal Cost Sheet {0} belongs to Project {1}, not {2}").format(
				doc.deal_cost_sheet, dcs_project or _("(none)"), doc.project
			)
		)


def validate_dcs_is_submitted(doc):
	"""An approved baseline may only be raised from a submitted (approved) DCS."""
	if not doc.deal_cost_sheet:
		return

	docstatus = frappe.db.get_value("Deal Cost Sheet", doc.deal_cost_sheet, "docstatus")
	if docstatus != 1:
		frappe.throw(
			_("Deal Cost Sheet {0} must be submitted/approved before it can be used as a Project Cost Baseline").format(
				doc.deal_cost_sheet
			)
		)


def set_baseline_amount_from_dcs(doc):
	"""Server-side is authoritative: always re-derive the baseline amount from
	the linked DCS's Total Cost rather than trusting whatever the client sent."""
	if not doc.deal_cost_sheet:
		return
	doc.baseline_amount = flt(frappe.db.get_value("Deal Cost Sheet", doc.deal_cost_sheet, "total_cost"))


def set_remaining_amount(doc):
	"""Remaining = Baseline Amount - (committed + actual) cost incurred so far.
	Computed against `doc.project`, which may not have any cost yet (a fresh
	baseline just remains equal to the full baseline amount)."""
	if not doc.project:
		return
	doc.remaining_amount = flt(doc.baseline_amount) - get_total_exposure(doc.project)


def validate_no_active_baseline_for_project(doc):
	"""A Project may have only one active (submitted + Approved) baseline at a
	time. Excludes the document this one amends, since that one is already
	cancelled by the time its amendment reaches before_submit."""
	filters = {
		"project": doc.project,
		"docstatus": 1,
		"status": "Approved",
		"name": ["!=", doc.name],
	}
	existing = frappe.get_all("Project Cost Baseline", filters=filters, pluck="name", limit=1)
	if existing:
		frappe.throw(
			_("Project {0} already has an active approved baseline: {1}. Amend it instead of creating a new one.").format(
				doc.project, existing[0]
			)
		)


def carry_forward_revision(doc):
	"""On amend, bump the revision counter. The revision chain itself is
	traced via `amended_from` - Frappe's own field for this - rather than a
	second custom link, since a custom link to what is (at submit time) a
	cancelled document trips core's cancelled-link validation; `amended_from`
	is explicitly exempted from that check."""
	if doc.amended_from:
		previous = frappe.db.get_value("Project Cost Baseline", doc.amended_from, "revision")
		doc.revision = flt(previous or 0) + 1
	else:
		doc.revision = 1


def supersede_previous_baselines(doc):
	"""Mark any other Approved baseline for the same Project as Superseded once
	this one is approved - guards against the rare case of two baselines being
	submitted for the same Project outside of the normal amend flow."""
	others = frappe.get_all(
		"Project Cost Baseline",
		filters={"project": doc.project, "docstatus": 1, "status": "Approved", "name": ["!=", doc.name]},
		pluck="name",
	)
	for name in others:
		frappe.db.set_value("Project Cost Baseline", name, "status", "Superseded")


def refresh_remaining_amount(project, extra_exposure=0):
	"""Recompute and persist `remaining_amount` on the Project's active
	baseline (if any). Safe to call after submit - the field is
	`allow_on_submit` precisely so this can keep it live as actual cost
	accrues, without reopening the locked baseline_amount/project/DCS.

	`extra_exposure` - see `check_cost_overrun_for_project` - covers the
	document currently mid-submit, whose own row isn't reflected yet in the
	DB-backed committed/actual sums `get_total_exposure` reads."""
	baseline_name = get_active_baseline(project)
	if not baseline_name:
		return
	baseline_amount = flt(frappe.db.get_value("Project Cost Baseline", baseline_name, "baseline_amount"))
	remaining = baseline_amount - get_total_exposure(project) - flt(extra_exposure)
	frappe.db.set_value("Project Cost Baseline", baseline_name, "remaining_amount", remaining)


def get_active_baseline(project):
	"""Return the name of the single active (submitted + Approved) Project Cost
	Baseline for a Project, or None if it has none."""
	return frappe.db.get_value(
		"Project Cost Baseline", {"project": project, "docstatus": 1, "status": "Approved"}, "name"
	)


# ---------------------------------------------------------------------------
# Cost aggregation: committed / actual, reusing existing ERPNext Project cost
# fields and the Labor Preapproval consumed/remaining pattern rather than
# duplicating that logic.
# ---------------------------------------------------------------------------

def get_purchase_committed_cost(project):
	"""Committed purchase cost: submitted Purchase Orders not yet fully billed.
	Actual purchase cost (billed/received) is already rolled up by ERPNext core
	onto `Project.total_purchase_cost` - see get_actual_purchase_cost below."""
	result = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(po.base_grand_total), 0)
		FROM `tabPurchase Order` po
		WHERE po.project = %(project)s AND po.docstatus = 1 AND po.status != "Closed"
		""",
		{"project": project},
	)
	return flt(result[0][0]) if result else 0


def get_actual_purchase_cost(project):
	"""ERPNext core already maintains this on Project via its own Purchase
	Invoice/Purchase Receipt update triggers - reused as-is rather than
	re-summed here."""
	return flt(frappe.db.get_value("Project", project, "total_purchase_cost"))


def get_material_consumption_cost(project):
	"""Reused as-is from ERPNext core's Project rollup."""
	return flt(frappe.db.get_value("Project", project, "total_consumed_material_cost"))


def get_expense_cost(project):
	"""ERPNext core already maintains `total_expense_claim` on Project; reused
	as-is instead of re-summing Expense Claim rows."""
	return flt(frappe.db.get_value("Project", project, "total_expense_claim"))


def get_labour_cost(project):
	"""Sum of consumed (already paid, via submitted Labor Payment Voucher)
	labour cost across every Labor Preapproval raised against this Project,
	reusing `get_consumed_cost` from Labor Preapproval rather than
	re-deriving Labor Payment Voucher totals here."""
	from bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval import get_consumed_cost

	lpre_names = _get_project_lpre_names(project)
	return sum(flt(get_consumed_cost(name)) for name in lpre_names)


def get_labour_committed_cost(project):
	"""Sum of the still-outstanding (approved but not yet consumed) portion
	of every submitted Labor Preapproval against this Project - the labour
	equivalent of an open Purchase Order: authorised spend the Project has
	already committed to, whether or not it has been paid out yet. Reuses
	`get_remaining_cost` rather than re-deriving it here."""
	from bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval import get_remaining_cost

	lpre_names = _get_project_lpre_names(project)
	return sum(max(flt(get_remaining_cost(name)), 0) for name in lpre_names)


def _get_project_lpre_names(project):
	return frappe.get_all(
		"Labor Preapproval",
		filters={"source": "Project", "reference": project, "docstatus": 1},
		pluck="name",
	)


def get_committed_cost(project):
	"""Committed = raised but not yet actualised: open Purchase Orders, plus
	the not-yet-consumed portion of approved Labor Preapprovals."""
	return get_purchase_committed_cost(project) + get_labour_committed_cost(project)


def get_actual_cost(project):
	"""Actual = realised cost against the Project so far, aggregated across
	every approved cost source in scope for DEV-020."""
	return (
		get_actual_purchase_cost(project)
		+ get_material_consumption_cost(project)
		+ get_expense_cost(project)
		+ get_labour_cost(project)
	)


def get_total_exposure(project):
	"""Committed + Actual - what the Project has already obligated against its
	baseline, whether or not it has been billed/received yet."""
	return get_committed_cost(project) + get_actual_cost(project)


def get_project_cost_summary(project):
	"""Baseline -> Committed -> Actual -> Variance, the core comparison this
	feature exists to show. Returns None baseline/variance fields when the
	Project has no active approved baseline yet, rather than guessing one.

	Overrun is judged against *exposure* (committed + actual), not actual
	alone - a submitted-but-unbilled Purchase Order is already a real
	obligation against the baseline even though ERPNext core won't roll it
	into `total_purchase_cost` until it is received/billed. Judging only
	actual cost would let a Project blow past its baseline via open POs
	with no warning until invoices eventually land."""
	baseline_name = get_active_baseline(project)
	baseline_amount = flt(frappe.db.get_value("Project Cost Baseline", baseline_name, "baseline_amount")) if baseline_name else None

	committed = get_committed_cost(project)
	actual = get_actual_cost(project)
	exposure = committed + actual

	variance = (baseline_amount - exposure) if baseline_amount is not None else None
	variance_percent = (
		((exposure - baseline_amount) / baseline_amount) * 100 if baseline_amount else None
	)

	return {
		"project": project,
		"baseline": baseline_name,
		"baseline_amount": baseline_amount,
		"committed_cost": committed,
		"actual_cost": actual,
		"total_exposure": exposure,
		"variance": variance,
		"variance_percent": variance_percent,
		"is_overrun": variance is not None and variance < 0,
	}


# ---------------------------------------------------------------------------
# Overrun policy - deliberately configurable (BS Group Settings.cost_overrun_policy)
# rather than hard-coded, since the business rule is owned by DEC-09 and may
# change independently of this module.
# ---------------------------------------------------------------------------

def check_cost_overrun_for_project(project, raise_from=None, extra_exposure=0):
	"""Core, doctype-agnostic overrun check. Refreshes the active baseline's
	`remaining_amount` and, if committed+actual exposure now exceeds it,
	warns/blocks per `BS Group Settings.cost_overrun_policy`. A Project with
	no active baseline is out of scope - nothing to compare against.

	`raise_from` is only used to make the thrown/msgprint message name the
	transaction that triggered the check (e.g. a specific Purchase Order)
	instead of just the Project, when called from a transaction-level hook.

	`extra_exposure` accounts for the document currently being validated: a
	doc_events `validate` hook runs (even during submit) before Frappe writes
	the new docstatus to the database - see `Document._save`, which calls
	`run_before_save_methods` (-> validate) before `set_docstatus`/`db_update`.
	So the row this validate call belongs to is *not yet* reflected in the
	DB-backed committed-cost sum, and would otherwise let exactly the
	transaction that crosses the baseline slip through with no warning."""
	refresh_remaining_amount(project, extra_exposure=extra_exposure)

	summary = get_project_cost_summary(project)
	exposure = summary["total_exposure"] + flt(extra_exposure)
	baseline_amount = summary["baseline_amount"]
	if baseline_amount is None or exposure <= baseline_amount:
		return

	policy = frappe.db.get_single_value("BS Group Settings", "cost_overrun_policy") or "Warn"
	if policy == "None":
		return

	currency = frappe.get_cached_value("Project", project, "currency")
	variance = baseline_amount - exposure
	message = _(
		"{0}: committed + actual cost {1} exceeds the approved Project Cost Baseline {2} (variance {3})"
	).format(
		raise_from or summary["project"],
		frappe.utils.fmt_money(exposure, currency=currency),
		frappe.utils.fmt_money(baseline_amount, currency=currency),
		frappe.utils.fmt_money(variance, currency=currency),
	)

	if policy == "Block":
		frappe.throw(message, title=_("Project Cost Baseline Exceeded"))
	else:
		frappe.msgprint(message, title=_("Project Cost Baseline Exceeded"), indicator="orange", alert=True)


def check_project_cost_overrun(doc, method=None):
	"""doc_events hook for Project's own on_update."""
	check_cost_overrun_for_project(doc.name)


def check_transaction_cost_overrun(doc, method=None):
	"""doc_events hook for cost transactions that carry a `project` field
	(Purchase Order, Purchase Invoice, Expense Claim, ...). Runs on
	`validate`, so it fires on every save including submit - i.e. before the
	commitment is actually made, per the "warn or block before committed"
	business objective - not only after the fact via Project's own on_update
	(which core ERPNext doesn't even trigger for a Purchase Order, since PO
	submission never touches the Project document)."""
	if not getattr(doc, "project", None):
		return

	# Only count this document's own amount once it is actually being
	# submitted (doc._action == "submit") - a plain draft save is not yet a
	# commitment and shouldn't count toward exposure.
	extra_exposure = 0
	if getattr(doc, "_action", None) == "submit":
		extra_exposure = flt(getattr(doc, "base_grand_total", None) or getattr(doc, "grand_total", 0))

	check_cost_overrun_for_project(doc.project, raise_from=f"{doc.doctype} {doc.name}", extra_exposure=extra_exposure)


def check_labor_preapproval_cost_overrun(doc, method=None):
	"""doc_events hook for Labor Preapproval. Its Project link lives on
	`reference` (only meaningful when `source == "Project"`), not `project`,
	so it needs its own thin wrapper rather than reusing
	`check_transaction_cost_overrun` directly. An approved LPRE's full
	`total_labor_cost` counts as committed exposure the moment it is
	submitted - not just once Labor Attendance/Payment Vouchers are paid out
	against it - same reasoning as a submitted Purchase Order."""
	if doc.source != "Project" or not doc.reference:
		return

	extra_exposure = 0
	if getattr(doc, "_action", None) == "submit":
		extra_exposure = flt(doc.total_labor_cost)

	check_cost_overrun_for_project(doc.reference, raise_from=f"{doc.doctype} {doc.name}", extra_exposure=extra_exposure)


@frappe.whitelist()
def get_cost_summary(project):
	"""Whitelisted read-only entry point for dashboards/reports."""
	return get_project_cost_summary(project)
