"""Guard for DCS Governance Event.

Only code paths that explicitly set ``doc.flags.dcs_audit_write = 1`` before
calling ``insert()`` may create these records, and every record must carry a
non-empty change set.

``changes`` is a JSON field (a JSON-encoded list of dicts), not a child
table -- it must be decoded, never iterated as rows.
"""

import json

import frappe


def before_insert(doc, method=None):
	if doc.flags.get("dcs_audit_write") != 1:
		frappe.throw(
			"DCS Governance Event records may only be created by the audit-guard "
			"code path, not directly.",
			frappe.PermissionError,
		)

	changes = _load_changes(doc.changes)

	if not changes:
		frappe.log_error(
			title="DCS Governance Event - empty change set",
			message=frappe.as_json(
				{
					"dcs": doc.dcs,
					"event_code": doc.event_code,
					"source_endpoint": doc.source_endpoint,
					"raw_changes": doc.changes,
				}
			),
		)
		frappe.throw("DCS Governance Event must record at least one changed field.")

	for row in changes:
		fieldname = row.get("fieldname")
		target_doctype = row.get("target_doctype") or "Deal Cost Sheet"
		df = frappe.get_meta(target_doctype).get_field(fieldname) if fieldname else None

		if not row.get("field_label"):
			row["field_label"] = df.label if df else fieldname
		if not row.get("value_type"):
			row["value_type"] = df.fieldtype if df else type(row.get("new_value")).__name__

	doc.change_count = len(changes)
	doc.changes = json.dumps(changes)


def _load_changes(raw):
	if not raw:
		return []
	if isinstance(raw, str):
		try:
			raw = json.loads(raw)
		except ValueError:
			return []
	if not isinstance(raw, list):
		return []
	return [row for row in raw if isinstance(row, dict) and row]
