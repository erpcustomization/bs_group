# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Server-side, AI-assisted DCS -> Quotation draft generation.

What this does and, just as importantly, what it does not:

* It builds the Quotation from the Deal Cost Sheet **atomically** - the items,
  company-specific taxes and the AI narrative are all assembled in memory and
  written with a single ``insert``. There is no mid-flow commit, so a failure
  at any point leaves no half-built draft behind.
* Every figure - rates, quantities, amounts, taxes, company currency,
  additional charges - is computed here from the DCS exactly as the existing
  ``Deal Cost Sheet.make_quotation`` does. The model never supplies a number.
* Claude is asked only for *narrative* (subject, scope overview, customer notes,
  per-line customer descriptions). Its output is applied only to those
  descriptive fields, after ``[NEEDS INPUT]`` markers are stripped and reported.
* Missing/zero costs and an unresolved company tax template are flagged, never
  invented or guessed.
* Existing permissions, the DCS margin gate and the commercial approval state
  are enforced before anything is created.
* The result is always a **draft** Quotation (docstatus 0).

Public whitelisted endpoints:
* ``preview_dcs_readiness(source_name)`` - read-only; reports blockers.
* ``generate_quotation_from_dcs(source_name, ...)`` - creates the draft.
"""

import frappe
from frappe import _
from frappe.utils import flt

from bsgroup.ai import narrative

# Roles allowed to override the approval / margin-gate block and to proceed
# despite flagged missing costs. Deliberately narrow. Every override is audited.
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
			"exclude_item_name_and_brand": r.get("exclude_item_name_and_brand"),
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
		"custom_approval_state": dcs.get("custom_approval_state"),
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
	the approval/gate block (if any), the missing-cost flags, the company tax
	template status, and whether the current user could override. Creates
	nothing."""
	dcs, header, _items, block_reason, missing = _readiness(source_name)
	_template, tax_warning = _resolve_company_tax_template(dcs.company)
	return {
		"ok": not block_reason and not missing,
		"block_reason": block_reason,
		"missing_costs": missing,
		"tax_warning": tax_warning,
		"can_override": _can_override(),
	}


