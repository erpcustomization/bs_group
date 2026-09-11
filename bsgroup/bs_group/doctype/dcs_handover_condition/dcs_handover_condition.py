# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

GOVERNED = [
	"state",
	"category",
	"original_category",
	"domain",
	"condition_title",
	"detail",
	"last_action_note",
	"assigned_to",
	"hold_state",
	"cleared_by",
	"cleared_on",
	"clearance_note",
	"accepted_by",
	"accepted_on",
	"acceptance_reason",
	"acknowledged",
	"exposure_amount",
	"exposure_note",
	"follow_up_date",
	"auto_generated",
	"source_key",
	"raised_by",
	"raised_on",
	"dcs",
	"condition_no",
]


class DCSHandoverCondition(Document):
	def before_save(self):
		# DCS Handover Condition - Accepted Risk Guard (Before Save)
		# An accepted risk retains its original blocker identity and can never be marked Clear.
		# The acceptance record is immutable once written.
		doc = self
		prev = doc.get_doc_before_save()

		if prev is not None:
			if prev.get("state") == "Accepted Risk":
				if doc.get("state") != "Accepted Risk":
					frappe.throw(
						"Handover condition "
						+ str(doc.name)
						+ " is a recorded ACCEPTED RISK. An accepted risk retains its "
						"original blocker and can never be marked Cleared or reopened. "
						"Raise a new condition instead."
					)
				locked = [
					"accepted_by",
					"accepted_on",
					"acceptance_reason",
					"acknowledged",
					"exposure_amount",
					"exposure_note",
					"follow_up_date",
					"original_category",
					"condition_title",
					"domain",
					"dcs",
					"condition_no",
				]
				for f in locked:
					if str(prev.get(f)) != str(doc.get(f)):
						frappe.throw(
							"Accepted risk "
							+ str(doc.name)
							+ " is immutable. The field '"
							+ str(f)
							+ "' cannot be changed after the risk was accepted."
						)
			if prev.get("state") == "Cleared":
				if doc.get("state") == "Accepted Risk":
					frappe.throw(
						"Handover condition "
						+ str(doc.name)
						+ " is already Cleared. A cleared condition cannot be converted "
						"into an accepted risk."
					)
			locked2 = ["dcs", "condition_no", "raised_by", "raised_on"]
			for f2 in locked2:
				if str(prev.get(f2)) != str(doc.get(f2)):
					frappe.throw(
						"Handover condition "
						+ str(doc.name)
						+ " identity is immutable. The field '"
						+ str(f2)
						+ "' cannot be changed."
					)

		if doc.get("state") == "Accepted Risk":
			if not doc.get("acceptance_reason"):
				frappe.throw("An accepted risk requires a written reason.")
			if not doc.get("acknowledged"):
				frappe.throw("An accepted risk requires an explicit acknowledgement.")
			if str(doc.get("original_category")) not in ["Blocker", "Watch Item"]:
				frappe.throw(
					"An accepted risk must retain the original condition category it "
					"was raised as."
				)

	def on_trash(self):
		# DCS Handover Condition - Deletion Guard (Before Delete)
		frappe.throw(
			"Handover condition "
			+ str(self.name)
			+ " cannot be deleted. Handover conditions and accepted risks are an "
			"immutable governance record. Clear it, or record a corrective "
			"condition instead."
		)

	def validate(self):
		# DCS Handover Condition - Governed Field Guard.
		# Conditions are raised, cleared and accepted only through the Award and Handover
		# Workspace, which sets doc.flags.dcs_api_write on the document it saves. Any
		# other edit path is refused.
		doc = self
		prev = doc.get_doc_before_save()

		if prev is None:
			# A condition is governed history. It may only be created by a DCS service,
			# each of which validates authority and Deal Cost Sheet permission before
			# raising anything.
			if doc.flags.get("dcs_api_write") != 1:
				frappe.throw(
					"A handover condition may only be raised by a governed Deal Cost "
					"Sheet service, which validates authority and Deal Cost Sheet "
					"permission first. Direct creation of a handover condition is not "
					"permitted."
				)
			if str(doc.get("state") or "") != "Open":
				frappe.throw(
					"A handover condition must be raised in the Open state. A "
					"condition cannot be created already cleared or already accepted "
					"as risk."
				)
			if (
				doc.get("cleared_by")
				or doc.get("cleared_on")
				or doc.get("accepted_by")
				or doc.get("accepted_on")
			):
				frappe.throw(
					"A handover condition cannot be created with a clearance or "
					"acceptance already recorded."
				)
		else:
			if doc.flags.get("dcs_api_write") != 1:
				changed = []
				for f in GOVERNED:
					if str(prev.get(f) or "") != str(doc.get(f) or ""):
						changed.append(f)
				if len(changed) > 0:
					frappe.throw(
						"These handover condition fields are governed by the Award and "
						"Handover Workspace and cannot be edited directly: "
						+ "; ".join(changed)
						+ ". Clearing a blocker, accepting a risk or reassigning a "
						"domain must go through the workspace so that authority is "
						"checked and the action is attributed."
					)
