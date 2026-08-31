import frappe


def execute():
	"""Backfill DocShares for Tech Task Scheduler rows that were assigned
	before sharing was added alongside assignment.

	For every row with a resource and a mapped Task/HD Ticket, share the
	target document with that resource if it isn't already shared.
	"""

	rows = frappe.db.sql(
		"""
		SELECT category, task, category_name, resource
		FROM `tabTech Task Scheduler List`
		WHERE resource IS NOT NULL AND resource != ''
		""",
		as_dict=True,
	)

	for row in rows:
		if row.category == "Project" and row.task:
			doctype, name = "Task", row.task
		elif row.category == "HD Ticket" and row.category_name:
			doctype, name = "HD Ticket", row.category_name
		else:
			continue

		user = row.resource

		if not frappe.db.exists(doctype, name):
			continue

		if frappe.db.exists(
			"DocShare",
			{"share_doctype": doctype, "share_name": name, "user": user},
		):
			continue

		frappe.share.add_docshare(
			doctype,
			name,
			user,
			read=1,
			write=1,
			notify=0,
			flags={"ignore_share_permission": True},
		)
