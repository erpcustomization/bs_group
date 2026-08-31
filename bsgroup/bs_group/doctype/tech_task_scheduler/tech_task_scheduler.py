# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as assign_to_add
from frappe.desk.form.assign_to import remove as assign_to_remove
from frappe.model.document import Document

from bsgroup.overrides.timesheet import sync_task_status


class TechTaskScheduler(Document):

	def on_submit(self):
		validate_labor_count(self)
		sync_assignments(self)


def sync_assignments(doc):
	"""Keep the resource assignment and row status in sync.

	- When a row has a mapped resource, assign the underlying record to that
	  user and move the status from Open (or blank) to "Scheduled".
	- When a row is reverted from "Scheduled" back to "Open", cancel the
	  existing assignment and clear the resource so the task becomes
	  unassigned and available for rescheduling.
	"""

	before = doc.get_doc_before_save()
	prev_status = {}
	if before:
		for prev_row in before.tech_task_scheduler_list:
			prev_status[prev_row.name] = prev_row.status

	for row in doc.tech_task_scheduler_list:

		target_doctype, target_name = get_row_target(row)
		reverted = prev_status.get(row.name) == "Scheduled" and row.status == "Open"

		if reverted:
			# Scheduled -> Open : unassign and free the row for rescheduling
			if row.resource and target_doctype and target_name:
				unassign_document(target_doctype, target_name, row.resource)

			if row.resource:
				frappe.db.set_value(
					"Tech Task Scheduler List",
					row.name,
					"resource",
					None,
					update_modified=False,
				)
				row.resource = None
			continue

		# Reflect this row's status on its linked Task, however it was set -
		# a manager editing the row directly (and submitting) should sync
		# just like the Timesheet path does.
		if target_doctype == "Task" and target_name and row.status:
			sync_task_status(target_name, row.status)

		if not row.resource:
			continue

		# Assign the underlying record (Project Task / HD Ticket) to the resource
		if target_doctype and target_name:
			assign_document(target_doctype, target_name, row.resource)

		# Mark the task as Scheduled once it is assigned
		if row.status in (None, "", "Open"):
			frappe.db.set_value(
				"Tech Task Scheduler List",
				row.name,
				"status",
				"Scheduled",
				update_modified=False,
			)
			row.status = "Scheduled"


def get_row_target(row):
	"""Return (doctype, name) of the record a row maps to, or (None, None)."""

	if row.category == "Project" and row.task:
		return "Task", row.task

	if row.category == "HD Ticket" and row.category_name:
		return "HD Ticket", row.category_name

	return None, None


def assign_document(doctype, name, user):
	"""Assign `user` to the given document, skipping if already assigned."""

	if not name or not frappe.db.exists(doctype, name):
		return

	already_assigned = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doctype,
			"reference_name": name,
			"allocated_to": user,
			"status": ["!=", "Cancelled"],
		},
		limit=1,
	)

	if already_assigned:
		return

	assign_to_add({
		"assign_to": [user],
		"doctype": doctype,
		"name": name,
	})

	share_document(doctype, name, user)


def share_document(doctype, name, user):
	"""Share the document with `user`, skipping if already shared."""

	if frappe.db.exists(
		"DocShare",
		{"share_doctype": doctype, "share_name": name, "user": user},
	):
		return

	frappe.share.add_docshare(
		doctype,
		name,
		user,
		read=1,
		write=1,
		notify=0,
		flags={"ignore_share_permission": True},
	)


def unassign_document(doctype, name, user):
	"""Cancel `user`'s assignment on the given document, if one exists."""

	if not name or not frappe.db.exists(doctype, name):
		return

	assigned = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": doctype,
			"reference_name": name,
			"allocated_to": user,
			"status": ["!=", "Cancelled"],
		},
		limit=1,
	)

	if not assigned:
		return

	assign_to_remove(doctype, name, user, ignore_permissions=True)

	unshare_document(doctype, name, user)


def unshare_document(doctype, name, user):
	"""Revoke `user`'s share on the given document, if one exists."""

	if not frappe.db.exists(
		"DocShare",
		{"share_doctype": doctype, "share_name": name, "user": user},
	):
		return

	frappe.share.remove(doctype, name, user)


