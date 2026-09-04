# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class LaborPreapproval(Document):
	def validate(self):
		self.validate_source()
		self.set_company()
		self.validate_labor_lines()
		self.calculate_totals()
		self.validate_self_approval()

	def before_insert(self):
		if self.amended_from:
			block_delete_and_amend_unless_system_manager(self, "amend")

		# A duplicated/amended LPRE starts with zero Scheduler allocation and
		# zero Attendance against it - these are carry-over values from the
		# source document and must not survive into the new one (belt and
		# suspenders alongside no_copy on both fields).
		self.remaining_persons = 0
		self.pending_attendance = 0

		# Same belt-and-suspenders as above for the workflow itself: an
		# amendment must restart at Draft, not carry in whatever state
		# (Cancelled, Approved, ...) the document it amends was left in -
		# no_copy on workflow_state already stops most of this (including
		# frappe.copy_doc()'s default ignore_no_copy=True path used by
		# scripted amends, which no_copy is what actually protects against).
		if self.amended_from:
			self.workflow_state = "Draft"

	def before_submit(self):
		# The workflow's own "Approve" transition is the only legitimate path
		# to docstatus 1 (see apply_workflow() in frappe/model/workflow.py:
		# it sets workflow_state to the transition's next_state, THEN calls
		# doc.submit()). A plain PUT/API write of docstatus=1 skips that
		# entirely and reaches here with workflow_state never having passed
		# through "Pending Approval" via the Approve action - so this is what
		# actually enforces "only Approve can submit", not the Submit button
		# being hidden client-side.
		before_save = self.get_doc_before_save()
		previous_state = before_save.workflow_state if before_save else None
		if previous_state != "Pending Approval":
			frappe.throw(
				_("Labor Preapproval can only be submitted via the workflow's 'Approve' action from Pending Approval"),
				title=_("Workflow Bypass Blocked"),
			)

	def on_trash(self):
		block_delete_and_amend_unless_system_manager(self, "delete")

	def validate_source(self):
		if self.source == "Project":
			if not self.reference:
				frappe.throw(_("Project is mandatory for a Project-origin Labor Preapproval"))
			if not self.task:
				frappe.throw(_("Task is mandatory for a Project-origin Labor Preapproval"))

			task_project = frappe.db.get_value("Task", self.task, "project")
			if task_project != self.reference:
				frappe.throw(_("Task {0} does not belong to Project {1}").format(self.task, self.reference))

		elif self.source == "HD Ticket":
			if not self.reference:
				frappe.throw(_("HD Ticket is mandatory for a Helpdesk-origin Labor Preapproval"))
			if not frappe.db.exists("HD Ticket", self.reference):
				frappe.throw(_("HD Ticket {0} does not exist").format(self.reference))

			# Project/Task are not required for Helpdesk-origin requests.
			self.task = None

		else:
			frappe.throw(_("Source must be either Project or HD Ticket"))

	def set_company(self):
		if self.source == "Project":
			self.company = frappe.db.get_value("Project", self.reference, "company")
			self.cost_center = frappe.db.get_value("Project", self.reference, "cost_center")
		else:
			self.company = frappe.defaults.get_global_default("company")
			self.cost_center = None

		if not self.company:
			frappe.throw(_("Unable to resolve Company for this Labor Preapproval"))

		# Most Projects don't carry their own cost centre, which left
		# cost_center blank on every record - fall back to the Company
		# default so labour cost is still attributable somewhere rather than
		# silently unset.
		if not self.cost_center:
			self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")

	def validate_labor_lines(self):
		if not self.labor_line_items:
			frappe.throw(_("At least one Labor Line Item is required"))

		for row in self.labor_line_items:
			if not row.role__skill:
				frappe.throw(_("Row {0}: Role / Skill is required").format(row.idx))
			if not row.no_of_persons or row.no_of_persons < 1:
				frappe.throw(_("Row {0}: No. of Persons must be at least 1").format(row.idx))
			if not row.days or row.days < 1:
				frappe.throw(_("Row {0}: No. of Days must be at least 1").format(row.idx))
			if row.rate is None or row.rate < 0:
				frappe.throw(_("Row {0}: Rate per Day cannot be negative").format(row.idx))

	def validate_self_approval(self):
		# Requester submission/resubmission is not approval - only block the actual
		# Approve/Reject transitions from being actioned by the requester themselves.
		# System Manager is exempt - they administer the workflow and routinely need
		# to submit/approve records they created (e.g. during setup or testing).
		if self.workflow_state in ("Approved", "Rejected") and self.has_value_changed("workflow_state"):
			if self.owner == frappe.session.user and "System Manager" not in frappe.get_roles(frappe.session.user):
				frappe.throw(_("You cannot approve or reject your own Labor Preapproval request"))

	def calculate_totals(self):
		# Server-side totals are authoritative; never trust values sent from the browser/API.
		total_persons = 0
		total_labor_cost = 0
		approved_person_days = 0

		for row in self.labor_line_items:
			row.total_cost = row.no_of_persons * row.days * row.rate
			total_persons += row.no_of_persons
			total_labor_cost += row.total_cost
			approved_person_days += row.no_of_persons * row.days

		self.total_persons = total_persons
		self.total_labor_cost = total_labor_cost
		self.approved_person_days = approved_person_days


