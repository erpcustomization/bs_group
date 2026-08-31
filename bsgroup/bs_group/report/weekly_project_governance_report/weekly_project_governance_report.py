# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate

# "Blocked" is judged purely off Task.status - any of the Pending* statuses
# the app's custom `status` Select options use to mean "stuck on someone
# else" (see property_setter on Task.status). No date/other logic mixed in.
BLOCKED_STATUSES = {
	"Pending",
	"Pending from Implementation",
	"Pending from Sales Account",
	"Pending from Client",
	"Pending Sign-Off",
	"Pending Invoicing",
}

CLOSED_STATUSES = {"Completed", "Cancelled"}


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Task", "fieldname": "name", "fieldtype": "Link", "options": "Task", "width": 150},
		{"label": "Subject", "fieldname": "subject", "fieldtype": "Data", "width": 220},
		{"label": "Project", "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 150},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 160},
		{"label": "Created", "fieldname": "created", "fieldtype": "Check", "width": 80},
		{"label": "Completed", "fieldname": "completed", "fieldtype": "Check", "width": 90},
		{"label": "Untouched", "fieldname": "untouched", "fieldtype": "Check", "width": 90},
		{"label": "Overdue", "fieldname": "overdue", "fieldtype": "Check", "width": 80},
		{"label": "Blocked", "fieldname": "blocked", "fieldtype": "Check", "width": 80},
		{"label": "Missing Timesheet", "fieldname": "missing_timesheet", "fieldtype": "Check", "width": 120},
		{"label": "Requires Action", "fieldname": "requires_action", "fieldtype": "Check", "width": 120},
		{"label": "Categories", "fieldname": "categories", "fieldtype": "Data", "width": 260},
		{"label": "Exp Start Date", "fieldname": "exp_start_date", "fieldtype": "Date", "width": 110},
		{"label": "Exp End Date", "fieldname": "exp_end_date", "fieldtype": "Date", "width": 110},
		{"label": "Last Touched", "fieldname": "modified", "fieldtype": "Datetime", "width": 150},
	]


def get_data(filters):
	from_date = getdate(filters.get("from_date"))
	to_date = getdate(filters.get("to_date"))

	if from_date > to_date:
		frappe.throw(frappe._("From Date cannot be after To Date"))

	task_filters = {}
	if filters.get("project"):
		task_filters["project"] = filters["project"]

	company = frappe.defaults.get_user_default("company")
	if company:
		task_filters["company"] = company

	# Scope to Tasks that could plausibly be relevant to this window: either
	# they existed on/before `to_date`, or their planned window overlaps it.
	# Anything created strictly after `to_date` has nothing to report yet.
	task_filters["creation"] = ["<=", f"{to_date} 23:59:59"]

	tasks = frappe.get_all(
		"Task",
		filters=task_filters,
		fields=[
			"name", "subject", "project", "status", "creation", "modified",
			"exp_start_date", "exp_end_date", "completed_on",
		],
	)

	if not tasks:
		return []

	task_names = [t.name for t in tasks]
	timesheet_logged = _get_tasks_with_timesheet_in_range(task_names, from_date, to_date)

	project_names = {}
	for t in tasks:
		if t.project and t.project not in project_names:
			project_names[t.project] = frappe.db.get_value("Project", t.project, "project_name") or t.project

	rows = []
	requested_category = filters.get("category")

	for t in tasks:
		created_date = getdate(t.creation)
		modified_date = getdate(t.modified)
		is_closed = t.status in CLOSED_STATUSES

		created = from_date <= created_date <= to_date
		completed = (
			t.status == "Completed"
			and t.completed_on
			and from_date <= getdate(t.completed_on) <= to_date
		)
		# Untouched: nothing happened on this Task during the chosen window -
		# its last modification falls outside [from_date, to_date] - and it's
		# still open work, not something already closed out.
		untouched = not is_closed and not (from_date <= modified_date <= to_date)
		overdue = (
			not is_closed
			and t.exp_end_date
			and getdate(t.exp_end_date) < to_date
		)
		blocked = t.status in BLOCKED_STATUSES
		# Missing Timesheet: the Task's planned window overlaps the chosen
		# period, it isn't closed, but no submitted Timesheet Detail row
		# against it falls inside that period.
		planned_in_window = (
			t.exp_start_date
			and t.exp_end_date
			and getdate(t.exp_start_date) <= to_date
			and getdate(t.exp_end_date) >= from_date
		)
		missing_timesheet = bool(planned_in_window) and not is_closed and t.name not in timesheet_logged

		requires_action = overdue or blocked or missing_timesheet or untouched

		categories = [
			label
			for flag, label in (
				(created, "Created"),
				(completed, "Completed"),
				(untouched, "Untouched"),
				(overdue, "Overdue"),
				(blocked, "Blocked"),
				(missing_timesheet, "Missing Timesheet"),
			)
			if flag
		]

		if not categories:
			continue

		if requested_category and requested_category not in categories:
			continue

		rows.append({
			"name": t.name,
			"subject": t.subject,
			"project": t.project,
			"project_name": project_names.get(t.project, ""),
			"status": t.status,
			"created": 1 if created else 0,
			"completed": 1 if completed else 0,
			"untouched": 1 if untouched else 0,
			"overdue": 1 if overdue else 0,
			"blocked": 1 if blocked else 0,
			"missing_timesheet": 1 if missing_timesheet else 0,
			"requires_action": 1 if requires_action else 0,
			"categories": ", ".join(categories),
			"exp_start_date": t.exp_start_date,
			"exp_end_date": t.exp_end_date,
			"modified": t.modified,
		})

	return rows


