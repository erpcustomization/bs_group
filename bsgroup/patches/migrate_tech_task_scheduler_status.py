import frappe

# Retired status values -> new aligned status values
STATUS_MAP = {
	"Draft": "Open",
	"In-Progress": "Working",
}


def execute():
	"""Migrate Tech Task Scheduler List rows off the retired status values
	so they use the status set shared with the Timesheet."""

	for old_status, new_status in STATUS_MAP.items():
		frappe.db.sql(
			"""
			UPDATE `tabTech Task Scheduler List`
			SET status = %s
			WHERE status = %s
			""",
			(new_status, old_status),
		)
