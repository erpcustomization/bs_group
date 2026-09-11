# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# A recorded revision is immutable. The approval decision fields may only be
# written by the Approval Workspace service (bsgroup.api.dcs.approval), which
# writes them with frappe.db.set_value so no document hook and no direct edit
# can forge a decision. Ported from the production Server Scripts
# "DCS Revision - Immutability Guard" and "DCS Revision - Deletion Guard".

LOCKED_FIELDS = [
	"dcs", "revision_no", "changed_by", "changed_on", "source", "reason",
	"prev_total_cost", "prev_total_selling", "prev_margin_percent", "prev_concession_percent",
	"new_total_cost", "new_total_selling", "new_margin_percent", "new_concession_percent",
	"gp_movement", "margin_movement", "technical_impact", "approval_requirement", "margin_gate",
]
DECISION_FIELDS = ["approval_state", "decided_by", "decided_on", "decision_reason"]
FINAL_STATES = ["Approved", "Rejected"]


class DCSRevision(Document):
	def validate(self):
		prev = self.get_doc_before_save()
		if prev is None:
			# A revision is governed negotiation history and may only be created by
			# the revision service, which validates commercial authority and Deal
			# Cost Sheet permission before anything is recorded.
			if not self.flags.dcs_api_write:
				frappe.throw(
					"A DCS Revision may only be created by the revision service, which validates "
					"commercial authority and Deal Cost Sheet permission before recording anything. "
					"Direct creation of a revision is not permitted, because it would be forged "
					"negotiation history."
				)
			return

		for f in LOCKED_FIELDS:
			if str(prev.get(f)) != str(self.get(f)):
				frappe.throw(
					"DCS Revision " + str(self.name) + " is immutable. The field '" + str(f)
					+ "' cannot be changed after the revision is recorded."
				)
		for f in DECISION_FIELDS:
			if str(prev.get(f) or "") != str(self.get(f) or ""):
				frappe.throw(
					"The approval decision on DCS Revision " + str(self.name) + " cannot be written directly. "
					"The field '" + str(f) + "' is recorded only by the Approval Workspace, which enforces "
					"approval authority. Direct edits are refused so that no approval can be spoofed."
				)
		if prev.get("approval_state") in FINAL_STATES:
			frappe.throw(
				"DCS Revision " + str(self.name) + " already carries a final decision ("
				+ str(prev.get("approval_state")) + "). A recorded approval decision cannot be altered."
			)

	def on_trash(self):
		# Revision history is an audit trail. Entries are never removed.
		frappe.throw(
			"DCS Revision " + str(self.name) + " cannot be deleted. Negotiation history is an immutable "
			"audit trail. If the revision was recorded in error, record a corrective revision instead."
		)
