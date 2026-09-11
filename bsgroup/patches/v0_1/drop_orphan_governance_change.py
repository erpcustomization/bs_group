"""A-4: remove the orphan child DocType ``DCS Governance Event Change``.

``DCS Governance Event.changes`` is a JSON field on every deployment (repo
history and production metadata both confirm it); no DocField or Custom Field
anywhere has ``options = DCS Governance Event Change``. The child DocType is
therefore unreachable. It is deleted only when its table is empty and nothing
links to it; otherwise the deletion is skipped and logged so an operator can
decide, and the migration continues.
"""

import frappe

CHILD = "DCS Governance Event Change"
LOG_TITLE = "BSG-REL-1"


def execute():
	if not frappe.db.exists("DocType", CHILD):
		return
	linked = frappe.get_all("DocField", filters={"options": CHILD}, fields=["parent", "fieldname"])
	linked += frappe.get_all("Custom Field", filters={"options": CHILD}, fields=["dt as parent", "fieldname"])
	rows = frappe.db.count(CHILD) if frappe.db.table_exists(CHILD) else 0
	if linked or rows:
		frappe.log_error(
			title=LOG_TITLE,
			message=f"{CHILD}: NOT deleted - {rows} row(s), linked from {linked}. Manual decision required.",
		)
		return
	frappe.delete_doc("DocType", CHILD, force=1, ignore_permissions=True, ignore_missing=True)
	frappe.log_error(title=LOG_TITLE, message=f"{CHILD}: orphan child DocType deleted (0 rows, no links).")
