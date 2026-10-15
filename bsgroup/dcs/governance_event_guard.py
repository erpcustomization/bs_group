"""Trust boundary for DCS Governance Event.

Registered on ``doc_events["DCS Governance Event"]["before_insert"]`` in
``hooks.py`` and also called from the DocType controller so the boundary
holds even if the hook registration were ever lost.

* Insert is permitted only when ``doc.flags.dcs_audit_write == 1``. The flag
  cannot be set over REST, so ``/api/resource`` and ``frappe.client.insert``
  are refused with ``PermissionError``.
* ``actor``, ``event_timestamp``, ``outcome`` and ``correlation_id`` are
  overwritten from the server context. Whatever the caller put in them is
  discarded.
* ``changes`` is a JSON-encoded list of dicts (never a child table); an empty
  or malformed change set is rejected after being logged.
* ``source_event_id`` (idempotency key) must not already exist.
"""

import json

import frappe
from frappe.utils import now

from bsgroup.dcs.governance import get_correlation_id

VALID_OUTCOMES = ("Success", "Failure")


def before_insert(doc, method=None):
	if doc.flags.get("dcs_audit_write") != 1:
		frappe.throw(
			"DCS Governance Event records may only be created by the audit-guard "
			"code path, not directly.",
			frappe.PermissionError,
		)

	# --- server-derived identity: never trust the caller ---------------------
	doc.actor = frappe.session.user
	doc.event_timestamp = now()
	doc.correlation_id = get_correlation_id()
	if doc.outcome not in VALID_OUTCOMES:
		doc.outcome = "Success"

	# --- idempotency -----------------------------------------------------------
	if doc.source_event_id:
		dup = frappe.db.get_value("DCS Governance Event", {"source_event_id": doc.source_event_id}, "name")
		if dup:
			frappe.throw(
				f"A governance event for this request already exists ({dup}). "
				"Repeated identical requests are not recorded twice.",
				frappe.DuplicateEntryError,
			)

	# --- change set ------------------------------------------------------------
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
		df = None
		if fieldname and frappe.db.exists("DocType", target_doctype):
			df = frappe.get_meta(target_doctype).get_field(fieldname)

		# Callers that don't know the real label/type (e.g. dcs_presales_sync)
		# fall back to the fieldname itself / a generic "Data" type -- prefer
		# real doctype metadata over those placeholders whenever it's available.
		if df:
			row["field_label"] = df.label or row.get("field_label") or fieldname
			row["value_type"] = df.fieldtype
		else:
			row.setdefault("field_label", fieldname)
			row.setdefault("value_type", type(row.get("new_value")).__name__)

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
