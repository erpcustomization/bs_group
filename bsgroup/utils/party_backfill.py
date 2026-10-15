"""Allow-list party backfill for Presales Request / Deal Cost Sheet (REL-1, H-1 follow-up).

The bulk patch ``bsgroup.patches.v0_1.backfill_party_fields`` proposes a party for
*every* record and, when applied, writes all of them. The read-only production
assessment of 2026-09-27 showed that an all-or-nothing apply would clear 100 real
Customer links, so historical party data is corrected only through an explicit
**manifest** (allow-list) from now on.

Nothing in this module is whitelisted and it is not registered in ``patches.txt``:
installing or migrating the app never writes business data, and nothing here can be
reached over the API. The only execution surface is the ``Party Backfill Run`` DocType
(System Manager: create + read; a run is immutable once inserted), whose controller
calls :func:`execute` inside the insert transaction. It is therefore driven exactly
like any other document - from the desk form, or from the System Console with
``frappe.get_doc({...}).insert()`` under the sandbox's ordinary permission checks.

Manifest
--------
A JSON document stored **privately on the site** (a private ``File``; it is never part
of the repository), with ``schema = bsgroup/party-backfill-allowlist/1`` and one entry
per record: ``(doctype, name)``, the approved **before** values, the approved
**after** values and the **source fingerprint** captured at assessment time (record
docstatus, its own link fields, the Opportunity's party, that party's organisation
name, and every Quotation linked back to the record with the party it was quoted
to). ``manifest_sha256`` - the SHA-256 of the exact bytes stored on the site - is the
approval token: an Apply or Restore is refused unless the caller supplies it.

Evaluation and writing
----------------------
Each entry is evaluated against the live database and **rejected** - never adjusted -
when the record is missing, its current values differ from the approved before values,
any source datum or link differs from the fingerprint, or the proposal recomputed from
live data (the bulk patch's own rules) differs from the approved after values. A record
already holding the after values is ``ALREADY_APPLIED``. A populated party is preserved
unless the entry says ``"allow_overwrite_populated": true``.

In Apply mode every eligible record is evaluated a **second time with row locks**
(``SELECT ... FOR UPDATE`` on the record, its Opportunity, its party and its
back-linked Quotations) immediately before the write, inside the same transaction; if
anything differs from the first evaluation the record is
``REJECTED_CHANGED_BETWEEN_EVALUATION_AND_WRITE`` and left alone. After each write the
row is re-read and must equal the approved after values, or the whole run raises and
the transaction rolls back. Writes use ``frappe.db.set_value(update_modified=False)``.

Gate
----
Writes happen only when ``mode`` is Apply/Restore **and** ``bsg_apply_party_backfill``
is set in site config **and** the supplied ``manifest_sha256`` matches the stored
manifest. Whatever the outcome of an Apply/Restore attempt - refused, applied, or
failed anywhere after the permission check (input validation, manifest loading,
evaluation, write) - the flag is removed from site config again in a ``finally``
block, so it is never left armed; if it cannot be removed the run raises and the
transaction fails.

Outputs
-------
``execute`` returns a summary plus the evaluation CSV and, for records written, a
before-values JSON export (per record: before, after, fields written) that ``Restore``
consumes to put those records back, record by record, only where they still hold the
approved after values. The ``Party Backfill Run`` document stores the summary and
attaches both exports as private files.
"""

import csv
import hashlib
import io
import json
import os

import frappe
from frappe import _
from frappe.utils import cint

from bsgroup.patches.v0_1.backfill_party_fields import _proposal
from bsgroup.utils.party import PARTY_TYPES, organisation_name_for

CONF_FLAG = "bsg_apply_party_backfill"
SCHEMA = "bsgroup/party-backfill-allowlist/1"
SCHEMA_BEFORE_VALUES = SCHEMA + "/before-values"

MODE_DRY_RUN, MODE_APPLY, MODE_RESTORE = "Dry Run", "Apply", "Restore"
MODES = (MODE_DRY_RUN, MODE_APPLY, MODE_RESTORE)

TARGETS = ("Presales Request", "Deal Cost Sheet")
PARTY_FIELDS = ("party_type", "party", "organisation_name", "customer")
LINK_FIELDS = {
	"Deal Cost Sheet": ("opportunity", "presales_request", "custom_quotation", "project"),
	"Presales Request": ("opportunity", "custom_deal_cost_sheet", "custom_quotation"),
}
BACKLINK_FIELD = {"Deal Cost Sheet": "custom_deal_cost_sheet", "Presales Request": "custom_presales_request"}

