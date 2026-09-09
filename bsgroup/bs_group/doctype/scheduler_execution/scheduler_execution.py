# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

PROTECTED_FIELD_GROUPS = {
	"immutable": [
		"scheduler", "scheduler_row", "company", "resource", "employee", "execution_title",
		"date", "category", "category_name", "activity_details", "assignment_type",
		"planned_start", "planned_end", "planned_hours", "team", "location", "project",
		"task", "ticket", "previous_execution", "next_execution",
	],
	"technician": [
		"actual_start", "actual_end", "actual_hours", "work_completed", "work_pending",
		"work_outcome", "blocker_category", "blocker_details", "blocker_owner",
		"follow_up_required", "follow_up_date", "completion_evidence", "completion_note",
	],
	"lifecycle": ["operational_status", "verification_status", "awaiting_verification_on"],
	"supervisor": [
		"verified_by", "verification_date", "supervisor_comment", "productive_category", "billable",
	],
}

PROTECTED_FIELDS = [f for group in PROTECTED_FIELD_GROUPS.values() for f in group]
IMMUTABLE_FIELDS = PROTECTED_FIELD_GROUPS["immutable"]

ACTION_FIELD_MAP = {
	"start_work": ["operational_status", "actual_start", "work_outcome"],
	"mark_blocked": ["operational_status", "blocker_category", "blocker_details", "blocker_owner", "follow_up_required", "follow_up_date"],
	"resume_work": ["operational_status", "work_outcome", "blocker_category", "blocker_details", "blocker_owner"],
	"submit_for_verification": [
		"operational_status", "verification_status", "actual_end", "actual_hours", "work_completed",
		"work_pending", "work_outcome", "follow_up_required", "follow_up_date", "completion_evidence",
		"awaiting_verification_on", "verified_by", "verification_date",
	],
	"correct_work": ["operational_status", "actual_end", "actual_hours", "work_outcome"],
	"verify_execution": ["operational_status", "verification_status", "verified_by", "verification_date", "supervisor_comment", "productive_category", "billable"],
	"reject_for_correction": ["verification_status", "verified_by", "verification_date", "supervisor_comment"],
	"close_execution": ["operational_status"],
	"update_work": [
		"operational_status", "actual_start", "actual_end", "actual_hours", "work_completed",
		"work_pending", "work_outcome", "completion_note", "blocker_category", "blocker_details",
		"blocker_owner", "follow_up_required", "follow_up_date", "completion_evidence",
	],
	"ops_override": ["operational_status"],
}

RESERVED_SUPERVISOR_ACTIONS = ["verify_execution", "reject_for_correction", "close_execution"]
OPS_OVERRIDE_ACTIONS = ["ops_override"]
TECHNICIAN_ACTIONS = ["start_work", "mark_blocked", "resume_work", "submit_for_verification", "correct_work", "update_work"]

DATE_TYPE_FIELDS = ["date", "follow_up_date"]
DATETIME_TYPE_FIELDS = ["actual_start", "actual_end", "awaiting_verification_on", "verification_date"]
TIME_TYPE_FIELDS = ["planned_start", "planned_end"]


