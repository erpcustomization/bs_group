import json

import frappe

BLOCKED_PRIOR_STATUSES = [
	"Pre-Implementation",
	"Project Planning",
	"Pending from Client",
	"Pending from Sales Account",
	"Pending from Implementation",
]


def validate_completion_from_blocked_status(doc, method=None):
	"""A Task cannot be marked Completed directly from a pre-execution status -
	it must first move to an active execution status."""

	if doc.is_new() or doc.status != "Completed":
		return

	previous_status = frappe.db.get_value("Task", doc.name, "status")
	if previous_status in BLOCKED_PRIOR_STATUSES:
		frappe.throw(
			"This task cannot be marked Completed directly from '" + previous_status + "'. "
			"Please move it to an active execution status (e.g. Implementation In Progress, "
			"Delivery in Progress, In House Testing) before marking it Completed."
		)


def validate_milestone_requirements(doc, method=None):
	"""A Milestone Task must carry a Project and an Expected End Date."""

	if not doc.is_milestone:
		return

	if not doc.project:
		frappe.throw("A Milestone Task must be linked to a Project before it can be saved.")
	if not doc.exp_end_date:
		frappe.throw("A Milestone Task must have an Expected End Date before it can be saved.")


def _is_zztest_task(doc):
	if not doc.project:
		return False
	project_name = frappe.db.get_value("Project", doc.project, "project_name") or ""
	return project_name.startswith("ZZTEST")


def validate_zztest_task_closure_authority(doc, method=None):
	"""ZZTEST POC v2: Task closure authority guard. Applies to Project Tasks
	AND Internal Tasks. GUARD: only Tasks whose Project is named ZZTEST*."""

	if not _is_zztest_task(doc) or doc.is_new():
		return

	before_status = frappe.db.get_value("Task", doc.name, "status")

	is_ops = frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Operations Manager"})
	is_pm = frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "Projects Manager"})
	is_sm = frappe.db.exists("Has Role", {"parent": frappe.session.user, "role": "System Manager"})
	is_override = bool(is_ops or is_pm or is_sm)

	if doc.status == "Completed" and before_status != "Completed":
		assigned = json.loads(frappe.db.get_value("Task", doc.name, "_assign") or "[]")
		if frappe.session.user not in assigned and not is_override:
			frappe.throw(
				"Only an engineer assigned to this Task may complete it. Operations Manager, "
				"Projects Manager or System Manager may override."
			)

		if not is_override:
			peers = []
			for f in ["task", "internal_task"]:
				for p in frappe.get_all(
					"Tech Task Scheduler List",
					filters={f: doc.name},
					fields=["name", "parent", "date", "resource", "custom_assignment_type", "status"],
				):
					if not any(q.get("name") == p.get("name") for q in peers):
						peers.append(p)

			active_peers = []
			for p in peers:
				if p.get("status") in ("Cancelled", "Cancelled/Reassigned"):
					continue
				pds = frappe.utils.cint(frappe.db.get_value("Tech Task Scheduler", p.get("parent"), "docstatus"))
				if pds != 1:
					continue
				active_peers.append(p)

			if len(active_peers) > 1:
				primaries = [
					p for p in active_peers
					if (p.get("custom_assignment_type") or "Primary") == "Primary"
				]
				if not primaries:
					frappe.throw("Shared Task has no Primary assignment. Operations must nominate a Primary engineer.")

				latest_date = None
				for p in primaries:
					d = frappe.utils.getdate(p.get("date"))
					if latest_date is None or d > latest_date:
						latest_date = d

				latest = [p for p in primaries if frappe.utils.getdate(p.get("date")) == latest_date]

				if latest[0].get("resource") != frappe.session.user:
					frappe.throw(
						"Only the engineer holding the latest active Primary assignment ("
						+ latest[0].get("resource") + ") may complete this shared Task. "
						"Secondary resources may log work and time but cannot close it."
					)

	if before_status == "Completed" and doc.status != "Completed":
		if not is_override:
			frappe.throw("Only Operations Manager, Projects Manager or System Manager may reopen a completed Task.")
		reason = frappe.form_dict.get("zz_poc_reason")
		if not reason:
			frappe.throw("A reason is mandatory when reopening or returning a completed Task.")


def sync_zztest_task_scheduler_status(doc, method=None):
	"""ZZTEST POC v2: status write-back to scheduler rows. Scheduler status is
	derived from the execution record and the underlying Task/Ticket ONLY - it
	is never derived from whether the Timesheet is Draft, Submitted or
	Cancelled."""

	if not _is_zztest_task(doc):
		return

	rows = []
	for f in ["task", "internal_task"]:
		for r in frappe.get_all("Tech Task Scheduler List", filters={f: doc.name}, fields=["name", "status"]):
			if not any(q.get("name") == r.get("name") for q in rows):
				rows.append(r)

	for r in rows:
		if r.get("status") in ("Cancelled", "Cancelled/Reassigned"):
			continue

		ex = frappe.db.get_value(
			"Scheduler Execution",
			{"scheduler_row": r.get("name")},
			["name", "actual_start", "actual_end", "blocker_category", "blocker_details", "operational_status"],
			as_dict=True,
		)

		if doc.status == "Completed":
			new_status = "Closed"
		elif not ex:
			new_status = "Scheduled"
		elif ex.get("operational_status") == "Cancelled":
			new_status = "Cancelled/Reassigned"
		elif ex.get("blocker_category") or ex.get("blocker_details"):
			new_status = "Pending/Blocked"
		elif ex.get("actual_end"):
			new_status = "Work Logged"
		elif ex.get("actual_start"):
			new_status = "In Progress"
		else:
			new_status = "Scheduled"

		if new_status != r.get("status"):
			frappe.db.set_value("Tech Task Scheduler List", r.get("name"), "status", new_status, update_modified=False)
