"""Shared plumbing for the governed Deal Cost Sheet services.

Each public endpoint in this package is a faithful port of a production
Server Script (see ``bsgroup/dcs/server_script_export``), wrapped by
:func:`governed_endpoint` which adds what the scripts could not provide:

* a DocType-level permission check before any business code runs;
* a per-request idempotency key (``make_request_key``) so a repeated
  identical request is answered from the earlier governance event instead of
  mutating twice;
* the single governance-event writer from :mod:`bsgroup.dcs.governance`.

Nothing here trusts a caller-supplied actor, timestamp, source or
correlation value. Role checks read ``Has Role`` exactly as the scripts did.
"""

import functools

import frappe
from frappe import _
from frappe.utils import now_datetime

from bsgroup.dcs import governance

# ---------------------------------------------------------------------------
# Role model (verbatim from the production scripts)
# ---------------------------------------------------------------------------
MD = "Managing Director"
CC = "Commercial Controller"
COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]
TECHNICAL_ROLES = ["Technical Engineer", "Project Engineer", "Project Manager", "Operations Manager"]
CUSTOMER_SIDE = ["Sales User", "Sales Manager", "Commercial Controller", "Managing Director"]
VENDOR_SIDE = ["Presales", "Sales Manager", "Commercial Controller", "Managing Director"]

MD_THRESHOLD = 16.0
CEILING = 26.0
MARGIN_FLOOR = 20.0


def get_user_roles(user=None):
	user = user or frappe.session.user
	rows = frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User"}, fields=["role"])
	return [r.get("role") for r in rows]


def has_any(roles, wanted):
	for r in wanted:
		if r in roles:
			return 1
	return 0


def matched(roles, wanted):
	return [r for r in wanted if r in roles]


def absf(v):
	return 0 - v if v < 0 else v


def r2(v):
	x = (v or 0) * 100.0
	if x < 0:
		return int(x - 0.5) / 100.0
	return int(x + 0.5) / 100.0


def r3(v):
	x = (v or 0) * 1000.0
	if x < 0:
		return int(x - 0.5) / 1000.0
	return int(x + 0.5) / 1000.0


def truthy_flag(v):
	return 1 if v in (1, "1", True, "true", "True", "YES", "yes", "TRUE") else 0


# ---------------------------------------------------------------------------
# Endpoint wrapper
# ---------------------------------------------------------------------------
_SKIP_ARGS = {"cmd", "csrf_token", "_", "ignore_permissions"}


def _clean_args(kwargs):
	return {k: v for k, v in (kwargs or {}).items() if k not in _SKIP_ARGS}


def governed_endpoint(endpoint, perm_doctype="Deal Cost Sheet", ptype="read", idempotent=True):
	"""Wrap a ported service.

	``fn(args)`` receives the request arguments as a dict (the script used
	``frappe.form_dict``) and returns the result dict (the script assigned
	``frappe.response["message"]``).
	"""

	def decorator(fn):
		@frappe.whitelist()
		@functools.wraps(fn)
		def wrapper(*a, **kwargs):
			args = _clean_args(kwargs)
			if frappe.session.user == "Guest" or not frappe.has_permission(perm_doctype, ptype):
				frappe.throw(_("Not permitted"), frappe.PermissionError)

			request_key = None
			if idempotent:
				request_key = governance.make_request_key(endpoint, args)
				prior = governance.find_replay(request_key)
				if prior:
					return {
						"ok": 1,
						"error": "",
						"idempotent_replay": 1,
						"governance_event": prior,
						"request_key": request_key,
						"state": {},
						"note": "This request was already recorded. Nothing was changed again.",
					}
			frappe.local.bsg_request_key = request_key
			try:
				result = fn(args)
			finally:
				frappe.local.bsg_request_key = None
			if isinstance(result, dict) and request_key:
				result.setdefault("request_key", request_key)
			return result

		wrapper.__wrapped_service__ = fn
		return wrapper

	return decorator


def current_request_key():
	return getattr(frappe.local, "bsg_request_key", None)


