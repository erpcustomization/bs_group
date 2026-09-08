# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
import re
from frappe.model.document import Document
from frappe.utils import getdate, nowdate, now


class PresalesRequest(Document):
	SITE_VISIT_CLOSING_STATUSES = ("Completed", "Won", "Lost")
	EFFORT_LOGGING_CLOSING_STATUSES = ("Ready for Quotation", "Submitted to Sales", "Completed", "Won", "Lost")
	COMPLETION_DATE_STATUSES = ("Completed", "Won", "Lost")

	def validate(self):
		self._validate_site_visit_required()
		self._validate_effort_logged_before_closing()

	def autoname(self):
		if self.customer:
			customer = re.sub(r'[^a-zA-Z0-9\s]', '', self.customer)  # keep uppercase too
			customer = re.sub(r'\s+', '-', customer.strip())

			self.name = frappe.model.naming.make_autoname(f"PR-{customer}-.###")
	
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
    presales_requests = frappe.get_all(
        "Presales Request",
        fields=["name", "due_date"]
    )

    today = getdate(nowdate())

    for pre in presales_requests:
        if pre.due_date:
            due_date = getdate(pre.due_date)

            overdue = 1 if due_date < today else 0
            delay_days = (today - due_date).days if overdue else 0

            frappe.db.set_value(
                "Presales Request",
                pre.name,
                {
                    "overdue": overdue,
                    "delay_days": delay_days
                }
            )