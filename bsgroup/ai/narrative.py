# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Pure, framework-free helpers for AI-assisted quotation narrative.

This module deliberately imports **nothing from frappe** so that the
safety-critical policy - what is sent to the model, what is treated as a
missing cost, when generation is blocked by an approval, and what may be
written back onto a draft - is fully unit-testable in isolation and easy to
review. All I/O (reading the DCS, calling Claude, saving the Quotation) lives
in ``quotation_generator.py``.

Two invariants this module encodes:

1. **No figures to the model, no figures from the model.** The context built
   for Claude carries only descriptive fields (subject, scope text, item
   headers / names / quantities / units / brands). Costs, selling rates,
   margins and GP are never included. The model is asked for prose only.
2. **Flag, never invent.** Missing costs are reported, not filled. Any model
   output still carrying a ``[NEEDS INPUT ...]`` marker is surfaced as a flag
   and is *not* written onto the customer-facing draft.
"""

import json
import re

NEEDS_INPUT_MARKER = "[NEEDS INPUT"

# Narrative fields on Quotation that AI output may populate. These are all
# level-0, descriptive fields - never a rate, quantity, amount or tax field.
NARRATIVE_FIELDS = ("custom_subject", "custom_scope_overview", "custom_customer_notes")


def _flt(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0


def detect_missing_costs(items, resources=None, charges=None, dcs_addtional_item_configured=True):
	"""Return a list of missing/zero-cost issues found on a DCS.

	Each issue is a dict: ``{"area", "ref", "issue"}``. An empty list means
	every priced row carries a cost and a selling figure and nothing needs a
	human before a quotation is produced. This function never fills a value -
	it only reports.
	"""
	issues = []
	resources = resources or []
	charges = charges or []

	for idx, row in enumerate(items or [], start=1):
		ref = row.get("item_code") or row.get("item_name") or f"Item row {idx}"
		qty = _flt(row.get("qty"))
		if not row.get("item_code") and not row.get("item_name"):
			issues.append({"area": "item", "ref": f"row {idx}", "issue": "Row has no item and no description."})
		if qty <= 0:
			issues.append({"area": "item", "ref": ref, "issue": "Quantity is zero or blank."})
		if _flt(row.get("cost_rate")) <= 0:
			issues.append({"area": "item", "ref": ref, "issue": "Cost rate is zero or blank."})
		if _flt(row.get("selling_rate")) <= 0:
			issues.append({"area": "item", "ref": ref, "issue": "Selling rate is zero or blank."})

	for idx, row in enumerate(resources, start=1):
		ref = row.get("role") or row.get("description") or f"Resource row {idx}"
		if _flt(row.get("cost_rate")) <= 0 and _flt(row.get("cost_amount")) <= 0:
			issues.append({"area": "resource", "ref": ref, "issue": "Resource cost is zero or blank."})

	total_charges = sum(_flt(c.get("amount")) for c in charges)
	if total_charges and not dcs_addtional_item_configured:
		issues.append({
			"area": "additional_charges",
			"ref": "BS Group Settings",
			"issue": "Additional charges exist but 'DCS Addtional Item' is not configured, so they cannot be transferred.",
		})

	return issues


def approval_gate_block_reason(dcs):
	"""Return a human-readable reason if a customer quotation must NOT be
	generated for this DCS yet, else ``None``.

	Conservative policy, mirroring the DCS commercial controls:

	* margin gate is ``Blocked`` -> block;
	* approval is required (``Managing Director`` / ``Blocked``) but no
	  approval has been recorded (``custom_approved_on`` empty) -> block;
	* an approval is actively in progress (``custom_approval_state`` is
	  ``Pending Endorsement`` or ``In Negotiation``) -> block, so a quotation is
	  never generated out from under a sign-off that is still being decided.

	A caller holding an override role may bypass this (decided in
	quotation_generator, not here), and the override is always audited.
	"""
	gate = (dcs.get("custom_margin_gate") or "").strip()
	if gate == "Blocked":
		reason = (dcs.get("custom_margin_gate_reason") or "").strip()
		return "Margin gate is Blocked" + (f": {reason}" if reason else "") + "."

	approval_required = (dcs.get("custom_approval_required") or "").strip()
	approved_on = (dcs.get("custom_approved_on") or "")
	if approval_required in ("Managing Director", "Blocked") and not approved_on:
		return f"Approval required ({approval_required}) but not yet recorded."

	approval_state = (dcs.get("custom_approval_state") or "").strip()
	if approval_state in ("Pending Endorsement", "In Negotiation") and not approved_on:
		return f"A commercial approval is in progress ({approval_state})."

	return None


def build_ai_context(dcs, items):
	"""Build the redacted, figure-free context handed to the model.

	Only descriptive fields are included. No cost, selling, margin or GP value
	ever appears here.
	"""
	context_items = []
	for idx, row in enumerate(items or [], start=1):
		# Deliberately no qty and no cost/selling/margin: the model writes prose
		# only and must not state or alter any number. Line ordering + names are
		# enough to describe each line.
		context_items.append({
			"line": idx,
			"header": row.get("header") or "",
			"item_name": row.get("item_name") or row.get("item_code") or "",
			"brand": row.get("brand") or "",
			"uom": row.get("uom") or row.get("stock_uom") or "",
			"existing_description": _strip_html(row.get("description") or ""),
		})
	return {
		"subject": dcs.get("subject") or "",
		"scope_overview": _strip_html(dcs.get("scope_overview") or ""),
		"customer_notes": dcs.get("customer_notes") or "",
		"company": dcs.get("company") or "",
		"items": context_items,
	}


SYSTEM_PROMPT = (
	"You are a proposal writer for an IT systems-integration company. You turn an "
	"internal deal cost sheet into clear, professional, customer-facing quotation "
	"narrative.\n\n"
	"HARD RULES - follow every one:\n"
	"1. Write prose only. Never state, invent, alter, guess or recompute any price, "
	"rate, cost, margin, discount, quantity, date, serial or part number. Those come "
	"from the ERP, not from you.\n"
	"2. Use ONLY the facts in the provided context. If something needed for a good "
	"sentence is missing, do not fabricate it - write the literal marker "
	"'[NEEDS INPUT: <what is missing>]' in place and move on.\n"
	"3. Do not promise timelines, warranties, SLAs or commercial terms that are not "
	"in the context.\n"
	"4. Keep it concise and businesslike. British English.\n"
	"5. Reply with a single JSON object and nothing else, using exactly these keys:\n"
	'   "subject": short one-line quotation subject,\n'
	'   "scope_overview_html": a few short paragraphs of scope narrative as simple HTML '
	"(<p>, <ul>, <li> only),\n"
	'   "customer_notes": short plain-text notes (assumptions/exclusions) or "",\n'
	'   "item_descriptions": array of {"line": <line number from context>, "text": '
	"<one-line customer-facing description, no prices>},\n"
	'   "needs_input": array of strings naming anything you could not complete.\n'
)


def build_prompt(context, instructions=None):
	"""Return ``(system_prompt, user_message)`` for the model call."""
	user = {
		"instructions": (instructions or "").strip() or "Generate the quotation narrative from this deal cost sheet.",
		"deal_cost_sheet": context,
	}
	user_message = (
		"Here is the deal cost sheet context as JSON. Produce the quotation narrative "
		"JSON per the rules.\n\n" + json.dumps(user, ensure_ascii=False, indent=2)
	)
	return SYSTEM_PROMPT, user_message


def parse_ai_response(text):
	"""Parse the model's JSON reply defensively.

	Returns a normalised dict: ``{"subject", "scope_overview_html",
	"customer_notes", "item_descriptions": [{"line", "text"}], "needs_input": []}``.
	Raises ValueError if no JSON object can be recovered.
	"""
	data = _extract_json_object(text)

	subject = _as_str(data.get("subject"))
	scope = _as_str(data.get("scope_overview_html"))
	notes = _as_str(data.get("customer_notes"))

	item_descriptions = []
	for entry in data.get("item_descriptions") or []:
		if not isinstance(entry, dict):
			continue
		try:
			line = int(entry.get("line"))
		except (TypeError, ValueError):
			continue
		desc = _as_str(entry.get("text"))
		if desc:
			item_descriptions.append({"line": line, "text": desc})

	needs_input = [_as_str(n) for n in (data.get("needs_input") or []) if _as_str(n)]

	return {
		"subject": subject,
		"scope_overview_html": scope,
		"customer_notes": notes,
		"item_descriptions": item_descriptions,
		"needs_input": needs_input,
	}


def select_narrative_updates(parsed, existing, items, overwrite=False):
	"""Decide what to write onto the draft Quotation.

	* Only narrative fields are ever returned - never a figure field.
	* A value that still contains a ``[NEEDS INPUT ...]`` marker is NOT written;
	  it is reported in the returned ``needs_input`` list instead, so no
	  placeholder leaks onto a customer document.
	* Unless ``overwrite`` is true, a field that already has content on the
	  draft is left as-is (the deterministic ``make_quotation`` copies subject /
	  scope / notes from the DCS; we only fill blanks by default).

	Returns ``(field_updates: dict, item_updates: list[{line,text}], needs_input: list[str])``.
	"""
	needs_input = list(parsed.get("needs_input") or [])
	field_updates = {}

	candidates = {
		"custom_subject": parsed.get("subject"),
		"custom_scope_overview": parsed.get("scope_overview_html"),
		"custom_customer_notes": parsed.get("customer_notes"),
	}
	for field, value in candidates.items():
		value = _as_str(value)
		if not value:
			continue
		if _has_needs_input(value):
			needs_input.append(f"{field}: model marked missing information")
			continue
		if not overwrite and _as_str(existing.get(field)):
			continue
		field_updates[field] = value

	item_count = len(items or [])
	item_updates = []
	for entry in parsed.get("item_descriptions") or []:
		line = entry.get("line")
		text = _as_str(entry.get("text"))
		if not text or _has_needs_input(text):
			if text:
				needs_input.append(f"item line {line}: model marked missing information")
			continue
		if not isinstance(line, int) or line < 1 or line > item_count:
			continue
		row = items[line - 1]
		if not overwrite and _as_str(row.get("description")):
			continue
		item_updates.append({"line": line, "text": text})

	# De-duplicate needs_input while preserving order.
	seen = set()
	deduped = []
	for n in needs_input:
		if n not in seen:
			seen.add(n)
			deduped.append(n)

	return field_updates, item_updates, deduped


# ---------------------------------------------------------------------------
# small internal helpers
# ---------------------------------------------------------------------------

def _as_str(value):
	if value is None:
		return ""
	return str(value).strip()


def _has_needs_input(value):
	return NEEDS_INPUT_MARKER.lower() in (value or "").lower()


def _strip_html(value):
	text = re.sub(r"<[^>]+>", " ", value or "")
	return re.sub(r"\s+", " ", text).strip()


def _extract_json_object(text):
	"""Recover a JSON object from model text that may be fenced or padded."""
	if not text:
		raise ValueError("empty model response")
	# Prefer a fenced ```json block if present.
	fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
	raw = fence.group(1) if fence else None
	if raw is None:
		start = text.find("{")
		end = text.rfind("}")
		if start == -1 or end == -1 or end <= start:
			raise ValueError("no JSON object found in model response")
		raw = text[start : end + 1]
	try:
		data = json.loads(raw)
	except json.JSONDecodeError as exc:
		raise ValueError(f"model response was not valid JSON: {exc}")
	if not isinstance(data, dict):
		raise ValueError("model response JSON was not an object")
	return data