def audit_event(a_dcs, a_code, a_label, a_endpoint, a_reason, a_rev_no, a_rev_ref, a_evid, a_changes):
	"""Drop-in for the scripts' ``dcs_audit_event`` helper, routed through the single writer."""
	return governance.record_governance_event(
		dcs=a_dcs,
		event_code=a_code,
		action_label=a_label,
		source_endpoint=a_endpoint,
		reason=a_reason or "",
		revision_no=a_rev_no,
		revision_reference=a_rev_ref or "",
		evidence_reference=a_evid or "",
		changes=a_changes,
		request_key=current_request_key() or "",
	)


snapshot = governance.snapshot
diff_changes = governance.diff_changes


# ---------------------------------------------------------------------------
# NRC-1 narrative contract (still served by the `dcs_narrative_guard` Server
# Script - documented exception, see Section 4 of the implementation package)
# ---------------------------------------------------------------------------
NRC_UNAVAILABLE = "[withheld - governed redaction unavailable]"


def _call_nrc(items):
	"""Invoke the NRC-1 contract exactly as the scripts did (same request, same transaction)."""
	from frappe.utils.safe_exec import call_whitelisted_function

	saved = frappe.response.get("message")
	got = None
	try:
		call_whitelisted_function("dcs_narrative_guard", mode="redact_batch", items=items)
		got = frappe.response.get("nrc") or frappe.response.get("message")
	finally:
		frappe.response["nrc"] = None
		frappe.response["message"] = saved
	return got


def nrc_batch(items):
	out = {"ok": 0, "texts": [], "levels": [], "err": ""}
	if items is None:
		return out
	if len(items) == 0:
		out["ok"] = 1
		return out
	try:
		got = _call_nrc(items)
		if got:
			if got.get("ok") == 1 and got.get("contract") == "NRC-1" and (
				got.get("count") == len(items) or len(got.get("texts") or []) == len(items)
			):
				out["ok"] = 1
				out["texts"] = got.get("texts")
				out["levels"] = got.get("levels")
			else:
				out["err"] = "NRC-1 contract mismatch"
		else:
			out["err"] = "NRC-1 service returned no payload"
	except Exception as nerr:
		out["err"] = str(nerr)
	return out


def nrc_entry_check(labels, values, scope="Handover and delivery"):
	out = {"block": "", "warn": "", "delegated": 0}
	keys, items = [], []
	for i, v in enumerate(values):
		if v is not None and str(v) != "":
			items.append(str(v))
			keys.append(labels[i])
	if not items:
		return out
	got = nrc_batch(items)
	if got["ok"] != 1:
		out["warn"] = (
			"The governed narrative check (NRC-1) could not be executed for this note. "
			"Technical and operations projections withhold narrative values while the check is unavailable."
		)
		return out
	out["delegated"] = 1
	highs, poss = [], []
	for k, lv in enumerate(got["levels"]):
		if lv == "high":
			highs.append(keys[k])
		elif lv == "possible":
			poss.append(keys[k])
	if highs:
		out["block"] = (
			"The " + str(highs[0]) + " appears to disclose a commercial amount. " + scope
			+ " narrative is readable by operations, technical and project roles, so commercial figures must be recorded in the governed commercial fields of the Deal Cost Sheet (cost, selling, margin) or in the exposure amount field, not in operational notes. Remove the figure from the "
			+ str(highs[0]) + " and record it against the governed commercial field instead."
		)
	elif poss:
		out["warn"] = (
			"The " + str(poss[0])
			+ " contains a number that resembles a financial value. It has been accepted, but technical and operations projections will withhold it."
		)
	return out


def nrc_govern(items):
	"""Two-pass redaction with self-audit, as dcs_screen5 did."""
	first = nrc_batch(items)
	if first["ok"] != 1:
		return {"ok": 0, "texts": [], "redacted": 0, "reason": "The governed redaction service is unavailable. Operational narrative is withheld."}
	red = sum(1 for lv in first["levels"] if lv != "clean")
	second = nrc_batch(first["texts"])
	if second["ok"] != 1:
		return {"ok": 0, "texts": [], "redacted": 0, "reason": "The governed redaction self-audit could not complete. Operational narrative is withheld."}
	for lv in second["levels"]:
		if lv != "clean":
			return {"ok": 0, "texts": [], "redacted": 0, "reason": "The governed redaction self-audit detected residual commercial signal. Operational narrative is withheld."}
	return {"ok": 1, "texts": first["texts"], "redacted": red, "reason": ""}