def validate_labor_count(doc):
	"""Enforce the approved labor count per (category, reference, task).

	A Project can have several Labor Preapprovals against it - one per Task -
	each with its own independent budget. Scoping only by `reference` (the
	Project/Ticket) would pool every Task's approval into one shared number
	and let one Task's allocation eat into another Task's budget, and would
	also silently skip validating every Task after the first one seen for
	the same reference. Scoping by (category, reference, task) keeps each
	Task's Labor Preapproval - and its remaining balance - independent, the
	way multiple LPREs against one Project/different Tasks are meant to work.
	HD Ticket-sourced rows have no task, so `task` collapses to None there
	and the whole ticket acts as the scope, as before.
	"""

	checked_scopes = []

	for row in doc.tech_task_scheduler_list:

		if row.category not in ("Project", "HD Ticket") or not row.category_name:
			continue

		reference = row.category_name
		task = row.task if row.category == "Project" else None
		scope = (row.category, reference, task)

		if scope in checked_scopes:
			continue

		checked_scopes.append(scope)

		def _same_scope(d):
			d_task = d.task if row.category == "Project" else None
			return d.category == row.category and d.category_name == reference and d_task == task

		any_allocation_for_scope = any(
			(d.allocated_labor or 0) > 0
			for d in doc.tech_task_scheduler_list
			if _same_scope(d)
		)

		lpre_filters = {
			"source": row.category,
			"reference": reference,
			"docstatus": 1,
			"workflow_state": "Approved",
		}
		if row.category == "Project":
			lpre_filters["task"] = task

		if any_allocation_for_scope:
			# Outsourced labor is being allocated against this row - an Approved
			# Labor Preapproval is mandatory. Draft/Pending/Rejected LPREs (or none
			# at all) must hard-block; only Approved (docstatus=1) authorizes scheduling.
			any_lpre_filters = {"source": row.category, "reference": reference}
			if row.category == "Project":
				any_lpre_filters["task"] = task
			any_lpre_exists = frappe.db.exists("Labor Preapproval", any_lpre_filters)

			labor_preapprovals = frappe.get_all(
				"Labor Preapproval", filters=lpre_filters, fields=["name", "total_persons"]
			)

			if not labor_preapprovals:
				scope_label = f"{reference} / {task}" if task else reference
				if any_lpre_exists:
					frappe.throw(_(
						"Cannot allocate outsourced labor for {0} {1}: the linked Labor "
						"Preapproval exists but is not Approved."
					).format(row.category, scope_label))
				frappe.throw(_(
					"Cannot allocate outsourced labor for {0} {1}: no Approved Labor "
					"Preapproval found."
				).format(row.category, scope_label))
		else:
			labor_preapprovals = frappe.get_all(
				"Labor Preapproval", filters=lpre_filters, fields=["name", "total_persons"]
			)
			if not labor_preapprovals:
				continue

		approved_count = sum(
			(d.total_persons or 0)
			for d in labor_preapprovals
		)

		task_condition = "AND tsl.task = %(task)s" if task else "AND (tsl.task IS NULL OR tsl.task = '')"
		existing_used = frappe.db.sql(f"""
			SELECT COALESCE(SUM(tsl.allocated_labor), 0)
			FROM `tabTech Task Scheduler List` tsl
			INNER JOIN `tabTech Task Scheduler` ts
				ON ts.name = tsl.parent
			WHERE tsl.category_name = %(reference)s
			{task_condition}
			AND ts.name != %(doc_name)s
			AND ts.docstatus = 1
		""", {"reference": reference, "task": task, "doc_name": doc.name})[0][0]

		current_doc_used = sum(
			(d.allocated_labor or 0)
			for d in doc.tech_task_scheduler_list
			if _same_scope(d)
		)

		total_used = existing_used + current_doc_used
		remaining = approved_count - total_used

		if total_used > approved_count:

			scope_label = f"{reference} / {task}" if task else reference
			frappe.throw(_(
				"Approved labor count exceeded for {0} {1}.<br><br>"
				"Approved Count : {2}<br>"
				"Already Used : {3}<br>"
				"Current Allocation : {4}<br>"
				"Over By : {5}"
			).format(
				row.category,
				scope_label,
				approved_count,
				existing_used,
				current_doc_used,
				total_used - approved_count
			))

		for lp in labor_preapprovals:
			frappe.db.set_value(
				"Labor Preapproval",
				lp.name,
				"remaining_persons",
				remaining
			)