"""R3: fold the legacy ``DCS Governance Event Change`` child rows into the parent
event's ``changes`` JSON, deterministically and without deleting anything.

Background
----------
``DCS Governance Event.changes`` is a JSON field in this release, and no DocField
or Custom Field references the old child DocType, so Frappe's own orphan sweep
removes the child DocType's METADATA during ``bench migrate``. Its table, however,
still holds real audit rows. ``drop_orphan_governance_change`` correctly refuses to
delete them, but the sweep runs afterwards regardless, which left the rows stranded:
present on disk, unreachable through the ORM.

What this patch does
--------------------
For every parent event that still has an empty ``changes`` payload, the child rows
are read in ``idx`` order and written into the parent as the canonical change-row
JSON produced by :func:`bsgroup.dcs.governance.build_change_rows`, so the audit
payload is reachable from the immutable parent event exactly as new events are.

* Nothing is deleted. The child table is retained untouched as an archive.
* A parent that already carries a payload is never overwritten; it is counted as
  already-folded when the entry count matches, otherwise it is reported as a
  discrepancy and left alone.
* Idempotent: a second run folds nothing and re-verifies.
* Runs in ``pre_model_sync``, i.e. BEFORE the orphan sweep, so a clean deployment
  folds the rows while the child DocType metadata is still present.
* The reconciliation summary (total rows, folded, already present, unreachable,
  accessible-after) is written to Error Log ``BSG-REL-1`` and returned, so the
  154/154 proof is evidence, not an assertion.

Writes use ``frappe.db.set_value(..., update_modified=False)`` so no document hook,
notification or governance side effect fires for a historical data migration.
"""

import json

import frappe

CHILD = "DCS Governance Event Change"
PARENT = "DCS Governance Event"
LOG_TITLE = "BSG-REL-1"


def _canonical_rows(rows):
	"""Child rows -> the canonical payload shape used by governance.build_change_rows."""
	out = []
	for r in rows:
		entry = {
			"fieldname": r.get("fieldname"),
			"target_doctype": r.get("target_doctype") or PARENT,
			"target_name": r.get("target_name") or r.get("parent"),
			"old_value": "" if r.get("old_value") is None else str(r.get("old_value")),
			"new_value": "" if r.get("new_value") is None else str(r.get("new_value")),
		}
		# keep the two columns the JSON shape does not carry, rather than lose them
		if r.get("field_label"):
			entry["field_label"] = r.get("field_label")
		if r.get("value_type"):
			entry["value_type"] = r.get("value_type")
		out.append(entry)
	return out


def _entry_count(raw):
	if not raw:
		return 0
	try:
		parsed = json.loads(raw)
	except (TypeError, ValueError):
		return -1
	return len(parsed) if isinstance(parsed, list) else -1


def execute():
	if not frappe.db.table_exists(CHILD):
		return {"status": "no-table", "rows": 0}

	# Raw SQL throughout: on a bench where the orphan sweep has already removed the
	# child DocType's metadata the ORM cannot read this table at all.
	rows = frappe.db.sql(
		"""select parent, idx, fieldname, field_label, target_doctype, target_name,
				old_value, new_value, value_type
			from `tab{0}` order by parent, idx, name""".format(CHILD),
		as_dict=True,
	)
	total = len(rows)
	if not total:
		return {"status": "empty", "rows": 0}

	by_parent = {}
	for r in rows:
		by_parent.setdefault(r.get("parent"), []).append(r)

	folded_rows = 0
	folded_parents = 0
	already_rows = 0
	already_parents = 0
	missing_parent_rows = 0
	discrepancies = []

	for parent, group in sorted(by_parent.items()):
		if not parent or not frappe.db.exists(PARENT, parent):
			missing_parent_rows += len(group)
			discrepancies.append({"parent": parent, "issue": "parent event not found", "rows": len(group)})
			continue

		current = frappe.db.get_value(PARENT, parent, "changes")
		count_now = _entry_count(current)
		if count_now > 0:
			already_parents += 1
			already_rows += len(group)
			if count_now != len(group):
				discrepancies.append(
					{"parent": parent, "issue": "existing payload size differs", "child_rows": len(group), "payload_entries": count_now}
				)
			continue
		if count_now == -1:
			discrepancies.append({"parent": parent, "issue": "existing changes value is not a JSON list", "rows": len(group)})
			continue

		payload = _canonical_rows(group)
		frappe.db.set_value(
			PARENT, parent,
			{"changes": json.dumps(payload), "change_count": len(payload)},
			update_modified=False,
		)
		folded_parents += 1
		folded_rows += len(payload)

	# --- reconciliation: re-read every parent and count what is now reachable -------
	accessible = 0
	for parent, group in sorted(by_parent.items()):
		if not parent or not frappe.db.exists(PARENT, parent):
			continue
		accessible += max(_entry_count(frappe.db.get_value(PARENT, parent, "changes")), 0)

	summary = {
		"child_rows_total": total,
		"parents_total": len(by_parent),
		"folded_rows": folded_rows,
		"folded_parents": folded_parents,
		"already_present_rows": already_rows,
		"already_present_parents": already_parents,
		"rows_with_missing_parent": missing_parent_rows,
		"accessible_after": accessible,
		"reconciled": accessible == total and missing_parent_rows == 0 and not discrepancies,
		"child_table_retained": True,
		"discrepancies": discrepancies[:20],
	}
	frappe.log_error(title=LOG_TITLE, message="governance change-row fold\n" + frappe.as_json(summary))
	return summary
