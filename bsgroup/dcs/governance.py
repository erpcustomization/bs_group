"""Single writer for DCS Governance Events.

Every governed DCS action records its committed change set through
:func:`record_governance_event`. Nothing else in the app, and no Server
Script after this release, builds a ``DCS Governance Event`` by hand.

Trust model
-----------
* Only code that sets ``flags.dcs_audit_write = 1`` may insert an event, and
  only this module sets that flag.
* ``actor``, ``event_timestamp``, ``outcome`` and ``correlation_id`` are
  derived on the server. Caller-supplied values are ignored/overwritten in
  :mod:`bsgroup.dcs.governance_event_guard`.
* ``correlation_id`` is generated **once per request** (see
  :func:`get_correlation_id`) so every event written while serving one HTTP
  request or one background job shares it. It is not derived from the
  document name.
* ``source_event_id`` is an idempotency key for the *business action*. Two
  identical requests from the same user against the same document produce
  the same key; the second one is detected by :func:`find_replay` and the
  endpoint returns the earlier result instead of mutating again.
* The event is inserted in the caller's transaction and never commits on its
  own, so the business mutation and its audit record survive or roll back
  together.

The change-set helpers (:func:`snapshot`, :func:`diff_changes`) reproduce the
"D2a Phase 2" companions that were byte-identical across the production
Server Scripts (see ``bsgroup/dcs/server_script_export``).
"""

import hashlib
import json

import frappe
from frappe.utils import now

REQUEST_CORRELATION_ATTR = "bsg_correlation_id"


def get_correlation_id() -> str:
	"""Return the correlation id for the current request/job, creating it once."""
	cid = getattr(frappe.local, REQUEST_CORRELATION_ATTR, None)
	if not cid:
		cid = frappe.generate_hash(length=16)
		setattr(frappe.local, REQUEST_CORRELATION_ATTR, cid)
	return cid


def reset_correlation_id():
	"""Hook target for ``before_request``/``before_job`` so a worker never reuses an id."""
	if hasattr(frappe.local, REQUEST_CORRELATION_ATTR):
		delattr(frappe.local, REQUEST_CORRELATION_ATTR)


def _canonical(value):
	"""Stable JSON for hashing request payloads."""
	return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def make_request_key(endpoint: str, payload: dict) -> str:
	"""Idempotency key for one business action.

	Same user + same endpoint + same canonical payload => same key. The key is
	independent of time so a retry (double click, network replay) maps to the
	same value; a genuinely new action carries different arguments.
	"""
	raw = "|".join([frappe.session.user or "", endpoint or "", _canonical(payload or {})])
	return "REQ-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def find_replay(request_key: str):
	"""Return the name of the governance event already written for ``request_key``, if any."""
	if not request_key:
		return None
	return frappe.db.get_value("DCS Governance Event", {"source_event_id": request_key}, "name")


def snapshot(doctype: str, name: str, fields) -> dict:
	"""Read the named fields of a document straight from the database, as strings."""
	snap = {}
	if not name:
		return snap
	row = frappe.db.get_value(doctype, name, list(fields), as_dict=True)
	if row is None:
		return snap
	for f in fields:
		v = row.get(f)
		snap[f] = "" if v is None else str(v)
	return snap


def diff_changes(fields, before: dict, after: dict, doctype: str, name: str) -> list:
	"""Return ``[{field, old, new, dt, dn}]`` for every field whose stored value moved."""
	moved = []
	for f in fields:
		ov = before.get(f)
		nv = after.get(f)
		ov = "" if ov is None else ov
		nv = "" if nv is None else nv
		if str(ov) == str(nv):
			continue
		moved.append({"field": f, "old": ov, "new": nv, "dt": doctype, "dn": name})
	return moved


def build_change_rows(changes, default_doctype: str, default_name: str) -> list:
	"""Normalise the loose ``{field, old, new, dt, dn}`` list into stored rows, dropping no-ops."""
	kept = []
	for ch in changes or []:
		ov = ch.get("old")
		nv = ch.get("new")
		ov = "" if ov is None else ov
		nv = "" if nv is None else nv
		if str(ov) == str(nv):
			continue
		kept.append(
			{
				"fieldname": ch.get("field") or ch.get("fieldname"),
				"target_doctype": ch.get("dt") or ch.get("target_doctype") or default_doctype,
				"target_name": ch.get("dn") or ch.get("target_name") or default_name,
				"old_value": str(ov),
				"new_value": str(nv),
			}
		)
	return kept


def record_governance_event(
	dcs: str,
	event_code: str,
	action_label: str = "",
	source_endpoint: str = "",
	reason: str = "",
	revision_no=None,
	revision_reference: str = "",
	evidence_reference: str = "",
	changes=None,
	request_key: str = "",
	outcome: str = "Success",
) -> str:
	"""Insert one append-only governance event for ``dcs``.

	Returns the event name, or ``""`` when nothing actually changed (a no-op
	must not produce a misleading audit row). Never commits.
	"""
	rows = build_change_rows(changes, "Deal Cost Sheet", dcs)
	if not rows:
		return ""

	ev = frappe.new_doc("DCS Governance Event")
	ev.dcs = dcs
	ev.event_code = event_code
	ev.action_label = action_label
	ev.source_endpoint = source_endpoint
	ev.reason = reason or ""
	ev.revision_no = revision_no or 0
	ev.revision_reference = revision_reference or ""
	ev.evidence_reference = evidence_reference or ""
	ev.outcome = outcome
	ev.source_event_id = request_key or None  # NULL, never "" (lookups rely on truthiness)
	ev.changes = json.dumps(rows)
	ev.change_count = len(rows)
	# actor / event_timestamp / correlation_id are set by the guard from the
	# session and request context; values set here would be overwritten anyway.
	ev.actor = frappe.session.user
	ev.event_timestamp = now()
	ev.correlation_id = get_correlation_id()
	ev.flags.dcs_audit_write = 1
	# ignore_permissions is deliberate: no role holds `create` on the event
	# DocType, so the only way an event can exist is through this writer.
	ev.insert(ignore_permissions=True)
	return ev.name
