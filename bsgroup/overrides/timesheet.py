import frappe
from erpnext.projects.doctype.timesheet.timesheet import Timesheet


class CustomTimesheet(Timesheet):
	def on_update(self):
		sync_tech_task_scheduler_status(self)

	def validate_time_logs(self):
		for time_log in self.time_logs:
			time_log.set_to_time()
			# self.validate_overlap(time_log)  # disabled: overlap restriction not required
			time_log.set_project()
			time_log.validate_parent_project(self.parent_project)
			time_log.validate_task_project()

	def update_task_and_project(self):
		tasks, projects = [], []

		for data in self.time_logs:
			if data.task and data.task not in tasks:
				task = frappe.get_doc("Task", data.task)
				task.update_time_and_costing()

				time_logs_completed = all(tl.completed for tl in self.time_logs if tl.task == task.name)
				if time_logs_completed:
					task.status = "Completed"
				# skip setting "Working" — status stays as-is when not all logs are completed

				task.save(ignore_permissions=True)
				tasks.append(data.task)

			if data.project and data.project not in projects:
				projects.append(data.project)

		for project in projects:
			project_doc = frappe.get_doc("Project", project)
			project_doc.update_project()
			project_doc.save(ignore_permissions=True)


def sync_tech_task_scheduler_status(doc):
	"""Push the status set on each Timesheet line back to the matching
	Tech Task Scheduler task(s).

	A Timesheet line is matched to a Tech Task Scheduler List row on:
	  - resource            == the Timesheet user or its creator (owner)
	  - category            == line.custom_reference_type  (Project / HD Ticket)
	  - category_name       == line.custom_reference        (the Project / HD Ticket)
	  - task                == line.task                    (only when the line has a task)

	A System Manager may update any Timesheet: when the person saving/submitting
	holds that role, the resource restriction is skipped and matching is done on
	category / reference / task alone.

	All matching rows are updated. Cancelled scheduler documents are skipped.
	Runs on every save and on submit.
	"""

	# A System Manager can manage any task, so they are not restricted to their
	# own assignments. Everyone else only affects tasks assigned to them - the
	# assigned resource may be recorded either as the Timesheet's `user` or as
	# its creator (`owner`), e.g. when the sheet is filed while impersonating.
	is_system_manager = "System Manager" in frappe.get_roles()
	resources = list({r for r in (doc.user, doc.owner) if r})
	if not is_system_manager and not resources:
		return

	for row in doc.time_logs:
		sync_row_status(row, is_system_manager, resources)


def sync_row_status_on_change(doc, method=None):
	"""doc_events hook for Timesheet Detail's own `on_change`.

	Grid "quick edit" / `frappe.client.set_value` updates a Timesheet Detail
	row directly via `db_set`, which never calls the parent Timesheet's
	`on_update` - so the Tech Task Scheduler / Task sync above is skipped.
	This mirrors that logic for a single row so inline edits sync too.
	"""

	parent = frappe.db.get_value("Timesheet", doc.parent, ["user", "owner"], as_dict=True)
	if not parent:
		return

	is_system_manager = "System Manager" in frappe.get_roles()
	resources = list({r for r in (parent.user, parent.owner) if r})
	if not is_system_manager and not resources:
		return

	sync_row_status(doc, is_system_manager, resources)


# Tech Task Scheduler List's `category` is a display label, not always the
# linked doctype's name (e.g. "Presales" rows link to "Presales Request").
# Timesheet Detail's custom_reference_type stores the doctype name, so it
# must be translated before filtering on `category`. Keep in sync with
# CATEGORY_DOCTYPE_MAP in tech_task_scheduler.js.
REFERENCE_DOCTYPE_TO_CATEGORY = {
	"Presales Request": "Presales",
}


def sync_row_status(row, is_system_manager, resources):
	status = row.custom_status
	ref_type = row.custom_reference_type
	ref_name = row.custom_reference

	if not (status and ref_type and ref_name):
		return

	category = REFERENCE_DOCTYPE_TO_CATEGORY.get(ref_type, ref_type)

	filters = {
		"category": category,
		"category_name": ref_name,
	}
	if not is_system_manager:
		filters["resource"] = ["in", resources]
	if row.task:
		filters["task"] = row.task

	matches = frappe.get_all(
		"Tech Task Scheduler List",
		filters=filters,
		fields=["name", "parent", "status"],
	)

	for match in matches:
		# skip rows belonging to a cancelled Tech Task Scheduler
		if frappe.db.get_value("Tech Task Scheduler", match.parent, "docstatus") == 2:
			continue

		values = {}
		if match.status != status:
			values["status"] = status

		# Pending Details is mandatory on the scheduler row when status is Pending -
		# carry over the Timesheet line's description as that explanation.
		if status == "Pending" and row.description:
			values["pending_details"] = row.description

		if values:
			frappe.db.set_value(
				"Tech Task Scheduler List",
				match.name,
				values,
				update_modified=False,
			)

	# Reflect the same status on the linked Project Task (never HD Tickets)
	if ref_type == "Project" and row.task and matches:
		sync_task_status(row.task, status)