@frappe.whitelist()
def generate_quotation_from_dcs(
	source_name,
	instructions=None,
	overwrite_narrative=0,
	ignore_missing_costs=0,
):
	"""Create a **draft** Quotation from a Deal Cost Sheet, atomically, with
	AI-written narrative applied on top of the deterministic figures.

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

	# --- approval / margin-gate guard (preserve commercial approvals) --------
	if block_reason and not _can_override():
		return _blocked("approval_gate", block_reason, missing_costs=missing)

	# --- missing-cost guard: flag, never invent ------------------------------
	if missing and not (ignore_missing_costs and _can_override()):
		return _blocked(
			"missing_costs",
			_("This deal cost sheet has missing or zero costs. Fill them in, or ask a Sales Manager to override."),
			missing_costs=missing,
		)

	# --- build the draft in memory (all figures + company taxes) -------------
	quotation, tax_warnings = _build_quotation_doc(dcs)

	result = {
		"ok": 1,
		"quotation": None,
		"docstatus": 0,
		"block_reason": block_reason or None,  # recorded when overridden
		"missing_costs": missing,
		"tax_warnings": tax_warnings,
		"ai_used": False,
		"ai_error": None,
		"model": None,
		"fields_updated": [],
		"item_lines_updated": [],
		"needs_input": list(tax_warnings),
	}

	# --- AI narrative enrichment (best-effort; never fabricates) --------------
	# Runs entirely against the in-memory doc, before the single insert, so a
	# failure here can never create a partial draft.
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
			"needs_input": list(tax_warnings) + needs_input,
		})
	except Exception as exc:
		# AI is an enhancement, not a gate. Surface a sanitised reason and carry
		# on with the deterministic draft. anthropic_client already raises safe,
		# generic AIProviderError messages; anything else is logged server-side
		# and reported generically here.
		from bsgroup.ai.anthropic_client import AIProviderError

		if isinstance(exc, AIProviderError):
			result["ai_error"] = str(exc)
		else:
			frappe.log_error(title="BSG-AI-QUOTATION enrichment failed", message=frappe.get_traceback())
			result["ai_error"] = _("AI enrichment could not run (internal error).")
		frappe.clear_last_message()

	# --- single atomic insert + audit ----------------------------------------
	frappe.has_permission("Quotation", "create", throw=True)
	frappe.db.savepoint("bsg_ai_quotation")
	try:
		quotation.insert(ignore_permissions=True, ignore_mandatory=True)
	except Exception:
		frappe.db.rollback(save_point="bsg_ai_quotation")
		frappe.log_error(title="BSG-AI-QUOTATION insert failed", message=frappe.get_traceback())
		frappe.clear_last_message()
		return _blocked("insert_failed", _("The draft quotation could not be created. Nothing was saved."), missing_costs=missing)

	result["quotation"] = quotation.name
	result["docstatus"] = quotation.docstatus
	_audit(quotation, result)
	return result


def _resolve_company_tax_template(company):
	"""Resolve the sales-tax template for a company without hardcoding a
	country. Returns ``(template_name_or_None, warning_or_None)``.

	Order: the company's default template, else its only template. If a company
	has no template, or more than one and none marked default, we return no
	template and a warning - taxes are left for a human rather than guessed, so
	this is correct for both the AE and OM companies.
	"""
	if not company:
		return None, "No company on the deal cost sheet; taxes not applied."

	default_template = frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": company, "is_default": 1}, "name"
	)
	if default_template:
		return default_template, None

	templates = frappe.get_all(
		"Sales Taxes and Charges Template", filters={"company": company}, pluck="name"
	)
	if len(templates) == 1:
		return templates[0], None
	if not templates:
		return None, f"No sales-tax template exists for company '{company}'; set taxes on the draft manually."
	return None, f"Company '{company}' has multiple sales-tax templates and no default; set taxes on the draft manually."


def _build_quotation_doc(dcs):
	"""Build (but do not insert) a Quotation from the DCS.

	Mirrors ``bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet.make_quotation``
	figure-for-figure, with two deliberate differences that fix reviewed
	blockers: the tax template is resolved per company (not hardcoded to UAE
	VAT), and nothing is committed here (the caller inserts once, atomically).

	Returns ``(quotation_doc, tax_warnings)``.
	"""
	opp = frappe.db.get_value(
		"Opportunity",
		dcs.opportunity,
		["opportunity_from", "party_name", "custom_contact_person_name", "custom_organization_name"],
		as_dict=True,
	) or {}

	company_currency = frappe.db.get_value("Company", dcs.company, "default_currency") if dcs.company else None

	quotation = frappe.new_doc("Quotation")
	quotation.ignore_pricing_rule = 1
	quotation.opportunity = dcs.opportunity
	quotation.company = dcs.company
	if company_currency:
		quotation.currency = company_currency

	tax_warnings = []
	if dcs.company:
		tax_template, warning = _resolve_company_tax_template(dcs.company)
		if warning:
			tax_warnings.append(warning)
		if tax_template:
			quotation.taxes_and_charges = tax_template
			for tax in frappe.get_all(
				"Sales Taxes and Charges",
				filters={"parent": tax_template},
				fields=["charge_type", "account_head", "description", "rate", "included_in_print_rate"],
				order_by="idx",
			):
				quotation.append("taxes", tax)

	quotation.quotation_to = "Customer" if opp.get("opportunity_from") == "Customer" else "Lead"
	quotation.party_name = opp.get("party_name")
	quotation.custom_contact_person_name = opp.get("custom_contact_person_name") or opp.get("party_name")
	quotation.custom_organization_name = opp.get("custom_organization_name") or ""
	quotation.custom_subject = dcs.subject
	quotation.custom_customer_notes = dcs.customer_notes
	quotation.custom_scope_overview = dcs.scope_overview

	for row in dcs.items or []:
		if not row.item_code:
			continue
		item = frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom", "description"], as_dict=True) or {}
		if row.description:
			description = row.description
		elif row.exclude_item_name_and_brand:
			description = row.item_name or item.get("item_name") or row.item_code
		else:
			parts = [p for p in [row.brand, row.item_code, row.item_name or item.get("item_name")] if p]
			description = " - ".join(parts) if parts else row.item_code

		selling_rate = flt(row.selling_rate)
		qty = flt(row.qty)
		quotation.append("items", {
			"item_code": row.item_code,
			"item_name": row.item_name or item.get("item_name") or row.item_code,
			"brand": row.brand,
			"custom_exclude_item_name_and_brand": row.exclude_item_name_and_brand,
			"uom": item.get("stock_uom"),
			"stock_uom": item.get("stock_uom"),
			"description": description,
			"custom_header": row.header,
			"qty": qty,
			"custom_cost_rate": flt(row.cost_rate),
			"custom_selling_rate": selling_rate,
			"price_list_rate": selling_rate,
			"discount_percentage": 0,
			"rate": selling_rate,
			"amount": qty * selling_rate,
		})

	additional_charges_total = sum(flt(c.amount) for c in dcs.addtional_charges or [])
	if additional_charges_total:
		dcs_addtional_item = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
		# Readiness has already flagged an unconfigured item as a missing cost;
		# if we are here it is configured (or an override was granted).
		if dcs_addtional_item:
			item = frappe.db.get_value("Item", dcs_addtional_item, ["item_name", "stock_uom"], as_dict=True) or {}
			quotation.append("items", {
				"item_code": dcs_addtional_item,
				"item_name": item.get("item_name") or dcs_addtional_item,
				"uom": item.get("stock_uom"),
				"stock_uom": item.get("stock_uom"),
				"description": item.get("item_name") or dcs_addtional_item,
				"qty": 1,
				"price_list_rate": additional_charges_total,
				"discount_percentage": 0,
				"rate": additional_charges_total,
				"amount": additional_charges_total,
			})
		else:
			tax_warnings.append("Additional charges present but 'DCS Addtional Item' is not configured; they were not transferred.")

	return quotation, tax_warnings


def _apply_item_descriptions(quotation, dcs_items, item_updates, overwrite):
	"""Map context line numbers (over all DCS items) to the quotation's item
	rows and write descriptions onto matching rows only.

	Quotation rows are built one per DCS item that has an ``item_code``, in
	order, plus possibly a trailing additional-charges row. We walk both in
	order so a line description can never land on the wrong product, and we
	verify the item_code matches before writing.
	"""
	if not item_updates:
		return []

	line_to_row = {}
	q_rows = list(quotation.items or [])
	qi = 0
	for line, dcs_row in enumerate(dcs_items or [], start=1):
		if not dcs_row.get("item_code"):
			continue
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
			lines.append(f"AI enrichment note: {result['ai_error']}")
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