# ---------------------------------------------------------------------------
# Handover condition helpers (shared by award / PO / handover / delivery)
# ---------------------------------------------------------------------------
def next_condition_no(sheet_name):
	rows = frappe.get_all(
		"DCS Handover Condition", filters={"dcs": sheet_name}, fields=["condition_no"],
		order_by="condition_no desc", limit_page_length=1,
	)
	n = 0
	for r in rows:
		n = r.get("condition_no") or 0
	return n + 1


def find_condition(sheet_name, key):
	rows = frappe.get_all(
		"DCS Handover Condition", filters={"dcs": sheet_name, "source_key": key},
		fields=["name", "state", "category"], limit_page_length=1,
	)
	for r in rows:
		return r
	return None


def raise_condition(sheet_name, key, title, category, domain, detail):
	existing = find_condition(sheet_name, key)
	if existing is not None:
		return existing.get("name")
	c = frappe.new_doc("DCS Handover Condition")
	c.dcs = sheet_name
	c.condition_no = next_condition_no(sheet_name)
	c.condition_title = title
	c.category = category
	c.original_category = category
	c.domain = domain
	c.state = "Open"
	c.detail = detail
	c.raised_by = frappe.session.user
	c.raised_on = now_datetime()
	c.auto_generated = 1
	c.source_key = key
	c.flags.dcs_api_write = 1
	# Conditions are governed history: only a service may raise one, and the
	# service has already validated authority and Deal Cost Sheet permission.
	c.insert(ignore_permissions=True)
	return c.name


def open_blockers(sheet_name):
	return frappe.get_all(
		"DCS Handover Condition",
		filters={"dcs": sheet_name, "category": "Blocker", "state": "Open"},
		fields=["name", "condition_title", "domain"],
	)


def clear_auto(sheet_name, key, note):
	c = find_condition(sheet_name, key)
	if c is None or c.get("state") != "Open":
		return 0
	d = frappe.get_doc("DCS Handover Condition", c.get("name"))
	d.state = "Cleared"
	d.cleared_by = frappe.session.user
	d.cleared_on = now_datetime()
	d.clearance_note = note
	d.flags.dcs_api_write = 1
	d.save()
	return 1


# ---------------------------------------------------------------------------
# Native timeline + notification emit (go-live Day 2) - shared tail of the scripts
# ---------------------------------------------------------------------------
def emit_timeline(dcs_name, text):
	"""Best-effort Comment + Notification Log; never raises (as in production)."""
	try:
		if not dcs_name or not text:
			return
		tlc = frappe.new_doc("Comment")
		tlc.comment_type = "Info"
		tlc.reference_doctype = "Deal Cost Sheet"
		tlc.reference_name = dcs_name
		tlc.content = text
		tlc.insert(ignore_permissions=True)
		owner = frappe.db.get_value("Deal Cost Sheet", dcs_name, "deal_owner")
		delivery = frappe.db.get_value("Deal Cost Sheet", dcs_name, "custom_delivery_owner")
		users = []
		if owner:
			users.append(owner)
		if delivery and delivery not in users:
			users.append(delivery)
		for u in users:
			if u != frappe.session.user:
				tln = frappe.new_doc("Notification Log")
				tln.for_user = u
				tln.from_user = frappe.session.user
				tln.type = "Alert"
				tln.document_type = "Deal Cost Sheet"
				tln.document_name = dcs_name
				tln.subject = text
				tln.insert(ignore_permissions=True)
	except Exception:
		pass


def dcs_exists_and_open(dcs_name, result):
	"""Common preamble checks; fills result['error'] and returns False when blocked."""
	if not dcs_name:
		result["error"] = "dcs is required."
		return False
	if not frappe.db.exists("Deal Cost Sheet", dcs_name):
		result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
		return False
	if frappe.db.get_value("Deal Cost Sheet", dcs_name, "docstatus") == 2:
		result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
		return False
	return True
