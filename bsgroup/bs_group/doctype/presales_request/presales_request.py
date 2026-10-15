# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate

from bsgroup.utils.party import apply_party_model, require_customer, slug


class PresalesRequest(Document):
	SITE_VISIT_CLOSING_STATUSES = ("Completed", "Won", "Lost")
	EFFORT_LOGGING_CLOSING_STATUSES = ("Ready for Quotation", "Submitted to Sales", "Completed", "Won", "Lost")
	COMPLETION_DATE_STATUSES = ("Completed", "Won", "Lost")
	# D3: these outcomes commit the business to a counterparty; a Customer record must exist.
	CUSTOMER_REQUIRED_STATUSES = ("Won",)
	# Statuses the daily overdue scheduler leaves alone (A-8).
	CLOSED_STATUSES = ("Completed", "Won", "Lost", "Cancelled")

	def validate(self):
		apply_party_model(self)
		self._validate_customer_before_award()
		self._validate_unique_per_opportunity()
		self._validate_site_visit_required()
		self._validate_effort_logged_before_closing()

	def autoname(self):
		# Named after the organisation (D2); identical slug rule to the historical
		# customer-based name so existing PR-<slug>-### names stay consistent.
		apply_party_model(self)
		base = slug(self.organisation_name or self.customer)
		if base:
			self.name = frappe.model.naming.make_autoname(f"PR-{base}-.###")

	def _validate_customer_before_award(self):
		if self.status in self.CUSTOMER_REQUIRED_STATUSES:
			require_customer(self, _("the request is set to {0}").format(self.status))

	def _validate_unique_per_opportunity(self):
		"""A-7: one live Presales Request per Opportunity.

		Enforced only when the Opportunity link is being set or changed, so a
		pre-existing duplicate (historical remediation H-2) stays saveable.
		"""
		if not self.opportunity:
			return
		before = self.get_doc_before_save()
		if before is not None and before.opportunity == self.opportunity:
			return
		frappe.db.get_value("Opportunity", self.opportunity, "name", for_update=True)
		other = frappe.db.get_value(
			"Presales Request",
			{
				"opportunity": self.opportunity,
				"docstatus": ["<", 2],
				"status": ["!=", "Cancelled"],
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if other:
			frappe.throw(
				_("Opportunity {0} already has an active Presales Request: {1}. Only one Presales Request may be open per Opportunity.")
				.format(self.opportunity, other),
				title=_("Duplicate Presales Request"),
			)

	def before_save(self):
		calculate_quality_score(self)

	def on_update(self):
		from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import dcs_presales_sync
		dcs_presales_sync(self.name, source="interactive")

	def on_cancel(self):
		self.db_set("status", "Cancelled")

	def after_insert(self):
		if self.opportunity:
			frappe.db.set_value(
				"Opportunity",
				self.opportunity,
				"status",
				"Presales Request"
			)

	def _validate_site_visit_required(self):
		if not (self.site_visit_required and not self.site_visit):
			return

		if self.is_new():
			frappe.throw(frappe._("Site Visit is mandatory when Site Visit Required is checked"))
			return

		# A request cannot be closed out (Completed/Won/Lost) while a
		# required Site Visit is still missing, regardless of when the
		# checkbox was originally turned on - this is the gap that let a
		# request be ticked and then closed without one ever being raised.
		if self.status in self.SITE_VISIT_CLOSING_STATUSES:
			frappe.throw(
				frappe._("Site Visit is mandatory before this Presales Request can be set to {0}").format(self.status)
			)

		# Existing records created before this rule (or before any Site
		# Visit was raised against them) would otherwise be permanently
		# unsaveable - only enforce when the checkbox is actually being
		# turned on in this save, not on every edit of a pre-existing
		# record that was already left in this state.
		before_save = self.get_doc_before_save()
		was_already_required = bool(before_save and before_save.site_visit_required)
		if not was_already_required:
			frappe.throw(frappe._("Site Visit is mandatory when Site Visit Required is checked"))

	def _validate_effort_logged_before_closing(self):
		if self.status not in self.EFFORT_LOGGING_CLOSING_STATUSES:
			return

		if not self.actual_hours:
			frappe.throw(
				frappe._('Enter Actual Hours before moving this Presales Request to "{0}". '
						'Presales effort must be logged so the deal can be evaluated.').format(self.status)
			)

		if self.status in self.COMPLETION_DATE_STATUSES and not self.completion_date:
			self.completion_date = frappe.utils.nowdate()


def calculate_quality_score(doc):
		score = 0

		if doc.decision_maker_known:
			score += 20
		if doc.competition_known:
			score += 20
		if doc.budget_confirmed:
			score += 20
		if doc.timeline_defined:
			score += 20
		if doc.site_visit_required:
			score += 20

		doc.quality_score = score

def calculate_due_date():
	"""Daily scheduler (A-8): keep `overdue` / `delay_days` current on live requests.

	Only open, uncancelled requests with a due date are considered; a record is
	written only when the stored values actually differ; `modified` is never
	bumped by this housekeeping; one failing record never stops the run.
	"""
	today = getdate(nowdate())
	rows = frappe.get_all(
		"Presales Request",
		filters={
			"docstatus": ["<", 2],
			"status": ["not in", list(PresalesRequest.CLOSED_STATUSES)],
			"due_date": ["is", "set"],
		},
		fields=["name", "due_date", "overdue", "delay_days"],
		limit_page_length=0,
	)
	scanned = updated = failed = 0
	for pre in rows:
		scanned += 1
		try:
			due_date = getdate(pre.due_date)
			overdue = 1 if due_date < today else 0
			delay_days = (today - due_date).days if overdue else 0
			if frappe.utils.cint(pre.overdue) == overdue and frappe.utils.cint(pre.delay_days) == delay_days:
				continue
			frappe.db.set_value(
				"Presales Request", pre.name, {"overdue": overdue, "delay_days": delay_days}, update_modified=False
			)
			updated += 1
		except Exception:
			failed += 1
			frappe.log_error(title="Presales Request overdue scheduler", message=frappe.get_traceback())
	frappe.logger("bsgroup").info(
		f"calculate_due_date: scanned={scanned} updated={updated} failed={failed} today={today}"
	)
	return {"scanned": scanned, "updated": updated, "failed": failed}
