import frappe
from frappe.utils import getdate, now_datetime, nowdate

TASK_EXCLUDED_STATUSES = ("Completed", "Cancelled", "Overdue", "Template")


def mark_overdue_scheduler_rows():
	"""Hourly job: flag overdue Tasks and Tech Task Scheduler List rows.

	- Tasks: any Task past its exp_end_date and not yet finished is marked
	  Overdue directly - independent of whether it's scheduled anywhere.
	  Any Tech Task Scheduler List row already linked to that Task is flagged
	  Overdue too, so the scheduler view stays in sync.
	- HD Ticket rows (row.category_name set): overdue when the ticket's SLA
	  resolution_by has passed and its current HD Ticket Status isn't in the
	  "Resolved" category (Open/Paused both count as still unresolved).
	"""

	mark_overdue_tasks()
	mark_overdue_hd_ticket_rows()


def mark_overdue_tasks():
	today = getdate(nowdate())

	tasks = frappe.get_all(
		"Task",
		filters={
			"exp_end_date": ["<", today],
			"status": ["not in", TASK_EXCLUDED_STATUSES],
		},
		fields=["name"],
	)

	for task in tasks:
		frappe.db.set_value("Task", task.name, "status", "Overdue", update_modified=False)

		rows = frappe.get_all(
			"Tech Task Scheduler List",
			filters={
				"task": task.name,
				"status": ["not in", ["Completed", "Cancelled", "Overdue"]],
			},
			fields=["name", "parent"],
		)
		for row in rows:
			if frappe.db.get_value("Tech Task Scheduler", row.parent, "docstatus") == 2:
				continue
			mark_row_overdue(row.name)


def mark_overdue_hd_ticket_rows():
	now = now_datetime()

	rows = frappe.get_all(
		"Tech Task Scheduler List",
		filters={
			"category": "HD Ticket",
			"status": ["not in", ["Completed", "Cancelled", "Overdue"]],
		},
		fields=["name", "parent", "category_name"],
	)

	for row in rows:
		if not row.category_name:
			continue
		if frappe.db.get_value("Tech Task Scheduler", row.parent, "docstatus") == 2:
			continue
		check_hd_ticket_overdue(row, now)


def check_hd_ticket_overdue(row, now):
	ticket = frappe.db.get_value(
		"HD Ticket", row.category_name, ["status", "resolution_by"], as_dict=True
	)
	if not ticket or not ticket.resolution_by:
		return

	if now < ticket.resolution_by:
		return

	status_category = frappe.db.get_value("HD Ticket Status", ticket.status, "category")
	if status_category == "Resolved":
		return

	mark_row_overdue(row.name)


def mark_row_overdue(row_name):
	frappe.db.set_value(
		"Tech Task Scheduler List",
		row_name,
		"status",
		"Overdue",
		update_modified=False,
	)