class SchedulerExecution(Document):
	def before_cancel(self):
		# Document.cancel() never calls validate() - only before_cancel - so the
		# no-cancellation business rule must live here too, not only in validate(),
		# or a plain doc.cancel() call would silently succeed.
		frappe.throw("Scheduler Execution records cannot be cancelled. The approved lifecycle has no cancellation action.")

	def validate(self):
		before = self.get_doc_before_save()

		current_docstatus = frappe.utils.cint(self.docstatus)
		previous_docstatus = frappe.utils.cint(before.get("docstatus")) if before else 0

		if not before and current_docstatus != 0:
			frappe.throw("New Scheduler Execution must be created as a draft.")

		if current_docstatus == 2 and previous_docstatus != 2:
			frappe.throw("Scheduler Execution records cannot be cancelled. The approved lifecycle has no cancellation action.")

		if current_docstatus == 1 and previous_docstatus == 0:
			if self.operational_status != "Closed" or self.verification_status != "Verified":
				frappe.throw(
					"A Scheduler Execution may only be submitted by the approved Close action after "
					"supervisor verification. Current operational_status: %s. Current verification_status: %s."
					% (self.operational_status, self.verification_status)
				)

		if not before:
			self._validate_new_execution()
		else:
			self._validate_protected_fields(before)

	def _validate_new_execution(self):
		doc = self

		if doc.operational_status != "Scheduled":
			frappe.throw("New Scheduler Execution must be created with operational_status = Scheduled.")

		if doc.verification_status != "Pending Verification":
			frappe.throw("New Scheduler Execution must be created with verification_status = Pending Verification.")

		if doc.actual_start:
			frappe.throw("New Scheduler Execution must be created with actual_start blank.")

		if doc.actual_end:
			frappe.throw("New Scheduler Execution must be created with actual_end blank.")

		if doc.actual_hours:
			frappe.throw("New Scheduler Execution must be created with actual_hours blank.")

		if doc.awaiting_verification_on:
			frappe.throw("New Scheduler Execution must be created with awaiting_verification_on blank.")

		if doc.verified_by:
			frappe.throw("New Scheduler Execution must be created with verified_by blank.")

		if doc.verification_date:
			frappe.throw("New Scheduler Execution must be created with verification_date blank.")

		if doc.supervisor_comment:
			frappe.throw("New Scheduler Execution must be created with supervisor_comment blank.")

		if not doc.scheduler:
			frappe.throw("New Scheduler Execution must reference a Tech Task Scheduler.")

		if not doc.scheduler_row:
			frappe.throw("New Scheduler Execution must reference a Tech Task Scheduler row.")

		parent_docstatus = frappe.db.get_value("Tech Task Scheduler", doc.scheduler, "docstatus")
		if parent_docstatus is None:
			frappe.throw("Tech Task Scheduler %s does not exist." % doc.scheduler)

		if frappe.utils.cint(parent_docstatus) != 1:
			frappe.throw("New Scheduler Execution requires a submitted Tech Task Scheduler. %s is not submitted." % doc.scheduler)

		row_parent = frappe.db.get_value("Tech Task Scheduler List", doc.scheduler_row, "parent")
		if not row_parent:
			frappe.throw("Scheduler row %s does not exist." % doc.scheduler_row)

		if row_parent != doc.scheduler:
			frappe.throw("Scheduler row %s does not belong to Tech Task Scheduler %s." % (doc.scheduler_row, doc.scheduler))

		existing_execution = frappe.db.exists("Scheduler Execution", {"scheduler_row": doc.scheduler_row})
		if existing_execution:
			frappe.throw("Scheduler Execution %s already exists for scheduler row %s." % (existing_execution, doc.scheduler_row))

	def _validate_protected_fields(self, before):
		doc = self

		changed = []
		for field_name in PROTECTED_FIELDS:
			before_value = before.get(field_name)
			after_value = doc.get(field_name)

			if field_name in DATE_TYPE_FIELDS:
				if before_value:
					before_value = frappe.utils.getdate(before_value)
				if after_value:
					after_value = frappe.utils.getdate(after_value)
			elif field_name in DATETIME_TYPE_FIELDS:
				if before_value:
					before_value = frappe.utils.get_datetime(before_value)
				if after_value:
					after_value = frappe.utils.get_datetime(after_value)
			elif field_name in TIME_TYPE_FIELDS:
				if before_value:
					before_value = frappe.utils.get_time(before_value)
				if after_value:
					after_value = frappe.utils.get_time(after_value)

			if before_value != after_value:
				changed.append(field_name)

		if not changed:
			return

		action = doc.flags.get("scheduler_execution_action")

		if not action or action not in ACTION_FIELD_MAP:
			frappe.throw("Cannot change protected field(s) without an approved action: %s" % ", ".join(changed))

		allowed = ACTION_FIELD_MAP.get(action)

		not_allowed = [f for f in changed if f not in allowed]
		if not_allowed:
			frappe.throw("Action '%s' is not permitted to change: %s" % (action, ", ".join(not_allowed)))

		immutable_violation = [f for f in changed if f in IMMUTABLE_FIELDS]
		if immutable_violation:
			frappe.throw("Action '%s' cannot change immutable planning/reference field(s): %s" % (action, ", ".join(immutable_violation)))

		if action in TECHNICIAN_ACTIONS:
			if frappe.session.user != doc.resource:
				if not frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "System Manager"}):
					frappe.throw("You are not authorised to perform this action on this Scheduler Execution.")

		if action in OPS_OVERRIDE_ACTIONS:
			is_ops_mgr = frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Operations Manager"})
			is_proj_mgr = frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Projects Manager"})
			is_sys_mgr = frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "System Manager"})
			if not (is_ops_mgr or is_proj_mgr or is_sys_mgr):
				frappe.throw("Only Operations Manager, Projects Manager or System Manager may perform an operations override on a Scheduler Execution.")

		if action in RESERVED_SUPERVISOR_ACTIONS:
			is_ops_manager = frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Operations Manager"})
			is_system_manager = frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "System Manager"})
			if not is_ops_manager and not is_system_manager:
				frappe.throw("Only Operations Manager or System Manager may perform supervisor action '%s'." % action)

		action_validator = getattr(self, f"_validate_action_{action}", None)
		if action_validator:
			action_validator(before, changed)

	def _validate_action_start_work(self, before, changed):
		doc = self
		if before.get("operational_status") != "Scheduled":
			frappe.throw("Start Work requires the previous operational_status to be Scheduled.")
		if doc.operational_status != "In Progress":
			frappe.throw("Start Work must set operational_status to In Progress.")
		if before.get("actual_start"):
			frappe.throw("Start Work requires actual_start to have been blank before this action.")
		if not doc.actual_start:
			frappe.throw("Start Work must populate actual_start.")

	def _validate_action_mark_blocked(self, before, changed):
		doc = self
		if before.get("operational_status") != "In Progress":
			frappe.throw("Mark Blocked requires the previous operational_status to be In Progress.")
		if doc.operational_status != "Blocked":
			frappe.throw("Mark Blocked must set operational_status to Blocked.")
		if "blocker_category" not in changed:
			# blocker_category is a Select with no blank first option, so Frappe
			# silently defaults it at doc-creation time - a plain truthiness
			# check can never catch a genuinely-missing value; it must have
			# actually changed as part of this action.
			frappe.throw("Mark Blocked requires blocker_category.")
		if not doc.blocker_details:
			frappe.throw("Mark Blocked requires blocker_details.")
		if doc.follow_up_required and not doc.follow_up_date:
			frappe.throw("Mark Blocked requires follow_up_date when follow_up_required is checked.")
		if not doc.follow_up_required and doc.follow_up_date:
			frappe.throw("Mark Blocked requires follow_up_date to be blank when follow_up_required is not checked.")

	def _validate_action_resume_work(self, before, changed):
		doc = self
		if before.get("operational_status") != "Blocked":
			frappe.throw("Resume Work requires the previous operational_status to be Blocked.")
		if doc.operational_status != "In Progress":
			frappe.throw("Resume Work must set operational_status to In Progress.")
		if doc.actual_end:
			frappe.throw("Resume Work requires actual_end to remain blank.")

	def _validate_action_submit_for_verification(self, before, changed):
		doc = self
		if before.get("operational_status") != "In Progress":
			frappe.throw("Submit for Verification requires the previous operational_status to be In Progress.")
		if doc.operational_status != "Awaiting Verification":
			frappe.throw("Submit for Verification must set operational_status to Awaiting Verification.")
		if before.get("verification_status") not in ("Pending Verification", "Rejected for Correction"):
			frappe.throw("Submit for Verification requires the previous verification_status to be Pending Verification or Rejected for Correction.")
		if doc.verification_status != "Pending Verification":
			frappe.throw("Submit for Verification must set verification_status to Pending Verification.")
		if not before.get("actual_start"):
			frappe.throw("Submit for Verification requires actual_start to already exist.")
		if not doc.actual_end:
			frappe.throw("Submit for Verification requires actual_end to be populated.")

		start_time = frappe.utils.get_datetime(doc.actual_start)
		end_time = frappe.utils.get_datetime(doc.actual_end)
		if end_time <= start_time:
			frappe.throw("Submit for Verification requires actual_end to be later than actual_start.")

		if doc.actual_hours is None or doc.actual_hours < 0:
			frappe.throw("Submit for Verification requires actual_hours to be zero or greater.")
		if not doc.work_completed:
			frappe.throw("Submit for Verification requires work_completed.")
		if "work_outcome" not in changed:
			# work_outcome is a Select with no blank first option ("Fully Completed"),
			# so it is always already populated by doc-creation-time defaulting -
			# require it to have actually changed as part of this action.
			frappe.throw("Submit for Verification requires work_outcome.")
		if not doc.completion_evidence:
			frappe.throw("Submit for Verification requires completion_evidence.")
		if doc.work_outcome not in ("Fully Completed", "Cancelled by Operations") and not doc.work_pending:
			frappe.throw("Submit for Verification requires work_pending when work_outcome is not Fully Completed or Cancelled by Operations.")
		if doc.follow_up_required and not doc.follow_up_date:
			frappe.throw("Submit for Verification requires follow_up_date when follow_up_required is checked.")
		if not doc.follow_up_required and doc.follow_up_date:
			frappe.throw("Submit for Verification requires follow_up_date to be blank when follow_up_required is not checked.")
		if not doc.awaiting_verification_on:
			frappe.throw("Submit for Verification requires awaiting_verification_on to be populated.")

	def _validate_action_correct_work(self, before, changed):
		doc = self
		if before.get("operational_status") != "Awaiting Verification":
			frappe.throw("Correct Work requires the previous operational_status to be Awaiting Verification.")
		if before.get("verification_status") != "Rejected for Correction":
			frappe.throw("Correct Work requires the previous verification_status to be Rejected for Correction.")
		if doc.operational_status != "In Progress":
			frappe.throw("Correct Work must set operational_status to In Progress.")
		if not before.get("supervisor_comment"):
			frappe.throw("Correct Work requires supervisor_comment to already exist.")
		if doc.actual_end:
			frappe.throw("Correct Work requires actual_end to be cleared.")
		if doc.actual_hours:
			frappe.throw("Correct Work requires actual_hours to be cleared.")
		if not doc.actual_start:
			frappe.throw("Correct Work requires actual_start to remain populated.")

	def _validate_action_verify_execution(self, before, changed):
		doc = self
		if before.get("operational_status") != "Awaiting Verification":
			frappe.throw("Verify requires the previous operational_status to be Awaiting Verification.")
		if before.get("verification_status") != "Pending Verification":
			frappe.throw("Verify requires the previous verification_status to be Pending Verification.")
		if doc.operational_status != "Completed":
			frappe.throw("Verify must set operational_status to Completed.")
		if doc.verification_status != "Verified":
			frappe.throw("Verify must set verification_status to Verified.")
		if not doc.verified_by:
			frappe.throw("Verify must populate verified_by.")
		if doc.verified_by != frappe.session.user:
			frappe.throw("verified_by must match the acting supervisor.")
		if not doc.verification_date:
			frappe.throw("Verify must populate verification_date.")
		if "productive_category" not in changed:
			# productive_category is a Select with no blank first option ("Productive"),
			# so it is always already populated by doc-creation-time defaulting -
			# require it to have actually changed as part of this action.
			frappe.throw("Verify requires productive_category.")
		if doc.resource and doc.verified_by == doc.resource:
			frappe.throw("A technician cannot verify their own Scheduler Execution.")

	def _validate_action_reject_for_correction(self, before, changed):
		doc = self
		if before.get("operational_status") != "Awaiting Verification":
			frappe.throw("Reject for Correction requires the previous operational_status to be Awaiting Verification.")
		if before.get("verification_status") != "Pending Verification":
			frappe.throw("Reject for Correction requires the previous verification_status to be Pending Verification.")
		if doc.verification_status != "Rejected for Correction":
			frappe.throw("Reject for Correction must set verification_status to Rejected for Correction.")
		if doc.operational_status != "Awaiting Verification":
			frappe.throw("Reject for Correction must leave operational_status as Awaiting Verification.")
		if not doc.supervisor_comment:
			frappe.throw("Reject for Correction requires supervisor_comment.")
		if not doc.verified_by:
			frappe.throw("Reject for Correction must populate verified_by.")
		if doc.verified_by != frappe.session.user:
			frappe.throw("verified_by must match the acting supervisor.")
		if not doc.verification_date:
			frappe.throw("Reject for Correction must populate verification_date.")
		if doc.resource and doc.verified_by == doc.resource:
			frappe.throw("A technician cannot reject their own Scheduler Execution.")

	def _validate_action_close_execution(self, before, changed):
		doc = self
		if before.get("operational_status") != "Completed":
			frappe.throw("Close requires the previous operational_status to be Completed.")
		if before.get("verification_status") != "Verified":
			frappe.throw("Close requires verification_status to be Verified.")
		if doc.operational_status != "Closed":
			frappe.throw("Close must set operational_status to Closed.")
		if not before.get("verified_by"):
			frappe.throw("Close requires verified_by to already exist.")
		if not before.get("verification_date"):
			frappe.throw("Close requires verification_date to already exist.")
