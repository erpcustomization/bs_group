# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Server-side, AI-assisted DCS -> Quotation draft generation.

What this does and, just as importantly, what it does not:

* It reuses the existing, vetted ``make_quotation`` on Deal Cost Sheet to build
  the Quotation. Every figure - rates, quantities, amounts, taxes, company
  currency, additional charges - therefore comes from the ERP's own
  deterministic calculation, never from the model.
* Claude is asked only for *narrative* (subject, scope overview, customer notes,
  per-line customer descriptions). Its output is applied only to those
  descriptive fields, and only after ``[NEEDS INPUT]`` markers are stripped out
  and reported.
* Missing or zero costs are flagged and, by default, stop generation. They are
  never invented or filled.
* Existing permissions, the DCS margin gate and approval state are enforced
  before anything is created.
* The result is always a **draft** Quotation (docstatus 0). Nothing is
  submitted, sent or otherwise finalised here.

Public whitelisted endpoints:
* ``preview_dcs_readiness(source_name)`` - read-only; reports blockers.
* ``generate_quotation_from_dcs(source_name, ...)`` - creates the draft.
"""

import json

import frappe
from frappe import _

from bsgroup.ai import narrative

# Roles allowed to override the approval / margin-gate block and to proceed
# despite flagged missing costs. Deliberately narrow.
OVERRIDE_ROLES = ("System Manager", "Sales Manager")


def _can_override():
	return bool(set(frappe.get_roles()) & set(OVERRIDE_ROLES))


def _dcs_as_dict(dcs):
	"""Flatten the DCS document into the plain dicts the pure helpers expect."""
	items = [
		{
			"item_code": r.get("item_code"),
			"item_name": r.get("item_name"),
			"brand": r.get("brand"),
			"header": r.get("header"),
			"qty": r.get("qty"),
			"uom": r.get("uom") or r.get("stock_uom"),
			"stock_uom": r.get("stock_uom"),
			"cost_rate": r.get("cost_rate"),
			"selling_rate": r.get("selling_rate"),
			"description": r.get("description"),
		}
		for r in (dcs.get("items") or [])
	]
	resources = [
		{"role": r.get("role"), "description": r.get("description"), "cost_rate": r.get("cost_rate"), "cost_amount": r.get("cost_amount")}
		for r in (dcs.get("resources") or [])
	]
	charges = [{"amount": c.get("amount"), "description": c.get("description")} for c in (dcs.get("addtional_charges") or [])]
	header = {
		"subject": dcs.get("subject"),
		"scope_overview": dcs.get("scope_overview"),
		"customer_notes": dcs.get("customer_notes"),
		"company": dcs.get("company"),
		"custom_margin_gate": dcs.get("custom_margin_gate"),
		"custom_margin_gate_reason": dcs.get("custom_margin_gate_reason"),
		"custom_approval_required": dcs.get("custom_approval_required"),
		"custom_approved_on": dcs.get("custom_approved_on"),
	}
	return header, items, resources, charges


def _readiness(source_name):
	"""Shared read-only assessment used by both the preview and the generator.

	Returns ``(dcs_doc, header, items, block_reason_or_None, missing_costs)``.
	Enforces read permission on the DCS.
	"""
	frappe.has_permission("Deal Cost Sheet", "read", source_name, throw=True)
	dcs = frappe.get_doc("Deal Cost Sheet", source_name)

	header, items, resources, charges = _dcs_as_dict(dcs.as_dict())

	block_reason = narrative.approval_gate_block_reason(header)

	dcs_addtional_item = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
	missing = narrative.detect_missing_costs(
		items, resources, charges, dcs_addtional_item_configured=bool(dcs_addtional_item)
	)
	return dcs, header, items, block_reason, missing


@frappe.whitelist()
def preview_dcs_readiness(source_name):
	"""Read-only. Report whether a DCS is ready for AI quotation generation:
	the approval/gate block (if any), the missing-cost flags, and whether the
	current user could override. Creates nothing."""
	_dcs, _header, _items, block_reason, missing = _readiness(source_name)
	return {
		"ok": not block_reason and not missing,
		"block_reason": block_reason,
		"missing_costs": missing,
		"can_override": _can_override(),
	}


@frappe.whitelist()
def generate_quotation_from_dcs(
	source_name,
	instructions=None,
	overwrite_narrative=0,
	ignore_missing_costs=0,
):
	"""Create a **draft** Quotation from a Deal Cost Sheet, with AI-written
	narrative applied on top of the deterministic figures.

	Args:
		source_name: Deal Cost Sheet name.
		instructions: optional free-text steer for the narrative (no figures).
		overwrite_narrative: if truthy, replace existing subject/scope/notes/line
			descriptions; otherwise only blank fields are filled.
		ignore_missing_costs: if truthy AND the caller holds an override role,
			proceed despite flagged missing costs (they are still reported).

	Returns a result dict; on a hard block, ``ok`` is 0 and ``quotation`` is None.
	"""
	overwrite_narrative = frappe.utils.cint(overwrite_narrative)
	ignore_missing_costs = frappe.utils.cint(ignore_missing_costs)

	# --- permissions: read the DCS, create (and later write) a Quotation ------
	frappe.has_permission("Quotation", "create", throw=True)
	dcs, header, items, block_reason, missing = _readiness(source_name)

	# --- approval / margin-gate guard ----------------------------------------
	if block_reason and not _can_override():
		return _blocked("approval_gate", block_reason, missing_costs=missing)

	# --- missing-cost guard: flag, never invent ------------------------------
	if missing and not (ignore_missing_costs and _can_override()):
		return _blocked(
			"missing_costs",
			_("This deal cost sheet has missing or zero costs. Fill them in, or ask a Sales Manager to override."),
			missing_costs=missing,
		)

	# --- deterministic draft (all figures come from the ERP, not the model) --
	from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation as build_quotation_draft

	quotation_name = build_quotation_draft(source_name)
	quotation = frappe.get_doc("Quotation", quotation_name)
	frappe.has_permission("Quotation", "write", doc=quotation, throw=True)

	result = {
		"ok": 1,
		"quotation": quotation_name,
		"docstatus": quotation.docstatus,
		"block_reason": block_reason if block_reason else None,  # recorded when overridden
		"missing_costs": missing,
		"ai_used": False,
		"ai_error": None,
		"model": None,
		"fields_updated": [],
		"item_lines_updated": [],
		"needs_input": [],
	}

	# --- AI narrative enrichment (best-effort; never fabricates) --------------
	try:
		from bsgroup.ai import anthropic_client

		config = anthropic_client.get_active_config()
		context = narrative.build_ai_context(header, items)
		system_prompt, user_message = narrative.build_prompt(context, instructions)
		ai = anthropic_client.generate(system_prompt, user_message, config=config)
		parsed = narrative.parse_ai_response(ai["text"])

		field_updates, item_updates, needs_input = narrative.select_narrative_updates(
			parsed, existing=quotation.as_dict(), items=items, overwrite=bool(overwrite_narrative)
		)

		for field, value in field_updates.items():
			quotation.set(field, value)
		applied_lines = _apply_item_descriptions(quotation, items, item_updates, overwrite=bool(overwrite_narrative))

		result.update({
			"ai_used": True,
			"model": ai.get("model"),
			"fields_updated": sorted(field_updates.keys()),
			"item_lines_updated": applied_lines,
			"needs_input": needs_input,
		})
	except Exception as exc:
		# AI is an enhancement, not a gate. The deterministic draft already
		# exists; record why enrichment did not run and carry on. If the
		# provider is simply disabled this is expected, not an error.
		result["ai_error"] = str(exc)[:300]
		frappe.clear_last_message()

	# --- save the draft and leave an audit trail -----------------------------
	quotation.save(ignore_permissions=True)
	_audit(quotation, result)

	return result


def _apply_item_descriptions(quotation, dcs_items, item_updates, overwrite):
	"""Map context line numbers (over all DCS items) to the quotation's item
	rows and write descriptions onto matching rows only.

	``make_quotation`` appends one quotation row per DCS item that has an
	``item_code``, in order, plus possibly a trailing additional-charges row.
	We walk both in order so a line description can never land on the wrong
	product, and we verify the item_code matches before writing.
	"""
	if not item_updates:
		return []

	# Build: dcs line number -> quotation row (only for item_code rows).
	line_to_row = {}
	q_rows = list(quotation.items or [])
	qi = 0
	for line, dcs_row in enumerate(dcs_items or [], start=1):
		if not dcs_row.get("item_code"):
			continue
		# find the next quotation row with the same item_code
		while qi < len(q_rows) and q_rows[qi].get("item_code") != dcs_row.get("item_code"):
			qi += 1
		if qi < len(q_rows):
			line_to_row[line] = q_rows[qi]
			qi += 1

	applied = []
	for upd in item_updates:
		row = line_to_row.get(upd["line"])
		if not row:
			continue
		if not overwrite and (row.description or "").strip():
			continue
		row.description = upd["text"]
		applied.append(upd["line"])
	return applied


def _audit(quotation, result):
	"""Record what the AI step did on the Quotation's timeline. No secrets."""
	try:
		lines = [
			f"AI quotation assist ({'enrichment applied' if result['ai_used'] else 'deterministic only'})",
			f"Model: {result.get('model') or 'n/a'}",
			f"Fields updated: {', '.join(result['fields_updated']) or 'none'}",
			f"Item lines updated: {', '.join(map(str, result['item_lines_updated'])) or 'none'}",
		]
		if result.get("block_reason"):
			lines.append(f"Approval/gate override in effect: {result['block_reason']}")
		if result.get("missing_costs"):
			lines.append(f"Missing-cost flags at generation: {len(result['missing_costs'])}")
		if result.get("needs_input"):
			lines.append("Needs input: " + "; ".join(result["needs_input"]))
		if result.get("ai_error"):
			lines.append(f"AI enrichment skipped: {result['ai_error']}")
		quotation.add_comment("Info", "\n".join(lines))
	except Exception:
		frappe.clear_last_message()


def _blocked(kind, message, missing_costs=None):
	return {
		"ok": 0,
		"blocked": kind,
		"message": message,
		"quotation": None,
		"missing_costs": missing_costs or [],
		"can_override": _can_override(),
	}