def block_delete_and_amend_unless_system_manager(doc, action):
	"""Delete/Amend on the outsourced-labor authorization chain (Labor Preapproval,
	Labor Attendance, Labor Payment Voucher) is restricted to System Manager at the
	code level - not via DocPerm - so the restriction travels with the app instead
	of a per-site permission table that can drift or be reset independently."""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only System Manager can {0} {1}").format(action, doc.doctype))


def get_consumed_person_days(lpre_name, exclude_attendance=None):
	"""Count of submitted (docstatus=1) Labor Attendance rows against this LPRE.

	Each submitted Attendance represents one person-day of consumption.
	Cancelled/reversed Attendance (docstatus=2) never counts, and draft
	Attendance (docstatus=0) is not yet a real consumption event.
	"""
	filters = {"labor_preapproval": lpre_name, "docstatus": 1}
	if exclude_attendance:
		filters["name"] = ["!=", exclude_attendance]
	return frappe.db.count("Labor Attendance", filters)


def get_scheduled_labor_count(lpre):
	"""Total labour already allocated against this LPRE's (reference, task)
	scope via submitted Tech Task Scheduler rows - the same figure
	`validate_labor_count` in tech_task_scheduler.py uses as `existing_used`
	(+ the current doc).

	Scoped by task (when the LPRE is Project-sourced) so that separate Labor
	Preapprovals raised for different Tasks on the same Project each track
	their own scheduled allocation independently, instead of being pooled
	together under one shared "reference" total.
	"""
	if isinstance(lpre, str):
		lpre = frappe.get_doc("Labor Preapproval", lpre)

	if not lpre.reference:
		return 0

	task = lpre.task if lpre.source == "Project" else None
	task_condition = "AND tsl.task = %(task)s" if task else "AND (tsl.task IS NULL OR tsl.task = '')"

	total = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(tsl.allocated_labor), 0)
		FROM `tabTech Task Scheduler List` tsl
		INNER JOIN `tabTech Task Scheduler` ts ON ts.name = tsl.parent
		WHERE tsl.category_name = %(reference)s AND ts.docstatus = 1
		{task_condition}
		""",
		{"reference": lpre.reference, "task": task},
	)[0][0]
	return frappe.utils.flt(total)


def get_remaining_person_days(lpre, exclude_attendance=None):
	"""`lpre` may be a Labor Preapproval doc or name.

	Attendance is fulfilment of what was actually *scheduled* (Tech Task
	Scheduler), not a second, independent draw against the full approved
	budget - so the cap here is the scheduled allocation, not
	`approved_person_days`, whenever a scheduled allocation exists. This is
	what keeps "6 allocated in Scheduler -> attendance capped at 6" true,
	instead of Attendance being allowed up to the full approved 10 and
	silently drifting out of step with what Scheduler already reserved.

	If nothing has been scheduled yet (scheduled == 0), fall back to the
	full approved budget so Attendance isn't blocked for LPREs that don't
	go through the Scheduler at all.
	"""
	if isinstance(lpre, str):
		lpre = frappe.get_doc("Labor Preapproval", lpre)
	consumed = get_consumed_person_days(lpre.name, exclude_attendance=exclude_attendance)
	scheduled = get_scheduled_labor_count(lpre)
	approved = frappe.utils.flt(lpre.approved_person_days)
	cap = scheduled if scheduled > 0 else approved
	return cap - consumed


def get_consumed_cost(lpre_name, exclude_voucher=None):
	"""Sum of Labor Payment Voucher Item amounts already committed against this LPRE,
	across all submitted (docstatus=1) Labor Payment Vouchers."""
	conditions = [
		"lpv.docstatus = 1",
		"la.labor_preapproval = %(lpre)s",
	]
	values = {"lpre": lpre_name}
	if exclude_voucher:
		conditions.append("lpv.name != %(voucher)s")
		values["voucher"] = exclude_voucher

	result = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(lpvi.amount), 0)
		FROM `tabLabor Payment Voucher Item` lpvi
		INNER JOIN `tabLabor Payment Voucher` lpv ON lpv.name = lpvi.parent
		INNER JOIN `tabLabor Attendance` la ON la.name = lpvi.labor_attendance
		WHERE {" AND ".join(conditions)}
		""",
		values,
	)
	return frappe.utils.flt(result[0][0]) if result else 0