ELIGIBLE = "ELIGIBLE"
APPLIED = "APPLIED"
ALREADY_APPLIED = "ALREADY_APPLIED"
REJECTED_DOCTYPE = "REJECTED_DOCTYPE_NOT_ALLOWED"
REJECTED_ENTRY = "REJECTED_ENTRY_INVALID"
REJECTED_MISSING = "REJECTED_RECORD_MISSING"
REJECTED_BEFORE = "REJECTED_BEFORE_VALUES_CHANGED"
REJECTED_SOURCE = "REJECTED_SOURCE_OR_LINKS_CHANGED"
REJECTED_POPULATED = "REJECTED_POPULATED_PARTY_NOT_APPROVED"
REJECTED_PROPOSAL = "REJECTED_RECOMPUTED_PROPOSAL_DIFFERS"
REJECTED_STATE = "REJECTED_CURRENT_STATE_NOT_APPROVED_AFTER"
REJECTED_RACE = "REJECTED_CHANGED_BETWEEN_EVALUATION_AND_WRITE"
REJECTED = (
	REJECTED_DOCTYPE, REJECTED_ENTRY, REJECTED_MISSING, REJECTED_BEFORE, REJECTED_SOURCE,
	REJECTED_POPULATED, REJECTED_PROPOSAL, REJECTED_STATE, REJECTED_RACE,
)


# --- helpers ---------------------------------------------------------------------------

def _n(value):
	"""NULL and '' are the same absence; everything else is compared exactly."""
	return None if value is None or value == "" else value


def _party_values(mapping):
	return {f: _n((mapping or {}).get(f)) for f in PARTY_FIELDS}


def _diff(a, b):
	return {k: {"live": a.get(k), "approved": b.get(k)} for k in set(a) | set(b) if a.get(k) != b.get(k)}


def _sha256(data):
	return hashlib.sha256(data).hexdigest()


def snapshot(doctype, name, lock=False):
	"""Current before-values and source fingerprint of one record, or None if it is missing.

	``lock=True`` reads the record, its Opportunity, its party and its back-linked
	Quotations with ``SELECT ... FOR UPDATE`` so that, inside the apply transaction,
	nothing can change between this read and the write. The fingerprint covers values,
	not timestamps, so a re-save that changes nothing relevant does not block a record.
	"""
	if doctype not in TARGETS:
		return None
	row = frappe.db.get_value(
		doctype, name, ["name", "docstatus", *PARTY_FIELDS, *LINK_FIELDS[doctype]], as_dict=True, for_update=lock
	)
	if not row:
		return None
	opp = None
	if row.get("opportunity"):
		opp = frappe.db.get_value(
			"Opportunity", row.opportunity, ["opportunity_from", "party_name"], as_dict=True, for_update=lock
		)
	party_org = None
	if opp and opp.opportunity_from in PARTY_TYPES and opp.party_name:
		if lock:
			frappe.db.get_value(opp.opportunity_from, opp.party_name, "name", for_update=True)
		party_org = _n(organisation_name_for(opp.opportunity_from, opp.party_name))
	if lock:
		quotations = frappe.db.sql(
			f"select name, quotation_to, party_name from `tabQuotation` where `{BACKLINK_FIELD[doctype]}` = %s order by name for update",
			(name,), as_dict=True,
		)
	else:
		quotations = frappe.get_all(
			"Quotation", filters={BACKLINK_FIELD[doctype]: name},
			fields=["name", "quotation_to", "party_name"], order_by="name asc", limit_page_length=0,
		)
	source = {
		"docstatus": cint(row.docstatus),
		"links": {f: _n(row.get(f)) for f in LINK_FIELDS[doctype]},
		"opportunity_exists": bool(opp),
		"opportunity_from": _n(opp.opportunity_from) if opp else None,
		"party_name": _n(opp.party_name) if opp else None,
		"party_organisation_name": party_org,
		"quotations": sorted(
			({"name": q.name, "quotation_to": _n(q.quotation_to), "party_name": _n(q.party_name)} for q in quotations),
			key=lambda q: q["name"],
		),
	}
	return {"before": _party_values(row), "source": source, "row": row}