# Map the shared scheduler/timesheet status onto the Task doctype's own options.
# Only "Pending" differs ("Pending" on Task); the rest are identical.
TASK_STATUS_MAP = {
	"Open": "Open",
	"Working": "Working",
	"Pending": "Pending",
	"Completed": "Completed",
	"Overdue": "Overdue",
	"Cancelled": "Cancelled",
}


def sync_task_status(task, status):
	"""Set the Task's status from a Timesheet line status, if it changed."""

	task_status = TASK_STATUS_MAP.get(status)
	if not task_status or not frappe.db.exists("Task", task):
		return

	if frappe.db.get_value("Task", task, "status") != task_status:
		frappe.db.set_value("Task", task, "status", task_status, update_modified=False)


def sync_scheduler_execution_link_on_submit(doc, method=None):
	# ZZTEST POC - FIX 5: Timesheet link sync (After Submit)
	# Relinks Scheduler Execution and scheduler rows to this Timesheet (including an amended one).
	# Financial status NEVER changes operational status - only timesheet_condition is updated.
	if (doc.title or "").startswith("ZZTEST") and frappe.utils.cint(doc.docstatus) != 2:
		for d in doc.time_logs:
			if d.custom_reference_type == "Scheduler Execution" and d.custom_reference:
				if not frappe.db.exists("Scheduler Execution", d.custom_reference):
					continue
				cur_ts = frappe.db.get_value("Scheduler Execution", d.custom_reference, "timesheet")
				if cur_ts and cur_ts != doc.name:
					cur_ds = frappe.utils.cint(frappe.db.get_value("Timesheet", cur_ts, "docstatus") or 0)
					if cur_ds != 2:
						continue
				frappe.db.set_value("Scheduler Execution", d.custom_reference, "timesheet", doc.name, update_modified=False)
				frappe.db.set_value("Scheduler Execution", d.custom_reference, "timesheet_detail", d.name, update_modified=False)
				frappe.db.set_value("Scheduler Execution", d.custom_reference, "timesheet_condition", "Submitted", update_modified=False)


def sync_scheduler_execution_link_on_save(doc, method=None):
	# ZZTEST POC - FIX 5: Timesheet link sync (After Save)
	# Relinks Scheduler Execution and scheduler rows to this Timesheet (including an amended one).
	# Financial status NEVER changes operational status - only timesheet_condition is updated.
	if (doc.title or "").startswith("ZZTEST") and frappe.utils.cint(doc.docstatus) != 2:
		for d in doc.time_logs:
			if d.custom_reference_type == "Scheduler Execution" and d.custom_reference:
				if not frappe.db.exists("Scheduler Execution", d.custom_reference):
					continue
				cur_ts = frappe.db.get_value("Scheduler Execution", d.custom_reference, "timesheet")
				if cur_ts and cur_ts != doc.name:
					cur_ds = frappe.utils.cint(frappe.db.get_value("Timesheet", cur_ts, "docstatus") or 0)
					if cur_ds != 2:
						continue
				frappe.db.set_value("Scheduler Execution", d.custom_reference, "timesheet", doc.name, update_modified=False)
				frappe.db.set_value("Scheduler Execution", d.custom_reference, "timesheet_detail", d.name, update_modified=False)
				frappe.db.set_value("Scheduler Execution", d.custom_reference, "timesheet_condition", "OK", update_modified=False)


def release_scheduler_execution_before_cancel(doc, method=None):
	# ZZTEST POC - FIX 5: Timesheet cancellation support (Before Cancel)
	# Clears the operational links to this Timesheet BEFORE Frappe runs its back-link check,
	# so cancellation no longer fails with LinkExistsError and users never have to clear links by hand.
	# It preserves traceability and NEVER changes Task, Ticket, Internal Task or scheduler operational status.
	if (doc.title or "").startswith("ZZTEST"):
		touched = []
		for d in doc.time_logs:
			if d.custom_reference_type == "Scheduler Execution" and d.custom_reference:
				if not frappe.db.exists("Scheduler Execution", d.custom_reference):
					continue
				ed = frappe.get_doc("Scheduler Execution", d.custom_reference)
				trace = ed.get("cancelled_timesheets") or ""
				entry = doc.name + " (row " + str(d.name) + ", " + str(d.hours) + "h) cancelled by " + frappe.session.user + " on " + frappe.utils.now()
				ed.cancelled_timesheets = (trace + "\n" + entry).strip()
				ed.timesheet = None
				ed.timesheet_detail = None
				ed.timesheet_condition = "Cancelled - Correction Required"
				ed.flags.scheduler_execution_action = "update_work"
				ed.flags.ignore_permissions = True
				ed.save()
				touched.append(ed.name)
		# also release any Scheduler Execution rows that still point at this Timesheet
		for e in frappe.get_all("Scheduler Execution", filters={"timesheet": doc.name}, fields=["name"]):
			frappe.db.set_value("Scheduler Execution", e.get("name"), "timesheet", None, update_modified=False)
			frappe.db.set_value("Scheduler Execution", e.get("name"), "timesheet_detail", None, update_modified=False)
			frappe.db.set_value("Scheduler Execution", e.get("name"), "timesheet_condition", "Cancelled - Correction Required", update_modified=False)