def get_remaining_cost(lpre, exclude_voucher=None):
	if isinstance(lpre, str):
		lpre = frappe.get_doc("Labor Preapproval", lpre)
	consumed = get_consumed_cost(lpre.name, exclude_voucher=exclude_voucher)
	approved = frappe.utils.flt(lpre.total_labor_cost)
	return approved - consumed


def sync_completion_status(lpre):
	"""`lpre` may be a Labor Preapproval doc or name. Refreshes `pending_attendance`
	(how much of what's currently *scheduled* still has no Attendance filed
	against it) and - once every scheduled unit for this LPRE has been
	attended and the full approved_person_days consumed - marks it Completed.

	`remaining_persons` is deliberately left untouched here: it is the Tech
	Task Scheduler's own "approved but not yet scheduled" figure (see
	validate_labor_count below) and must not be conflated with Attendance
	fulfilment of what was already scheduled - that was the earlier bug
	("scheduled 6 of 10, then 3 Attendance flipped remaining_persons from
	4 to 7").
	"""
	if isinstance(lpre, str):
		lpre = frappe.get_doc("Labor Preapproval", lpre)

	if lpre.docstatus != 1 or lpre.workflow_state not in ("Approved", "Completed"):
		return

	pending = get_remaining_person_days(lpre)
	frappe.db.set_value("Labor Preapproval", lpre.name, "pending_attendance", pending)

	fully_consumed = get_consumed_person_days(lpre.name) >= frappe.utils.flt(lpre.approved_person_days)

	if lpre.workflow_state == "Approved" and pending <= 0 and fully_consumed:
		frappe.db.set_value("Labor Preapproval", lpre.name, "workflow_state", "Completed")
	elif lpre.workflow_state == "Completed" and (pending > 0 or not fully_consumed):
		# An Attendance that had exhausted capacity was cancelled, freeing it back up.
		frappe.db.set_value("Labor Preapproval", lpre.name, "workflow_state", "Approved")


def sync_completion_status_from_attendance(doc, method=None):
	"""doc_events hook for Labor Attendance on_submit/on_cancel."""
	if doc.labor_preapproval:
		sync_completion_status(doc.labor_preapproval)