def _normalise_source(source):
	source = source or {}
	return {
		"docstatus": cint(source.get("docstatus")),
		"links": {k: _n(v) for k, v in (source.get("links") or {}).items()},
		"opportunity_exists": bool(source.get("opportunity_exists")),
		"opportunity_from": _n(source.get("opportunity_from")),
		"party_name": _n(source.get("party_name")),
		"party_organisation_name": _n(source.get("party_organisation_name")),
		"quotations": sorted(
			(
				{"name": q.get("name"), "quotation_to": _n(q.get("quotation_to")), "party_name": _n(q.get("party_name"))}
				for q in (source.get("quotations") or [])
			),
			key=lambda q: q["name"] or "",
		),
	}


def _recomputed_after(doctype, row):
	pr = _proposal(doctype, row)
	return {
		"party_type": _n(pr["party_type"]),
		"party": _n(pr["party"]),
		"organisation_name": _n(pr["organisation_name"]),
		"customer": _n(pr["new_customer"]),
	}


def evaluate(entry, lock=False):
	"""Classify one manifest entry against the live database. Never writes."""
	doctype, name = entry.get("doctype"), entry.get("name")
	if doctype not in TARGETS:
		return {"status": REJECTED_DOCTYPE, "reason": f"{doctype!r} is not a party-model doctype"}
	before, after = _party_values(entry.get("before")), _party_values(entry.get("after"))
	if not name or before == after or not (after["party_type"] and after["party"]):
		return {"status": REJECTED_ENTRY, "reason": "entry has no name, no change, or an incomplete after-party"}
	live = snapshot(doctype, name, lock=lock)
	if not live:
		return {"status": REJECTED_MISSING, "reason": f"{doctype} {name} does not exist"}
	if live["before"] == after:
		return {"status": ALREADY_APPLIED, "reason": "record already holds the approved after values", "live": live}
	if live["before"] != before:
		return {"status": REJECTED_BEFORE, "reason": json.dumps(_diff(live["before"], before), default=str), "live": live}
	if _normalise_source(live["source"]) != _normalise_source(entry.get("source")):
		return {
			"status": REJECTED_SOURCE,
			"reason": json.dumps(_diff(_normalise_source(live["source"]), _normalise_source(entry.get("source"))), default=str),
			"live": live,
		}
	if (before["party_type"] or before["party"]) and not entry.get("allow_overwrite_populated"):
		return {"status": REJECTED_POPULATED, "reason": "record already carries a party and the entry does not approve overwriting it", "live": live}
	recomputed = _recomputed_after(doctype, live["row"])
	if recomputed != after:
		return {"status": REJECTED_PROPOSAL, "reason": json.dumps(_diff(recomputed, after), default=str), "live": live}
	changes = {f: after[f] for f in PARTY_FIELDS if after[f] != live["before"][f]}
	return {"status": ELIGIBLE, "reason": "", "live": live, "changes": changes}


# --- manifest ----------------------------------------------------------------------------

def load_manifest(manifest, expected_schema=SCHEMA):
	"""Return (document, sha256, label).

	``manifest`` is the ``file_url`` of a **private** File on this site (the production
	path), a dict (tests), or an absolute filesystem path (bench execute on a bench).
	"""
	if isinstance(manifest, dict):
		raw = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
		label = "<in-memory>"
	elif isinstance(manifest, str) and manifest.startswith("/private/files/"):
		file_name = frappe.db.get_value("File", {"file_url": manifest, "is_private": 1}, "name")
		if not file_name:
			frappe.throw(_("Manifest {0} is not a private File on this site.").format(manifest))
		try:
			content = frappe.get_doc("File", file_name).get_content()
		except Exception as e:  # noqa: BLE001 - surface as a validation failure, never a half-run
			frappe.throw(_("Manifest {0} could not be read: {1}").format(manifest, e))
		raw = content.encode("utf-8") if isinstance(content, str) else bytes(content)
		label = manifest
	elif isinstance(manifest, str) and os.path.isabs(manifest):
		with open(manifest, "rb") as f:
			raw = f.read()
		label = manifest
	else:
		frappe.throw(_("Manifest must be the file_url of a private File (/private/files/...)."))
	try:
		doc = json.loads(raw.decode("utf-8"))
	except (UnicodeDecodeError, ValueError) as e:
		frappe.throw(_("Manifest {0} is not valid JSON: {1}").format(label, e))
	if not isinstance(doc, dict) or doc.get("schema") != expected_schema:
		frappe.throw(_("Manifest schema {0} is not {1}.").format(doc.get("schema"), expected_schema))
	entries = doc.get("entries") if expected_schema == SCHEMA else doc.get("records")
	if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
		frappe.throw(_("Manifest {0} has no list of records.").format(label))
	keys = [(e.get("doctype"), e.get("name")) for e in entries]
	if len(set(keys)) != len(keys):
		frappe.throw(_("Manifest contains duplicate records."))
	return doc, _sha256(raw), label


