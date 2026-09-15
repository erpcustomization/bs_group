import frappe


def execute():
	"""Backfill completed_on on Tasks that are Completed but have no
	completed_on, which happens when status was set via db_set, a migration,
	or any other path that skips the standard form/API save. Without this,
	such tasks silently drop out of Weekly Project Governance Report's
	"Completed" count, which filters on completed_on falling in the window.

	Uses `modified` as the best available proxy for when the task was
	actually completed.
	"""

	frappe.db.sql(
		"""
		UPDATE `tabTask`
		SET completed_on = DATE(modified)
		WHERE status = 'Completed' AND completed_on IS NULL
		"""
	)
