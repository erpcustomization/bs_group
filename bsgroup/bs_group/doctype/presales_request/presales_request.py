# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
import re
from frappe.model.document import Document
from frappe.utils import getdate, nowdate, now


class PresalesRequest(Document):
	def validate(self):
		if self.site_visit_required and not self.site_visit:
			frappe.throw(frappe._("Site Visit is mandatory when Site Visit Required is checked"))

	def autoname(self):
		if self.customer:
			customer = re.sub(r'[^a-zA-Z0-9\s]', '', self.customer)  # keep uppercase too
			customer = re.sub(r'\s+', '-', customer.strip())

			self.name = frappe.model.naming.make_autoname(f"PR-{customer}-.###")
	
	def before_save(self):
		calculate_quality_score(self)

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