def _gate(mode, provided_sha, actual_sha):
	"""None when writing is permitted, else the reason it is refused."""
	if mode == MODE_DRY_RUN:
		return "dry run"
	if not cint(frappe.conf.get(CONF_FLAG)):
		return f"apply gate off: site config {CONF_FLAG} is not set"
	if not provided_sha or provided_sha.strip().lower() != actual_sha.lower():
		return "manifest sha256 not supplied or does not match the manifest stored on the site"
	return None


def _flag_still_set():
	"""Re-read the merged site configuration from disk (never the cached process copy)."""
	return bool(cint((frappe.get_site_config(cached=False) or {}).get(CONF_FLAG)))


def clear_flag():
	"""Remove the arming flag from site config and from the running process.

	Raises when the flag cannot be verifiably removed - the caller's transaction then fails
	rather than finishing with an armed site. Idempotent when the flag is already absent.
	"""
	from frappe.installer import update_site_config

	try:
		update_site_config(CONF_FLAG, "None")  # the literal "None" deletes the key (frappe.installer._update_config_file)
	except Exception as e:  # noqa: BLE001
		frappe.conf.pop(CONF_FLAG, None)
		frappe.throw(_("Could not remove {0} from site config ({1}); the run is aborted and rolled back.").format(CONF_FLAG, e))
	frappe.conf.pop(CONF_FLAG, None)
	if _flag_still_set():
		frappe.throw(_("{0} is still set after removal (is it in common_site_config.json?); the run is aborted and rolled back.").format(CONF_FLAG))
	return True


# --- exports -----------------------------------------------------------------------------

def _evaluation_csv(results, run_id):
	out = io.StringIO()
	cols = ["run_id", "doctype", "name", "status", "reason", "written"]
	cols += [f"before_{f}" for f in PARTY_FIELDS] + [f"after_{f}" for f in PARTY_FIELDS]
	w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
	w.writeheader()
	for r in results:
		row = {"run_id": run_id, "doctype": r["doctype"], "name": r["name"], "status": r["status"], "reason": r["reason"], "written": r["written"]}
		row.update({f"before_{k}": v for k, v in (r.get("before") or {}).items()})
		row.update({f"after_{k}": v for k, v in (r.get("after") or {}).items()})
		w.writerow(row)
	return out.getvalue()


def _before_values_json(results, manifest_sha256, run_id):
	payload = {
		"schema": SCHEMA_BEFORE_VALUES,
		"site": frappe.local.site,
		"run_id": run_id,
		"manifest_sha256": manifest_sha256,
		"exported_at": frappe.utils.now(),
		"records": [
			{"doctype": r["doctype"], "name": r["name"], "before": r["before"], "after": r["after"], "written_fields": r["written_fields"]}
			for r in results if r["written"]
		],
	}
	return json.dumps(payload, indent=1, ensure_ascii=False, default=str)


# --- core --------------------------------------------------------------------------------

def _write(doctype, name, changes, approved_after):
	frappe.db.set_value(doctype, name, changes, update_modified=False)
	now = _party_values(frappe.db.get_value(doctype, name, list(PARTY_FIELDS), as_dict=True))
	if now != approved_after:
		frappe.throw(
			_("{0} {1}: values after write {2} do not equal the approved after values {3}; run aborted and rolled back.")
			.format(doctype, name, now, approved_after)
		)