CATEGORY_META = [
	("Created", "created", "blue"),
	("Completed", "completed", "green"),
	("Untouched", "untouched", "gray"),
	("Overdue", "overdue", "red"),
	("Blocked", "blocked", "orange"),
	("Missing Timesheet", "missing_timesheet", "purple"),
]


@frappe.whitelist()
def get_colorful_html(from_date, to_date, project=None, category=None):
	"""Zoho-style colourful summary of this same report's data - stat cards
	per category (Created/Completed/Untouched/Overdue/Blocked/Missing
	Timesheet/Requires Action) plus a colour-coded table underneath. Reuses
	get_data() so it can never disagree with the grid view of this report.
	"""
	filters = {"from_date": from_date, "to_date": to_date}
	if project:
		filters["project"] = project
	if category:
		filters["category"] = category

	rows = get_data(filters)

	def esc(value):
		return frappe.utils.escape_html(value) if value else ""

	counts = {key: 0 for _, key, _ in CATEGORY_META}
	requires_action_count = 0
	for r in rows:
		for _, key, _ in CATEGORY_META:
			if r.get(key):
				counts[key] += 1
		if r.get("requires_action"):
			requires_action_count += 1

	stat_cards = "".join(
		f"""
		<div class="wpg-stat wpg-stat-{color}">
			<div class="wpg-stat-label">{label}</div>
			<div class="wpg-stat-value">{counts[key]}</div>
		</div>
		"""
		for label, key, color in CATEGORY_META
	)
	stat_cards += f"""
	<div class="wpg-stat wpg-stat-red wpg-stat-emphasis">
		<div class="wpg-stat-label">Requires Action</div>
		<div class="wpg-stat-value">{requires_action_count}</div>
	</div>
	"""

	def category_badges(row):
		badges = []
		for label, key, color in CATEGORY_META:
			if row.get(key):
				badges.append(f'<span class="wpg-badge wpg-badge-{color}">{label}</span>')
		return " ".join(badges) or "-"

	table_rows = "".join(
		f"""
		<tr class="{'wpg-row-action' if r.get('requires_action') else ''}">
			<td>{esc(r.get('name'))}</td>
			<td>{esc(r.get('subject'))}</td>
			<td>{esc(r.get('project_name')) or esc(r.get('project')) or '-'}</td>
			<td>{esc(r.get('status'))}</td>
			<td>{category_badges(r)}</td>
			<td>{frappe.utils.format_date(r.get('exp_end_date')) if r.get('exp_end_date') else '-'}</td>
		</tr>
		"""
		for r in rows
	) or '<tr><td colspan="6" class="wpg-empty">No Tasks in this window/scope</td></tr>'

	return f"""
	<style>
		.wpg-wrap {{ font-family: inherit; }}
		.wpg-stats {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; }}
		.wpg-stat {{
			flex: 1 1 130px; border-radius: 8px; padding: 12px 14px;
			background: #f4f6fb; border: 1px solid #e3e8f0;
		}}
		.wpg-stat-label {{
			font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
			color: #6b7280; margin-bottom: 4px;
		}}
		.wpg-stat-value {{ font-size: 22px; font-weight: 700; color: #1f2937; }}
		.wpg-stat-blue {{ background: #eaf1ff; border-color: #cddcfb; }}
		.wpg-stat-blue .wpg-stat-value {{ color: #2c6ef2; }}
		.wpg-stat-green {{ background: #eafaf1; border-color: #c9f0d9; }}
		.wpg-stat-green .wpg-stat-value {{ color: #1f9d55; }}
		.wpg-stat-gray {{ background: #f2f3f5; border-color: #e0e2e6; }}
		.wpg-stat-gray .wpg-stat-value {{ color: #6b7280; }}
		.wpg-stat-red {{ background: #fdeeee; border-color: #f6cfcf; }}
		.wpg-stat-red .wpg-stat-value {{ color: #d64545; }}
		.wpg-stat-orange {{ background: #fff4e5; border-color: #fbdfb3; }}
		.wpg-stat-orange .wpg-stat-value {{ color: #d9822b; }}
		.wpg-stat-purple {{ background: #f3ecfd; border-color: #ddc9f5; }}
		.wpg-stat-purple .wpg-stat-value {{ color: #7e3ff2; }}
		.wpg-stat-emphasis {{ border-width: 2px; }}
		.wpg-wrap table {{
			width: 100%; border-collapse: collapse; font-size: 12px;
			border: 1px solid #e5e7eb; border-radius: 6px; overflow: hidden;
		}}
		.wpg-wrap thead th {{
			background: #2c6ef2; color: #fff; text-align: left;
			padding: 8px 10px; font-weight: 500;
		}}
		.wpg-wrap tbody td {{ padding: 7px 10px; border-top: 1px solid #eef0f4; color: #374151; }}
		.wpg-wrap tbody tr:nth-child(even) {{ background: #f9fafc; }}
		.wpg-wrap tbody tr:hover {{ background: #f0f4ff; }}
		.wpg-wrap tbody tr.wpg-row-action {{ background: #fff8f2; }}
		.wpg-wrap tbody tr.wpg-row-action:hover {{ background: #fdeee0; }}
		.wpg-empty {{ text-align: center; color: #9ca3af; padding: 16px; }}
		.wpg-badge {{
			display: inline-block; padding: 2px 8px; border-radius: 999px;
			font-size: 10px; font-weight: 600; margin: 1px;
		}}
		.wpg-badge-blue {{ background: #eaf1ff; color: #2c6ef2; }}
		.wpg-badge-green {{ background: #eafaf1; color: #1f9d55; }}
		.wpg-badge-gray {{ background: #f0f1f3; color: #6b7280; }}
		.wpg-badge-red {{ background: #fdeeee; color: #d64545; }}
		.wpg-badge-orange {{ background: #fff4e5; color: #d9822b; }}
		.wpg-badge-purple {{ background: #f3ecfd; color: #7e3ff2; }}
	</style>
	<div class="wpg-wrap">
		<div class="wpg-stats">{stat_cards}</div>
		<table>
			<thead><tr><th>Task</th><th>Subject</th><th>Project</th><th>Status</th><th>Categories</th><th>Exp End</th></tr></thead>
			<tbody>{table_rows}</tbody>
		</table>
	</div>
	"""


def _get_tasks_with_timesheet_in_range(task_names, from_date, to_date):
	"""Task names that have at least one submitted Timesheet Detail row
	(from_time date) inside [from_date, to_date]."""
	if not task_names:
		return set()

	rows = frappe.db.sql(
		"""
		SELECT DISTINCT tsd.task
		FROM `tabTimesheet Detail` tsd
		INNER JOIN `tabTimesheet` ts ON ts.name = tsd.parent
		WHERE ts.docstatus = 1
		AND tsd.task IN %(tasks)s
		AND DATE(tsd.from_time) BETWEEN %(from_date)s AND %(to_date)s
		""",
		{"tasks": task_names, "from_date": from_date, "to_date": to_date},
	)
	return {r[0] for r in rows}