def close_open_preapprovals_for_project(project):
	"""Auto-close any still-Approved (i.e. open) Labor Preapproval tied to a
	Project once that Project is closed, so unused authorizations don't
	linger after the Project they were raised for has finished."""
	names = frappe.get_all(
		"Labor Preapproval",
		filters={"source": "Project", "reference": project, "docstatus": 1, "workflow_state": "Approved"},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Labor Preapproval", name, "workflow_state", "Closed")


@frappe.whitelist()
def get_summary_html(lpre_name):
	"""Build the dashboard shown in the `labor_preapproval_html` field:
	Project/Task, every Tech Task Scheduler row allocated against this LPRE's
	(reference, task) scope, every Labor Attendance filed against it, and the
	used/remaining rollup. Read-only reporting - all figures are re-derived
	live from the source documents rather than reusing any cached field, so
	the dashboard can never itself drift out of sync.
	"""
	lpre = frappe.get_doc("Labor Preapproval", lpre_name)

	task = lpre.task if lpre.source == "Project" else None
	task_condition = "AND tsl.task = %(task)s" if task else "AND (tsl.task IS NULL OR tsl.task = '')"

	scheduler_rows = []
	if lpre.reference:
		scheduler_rows = frappe.db.sql(
			f"""
			SELECT ts.name AS scheduler, ts.docstatus, tsl.resource, tsl.status, tsl.allocated_labor
			FROM `tabTech Task Scheduler List` tsl
			INNER JOIN `tabTech Task Scheduler` ts ON ts.name = tsl.parent
			WHERE tsl.category_name = %(reference)s AND ts.docstatus = 1
			{task_condition}
			ORDER BY ts.creation DESC
			""",
			{"reference": lpre.reference, "task": task},
			as_dict=True,
		)

	attendance_rows = frappe.get_all(
		"Labor Attendance",
		filters={"labor_preapproval": lpre.name, "docstatus": ["!=", 2]},
		fields=["name", "labour", "check_in_time", "check_out_time", "validation_status", "docstatus"],
		order_by="check_in_time desc",
	)

	scheduled_total = sum(flt(r.allocated_labor) for r in scheduler_rows)
	consumed = sum(1 for r in attendance_rows if r.docstatus == 1)
	approved = flt(lpre.approved_person_days)
	cap = scheduled_total if scheduled_total > 0 else approved
	remaining = cap - consumed

	project_title = None
	task_title = None
	if lpre.source == "Project" and lpre.reference:
		project_title = frappe.db.get_value("Project", lpre.reference, "project_name")
		if lpre.task:
			task_title = frappe.db.get_value("Task", lpre.task, "subject")

	def esc(value):
		return frappe.utils.escape_html(value) if value else ""

	def status_badge(status, docstatus=None):
		if docstatus == 1:
			return '<span class="lpre-badge lpre-badge-green">Submitted</span>'
		if docstatus is not None:
			return '<span class="lpre-badge lpre-badge-gray">Draft</span>'
		colors = {
			"Scheduled": "blue",
			"Open": "orange",
			"Working": "blue",
			"Pending": "orange",
			"Completed": "green",
			"Overdue": "red",
			"Cancelled": "gray",
		}
		color = colors.get(status, "gray")
		return f'<span class="lpre-badge lpre-badge-{color}">{esc(status) or "-"}</span>'

	attendance_body = "".join(
		f"""
		<tr>
			<td>{esc(r.name)}</td>
			<td>{esc(r.labour)}</td>
			<td>{frappe.utils.format_datetime(r.check_in_time) if r.check_in_time else "-"}</td>
			<td>{frappe.utils.format_datetime(r.check_out_time) if r.check_out_time else "-"}</td>
			<td>{status_badge(None, r.docstatus)}</td>
		</tr>
		"""
		for r in attendance_rows
	) or '<tr><td colspan="5" class="lpre-empty">No Labor Attendance filed yet</td></tr>'

	scheduler_body = "".join(
		f"""
		<tr>
			<td>{esc(r.scheduler)}</td>
			<td>{esc(r.resource) or "-"}</td>
			<td>{status_badge(r.status)}</td>
			<td class="lpre-num">{flt(r.allocated_labor)}</td>
		</tr>
		"""
		for r in scheduler_rows
	) or '<tr><td colspan="4" class="lpre-empty">No Tech Task Scheduler allocation yet</td></tr>'

	remaining_color = "lpre-stat-red" if remaining <= 0 else "lpre-stat-green"

	return f"""
	<style>
		.lpre-summary {{ font-family: inherit; }}
		.lpre-summary .lpre-stats {{
			display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px;
		}}
		.lpre-summary .lpre-stat {{
			flex: 1 1 150px; border-radius: 8px; padding: 12px 14px;
			background: #f4f6fb; border: 1px solid #e3e8f0;
		}}
		.lpre-summary .lpre-stat-label {{
			font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
			color: #6b7280; margin-bottom: 4px;
		}}
		.lpre-summary .lpre-stat-value {{ font-size: 18px; font-weight: 600; color: #1f2937; }}
		.lpre-summary .lpre-stat-blue {{ background: #eaf1ff; border-color: #cddcfb; }}
		.lpre-summary .lpre-stat-blue .lpre-stat-value {{ color: #2c6ef2; }}
		.lpre-summary .lpre-stat-green {{ background: #eafaf1; border-color: #c9f0d9; }}
		.lpre-summary .lpre-stat-green .lpre-stat-value {{ color: #1f9d55; }}
		.lpre-summary .lpre-stat-red {{ background: #fdeeee; border-color: #f6cfcf; }}
		.lpre-summary .lpre-stat-red .lpre-stat-value {{ color: #d64545; }}
		.lpre-summary h6 {{
			font-size: 12px; font-weight: 600; text-transform: uppercase;
			letter-spacing: .04em; color: #4b5563; margin: 18px 0 8px;
			border-left: 3px solid #2c6ef2; padding-left: 8px;
		}}
		.lpre-summary table {{
			width: 100%; border-collapse: collapse; font-size: 12px;
			border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden;
		}}
		.lpre-summary thead th {{
			background: #2c6ef2; color: #fff; text-align: left;
			padding: 7px 10px; font-weight: 500;
		}}
		.lpre-summary tbody td {{
			padding: 7px 10px; border-top: 1px solid #eef0f4; color: #374151;
		}}
		.lpre-summary tbody tr:nth-child(even) {{ background: #f9fafc; }}
		.lpre-summary tbody tr:hover {{ background: #f0f4ff; }}
		.lpre-summary .lpre-num {{ text-align: right; }}
		.lpre-summary .lpre-empty {{ text-align: center; color: #9ca3af; padding: 14px; }}
		.lpre-badge {{
			display: inline-block; padding: 2px 9px; border-radius: 999px;
			font-size: 11px; font-weight: 600;
		}}
		.lpre-badge-green {{ background: #eafaf1; color: #1f9d55; }}
		.lpre-badge-blue {{ background: #eaf1ff; color: #2c6ef2; }}
		.lpre-badge-orange {{ background: #fff4e5; color: #d9822b; }}
		.lpre-badge-red {{ background: #fdeeee; color: #d64545; }}
		.lpre-badge-gray {{ background: #f0f1f3; color: #6b7280; }}
	</style>
	<div class="lpre-summary">
		<div class="lpre-stats">
			<div class="lpre-stat"><div class="lpre-stat-label">Project</div><div class="lpre-stat-value">{esc(project_title) or esc(lpre.reference) or "-"}</div></div>
			<div class="lpre-stat"><div class="lpre-stat-label">Task</div><div class="lpre-stat-value">{esc(task_title) or esc(lpre.task) or "-"}</div></div>
			<div class="lpre-stat lpre-stat-blue"><div class="lpre-stat-label">Approved</div><div class="lpre-stat-value">{approved}</div></div>
			<div class="lpre-stat lpre-stat-blue"><div class="lpre-stat-label">Scheduled</div><div class="lpre-stat-value">{scheduled_total}</div></div>
			<div class="lpre-stat lpre-stat-green"><div class="lpre-stat-label">Used</div><div class="lpre-stat-value">{consumed}</div></div>
			<div class="lpre-stat {remaining_color}"><div class="lpre-stat-label">Remaining</div><div class="lpre-stat-value">{remaining}</div></div>
		</div>

		<h6>Tech Task Scheduler Allocation</h6>
		<table>
			<thead><tr><th>Scheduler</th><th>Resource</th><th>Status</th><th class="lpre-num">Allocated</th></tr></thead>
			<tbody>{scheduler_body}</tbody>
		</table>

		<h6>Labor Attendance</h6>
		<table>
			<thead><tr><th>Attendance</th><th>Labour</th><th>Check-In</th><th>Check-Out</th><th>Status</th></tr></thead>
			<tbody>{attendance_body}</tbody>
		</table>
	</div>
	"""


def validate_lpre_is_approved(lpre):
	"""`lpre` may be a Labor Preapproval doc or name. Raises if not an authoritative,
	fully Approved Labor Preapproval (docstatus = 1 and workflow_state = Approved)."""
	if isinstance(lpre, str):
		lpre = frappe.get_doc("Labor Preapproval", lpre)

	if lpre.docstatus != 1 or lpre.workflow_state != "Approved":
		frappe.throw(
			_("Labor Preapproval {0} is not Approved (status: {1})").format(
				lpre.name, lpre.workflow_state or ("Draft" if lpre.docstatus == 0 else "Cancelled")
			)
		)
	return lpre