def _apply(doc, sha, writing):
	results = []
	for entry in doc.get("entries") or []:
		ev = evaluate(entry)
		res = {
			"doctype": entry.get("doctype"), "name": entry.get("name"), "status": ev["status"], "reason": ev["reason"],
			"before": (ev.get("live") or {}).get("before") or _party_values(entry.get("before")),
			"after": _party_values(entry.get("after")), "written": 0, "written_fields": [],
		}
		if writing and ev["status"] == ELIGIBLE:
			# second evaluation under row locks: nothing may have moved since the first one
			locked = evaluate(entry, lock=True)
			if locked["status"] != ELIGIBLE or locked.get("changes") != ev["changes"]:
				res.update(status=REJECTED_RACE, reason=f"record changed during the run: {locked['status']} {locked.get('reason', '')}"[:500])
			else:
				_write(entry["doctype"], entry["name"], locked["changes"], res["after"])
				res.update(status=APPLIED, written=1, written_fields=sorted(locked["changes"]))
		results.append(res)
	return results


def _restore(doc, writing):
	results = []
	for rec in doc.get("records") or []:
		doctype, name = rec["doctype"], rec["name"]
		before, after = _party_values(rec.get("before")), _party_values(rec.get("after"))
		res = {"doctype": doctype, "name": name, "before": before, "after": after, "written": 0, "written_fields": [], "reason": ""}
		row = frappe.db.get_value(doctype, name, list(PARTY_FIELDS), as_dict=True, for_update=writing) if doctype in TARGETS else None
		if not row:
			res.update(status=REJECTED_MISSING, reason=f"{doctype} {name} does not exist")
		elif _party_values(row) == before:
			res.update(status=ALREADY_APPLIED, reason="record already holds the before values")
		elif _party_values(row) != after:
			res.update(status=REJECTED_STATE, reason=json.dumps(_diff(_party_values(row), after), default=str))
		else:
			res.update(status=ELIGIBLE)
			if writing:
				changes = {f: before[f] for f in PARTY_FIELDS if before[f] != after[f]}
				_write(doctype, name, changes, before)
				res.update(status=APPLIED, written=1, written_fields=sorted(changes))
		results.append(res)
	return results


def execute(mode, manifest, manifest_sha256=None, run_id=None):
	"""Evaluate a manifest and, in Apply/Restore behind the gate, write the eligible records.

	Not whitelisted; called by the ``Party Backfill Run`` controller inside its insert
	transaction. Returns ``{"summary": {...}, "evaluation_csv": str, "before_values_json": str|None}``.
	``run_id`` (the run document's name) is stamped into both exports so each run's files are distinct.

	For an Apply or Restore attempt the arming flag is removed from site config in every
	case - refused, applied, or failed anywhere after the permission check (bad mode,
	unreadable or invalid manifest, evaluation or write error). If it cannot be removed the
	run raises, so the transaction fails instead of completing on an armed site.
	"""
	frappe.only_for("System Manager")  # permission check before any configuration mutation
	armed = mode in (MODE_APPLY, MODE_RESTORE)
	run_id = run_id or frappe.generate_hash(length=12)
	try:
		if mode not in MODES:
			frappe.throw(_("Mode must be one of {0}.").format(", ".join(MODES)))
		doc, sha, label = load_manifest(manifest, SCHEMA_BEFORE_VALUES if mode == MODE_RESTORE else SCHEMA)
		refusal = _gate(mode, manifest_sha256, sha)
		if mode == MODE_DRY_RUN and manifest_sha256 and manifest_sha256.strip().lower() != sha.lower():
			refusal = "dry run; note: the supplied sha256 does not match the manifest stored on the site"
		writing = refusal is None
		results = _restore(doc, writing) if mode == MODE_RESTORE else _apply(doc, sha, writing)
	finally:
		if armed:
			clear_flag()
	summary = {
		"run_id": run_id,
		"mode": mode,
		"outcome": ("applied" if mode == MODE_APPLY else "restored") if writing else ("refused" if mode != MODE_DRY_RUN else "dry run"),
		"refusal": refusal if mode != MODE_DRY_RUN else None,
		"manifest": label, "manifest_sha256": sha, "entries": len(results),
		"by_status": {s: sum(1 for r in results if r["status"] == s) for s in sorted({r["status"] for r in results})},
		"eligible": sum(1 for r in results if r["status"] in (ELIGIBLE, APPLIED)),
		"written": sum(r["written"] for r in results),
		"rejected": sum(1 for r in results if r["status"] in REJECTED),
		"flag_cleared": True if armed else None,
		"flag_now": cint(frappe.conf.get(CONF_FLAG)),
	}
	return {
		"summary": summary,
		"evaluation_csv": _evaluation_csv(results, run_id),
		"before_values_json": _before_values_json(results, sha, run_id) if (writing and mode == MODE_APPLY) else None,
	}
