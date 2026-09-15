# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Server-side, AI-assisted DCS -> Quotation draft generation.

Guarantees:

* **No automatic bypass.** A blocked margin gate, an in-progress approval,
  missing costs, or an unresolved company tax template all stop generation.
  A privileged user (System Manager / Sales Manager) can proceed only by
  passing the matching explicit override flag - holding the role is never
  enough on its own - and every override is written to the Quotation timeline.
* **Submitted DCS only.** A draft or cancelled Deal Cost Sheet is refused; this
  is never overridable.
* **Permissions and mandatory fields enforced.** The Quotation is inserted with
  permission checks and mandatory-field validation on (no ``ignore_permissions``
  / ``ignore_mandatory``); a validation or permission failure rolls back with no
  orphan draft.
* **Every figure is the ERP's.** Rates, quantities, amounts, taxes and each
  additional charge are computed from the DCS. The model only writes narrative.
* **All additional charges preserved.** Each additional-charge row becomes its
  own quotation line (description + amount), not one collapsed total.
* **Atomic.** Items, taxes and narrative are assembled in memory and written in
  a single insert inside a savepoint.
* **Draft only** (docstatus 0). Nothing is submitted or sent.

Public whitelisted endpoints:
* ``preview_dcs_readiness(source_name)`` - read-only; reports every blocker.
* ``generate_quotation_from_dcs(source_name, ...)`` - creates the draft.
"""

import frappe
from frappe import _
from frappe.utils import flt

from bsgroup.ai import narrative

# Roles that MAY override a block - but only when the caller also passes the
# matching explicit override flag. The role alone never bypasses anything.
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
	"""Shared read-only assessment. Enforces DCS read permission and returns a
	dict of every blocker so the preview and the generator agree."""
	frappe.has_permission("Deal Cost Sheet", "read", source_name, throw=True)
	dcs = frappe.get_doc("Deal Cost Sheet", source_name)

	header, items, resources, charges = _dcs_as_dict(dcs.as_dict())

	# Submitted-DCS status validation (never overridable).
	status_block = None
	if dcs.docstatus == 0:
		status_block = "The deal cost sheet is still a draft. Submit it before quoting."
	elif dcs.docstatus == 2:
		status_block = "The deal cost sheet is cancelled and cannot be quoted."

	approval_block = narrative.approval_gate_block_reason(header)

	dcs_addtional_item = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
	missing = narrative.detect_missing_costs(
		items, resources, charges, dcs_addtional_item_configured=bool(dcs_addtional_item)
	)

	tax_template, tax_warning = _resolve_company_tax_template(dcs.company)

	return {
		"dcs": dcs,
		"header": header,
		"items": items,
		"status_block": status_block,
		"approval_block": approval_block,
		"missing": missing,
		"tax_template": tax_template,
		"tax_block": tax_warning,  # None when a template resolved cleanly
	}


@frappe.whitelist()
def preview_dcs_readiness(source_name):
	"""Read-only. Report every blocker (status, approval, missing costs, taxes)
	and whether the current user could override the overridable ones. Creates
	nothing."""
	rd = _readiness(source_name)
	overridable_blocked = bool(rd["approval_block"] or rd["missing"] or rd["tax_block"])
	return {
		"ok": not (rd["status_block"] or overridable_blocked),
		"status_block": rd["status_block"],
		"block_reason": rd["approval_block"],
		"missing_costs": rd["missing"],
		"tax_block": rd["tax_block"],
		"can_override": _can_override(),
	}


@frappe.whitelist()
def generate_quotation_from_dcs(
	source_name,
	instructions=None,
	overwrite_narrative=0,
	override_approval=0,
	ignore_missing_costs=0,
	override_tax=0,
):
	"""Create a **draft** Quotation from a submitted Deal Cost Sheet.

	Overrides (``override_approval`` / ``ignore_missing_costs`` / ``override_tax``)
	are honoured only when the caller both passes the flag and holds an override
	role; each applied override is audited. A draft/cancelled DCS is always
	refused.
	"""
	overwrite_narrative = frappe.utils.cint(overwrite_narrative)
	override_approval = frappe.utils.cint(override_approval)
	ignore_missing_costs = frappe.utils.cint(ignore_missing_costs)
	override_tax = frappe.utils.cint(override_tax)
	can_override = _can_override()

	# --- permissions: read the DCS, create the Quotation ---------------------
	frappe.has_permission("Quotation", "create", throw=True)
	rd = _readiness(source_name)

	# --- submitted-DCS status (never overridable) ----------------------------
	if rd["status_block"]:
		return _blocked("dcs_status", rd["status_block"])

	# --- approval / margin-gate guard (explicit override only) ---------------
	if rd["approval_block"] and not (override_approval and can_override):
		return _blocked("approval_gate", rd["approval_block"], missing_costs=rd["missing"])

	# --- missing-cost guard (explicit override only) -------------------------
	if rd["missing"] and not (ignore_missing_costs and can_override):
		return _blocked(
			"missing_costs",
			_("This deal cost sheet has missing or zero costs. Fill them in, or a Sales Manager may override."),
			missing_costs=rd["missing"],
		)

	# --- tax validation (explicit override only) -----------------------------
	if rd["tax_block"] and not (override_tax and can_override):
		return _blocked("tax_unresolved", rd["tax_block"])

	applied_overrides = []
	if rd["approval_block"] and override_approval and can_override:
		applied_overrides.append(f"approval: {rd['approval_block']}")
	if rd["missing"] and ignore_missing_costs and can_override:
		applied_overrides.append(f"missing costs: {len(rd['missing'])} flag(s)")
	if rd["tax_block"] and override_tax and can_override:
		applied_overrides.append(f"tax: {rd['tax_block']}")

	# --- build the draft in memory (figures + company taxes + all charges) ---
	quotation, build_warnings = _build_quotation_doc(rd["dcs"], rd["tax_template"])

	result = {
		"ok": 1,
		"quotation": None,
		"docstatus": 0,
		"applied_overrides": applied_overrides,
		"missing_costs": rd["missing"],
		"warnings": build_warnings,
		"ai_used": False,
		"ai_error": None,
		"model": None,
		"fields_updated": [],
		"item_lines_updated": [],
		"needs_input": list(build_warnings),
	}

	# --- AI narrative enrichment (best-effort; never fabricates) --------------
	try:
		from bsgroup.ai import anthropic_client

		config = anthropic_client.get_active_config()
		context = narrative.build_ai_context(rd["header"], rd["items"])
		system_prompt, user_message = narrative.build_prompt(context, instructions)
		ai = anthropic_client.generate(system_prompt, user_message, config=config)
		parsed = narrative.parse_ai_response(ai["text"])

		field_updates, item_updates, needs_input = narrative.select_narrative_updates(
			parsed, existing=quotation.as_dict(), items=rd["items"], overwrite=bool(overwrite_narrative)
		)
		for field, value in field_updates.items():
			quotation.set(field, value)
		applied_lines = _apply_item_descriptions(quotation, rd["items"], item_updates, overwrite=bool(overwrite_narrative))

		result.update({
			"ai_used": True,
			"model": ai.get("model"),
			"fields_updated": sorted(field_updates.keys()),
			"item_lines_updated": applied_lines,
			"needs_input": list(build_warnings) + needs_input,
		})
	except Exception as exc:
		# AI is an enhancement, not a gate. Report a sanitised reason; log only
		# the exception TYPE server-side (never the prompt, customer data, config
		# or key - a full traceback could carry locals in developer mode).
		from bsgroup.ai.anthropic_client import AIProviderError

		if isinstance(exc, AIProviderError):
			result["ai_error"] = str(exc)
		else:
			frappe.log_error(title="BSG-AI-QUOTATION enrichment failed", message=type(exc).__name__)
			result["ai_error"] = _("AI enrichment could not run (internal error).")
		frappe.clear_last_message()

	# --- single atomic insert (permissions + mandatory enforced) -------------
	frappe.db.savepoint("bsg_ai_quotation")
	try:
		quotation.insert()
	except Exception as exc:
		frappe.db.rollback(save_point="bsg_ai_quotation")
		# Validation/permission messages are safe to surface and log; no
		# traceback (which could carry commercial data as locals).
		frappe.log_error(title="BSG-AI-QUOTATION insert failed", message=f"{type(exc).__name__}: {str(exc)[:200]}")
		frappe.clear_last_message()
		return _blocked("insert_failed", _("The draft quotation could not be created: {0}").format(str(exc)[:200]))

	result["quotation"] = quotation.name
	result["docstatus"] = quotation.docstatus
	_audit(quotation, result)
	return result


def _resolve_company_tax_template(company):
	"""Resolve the sales-tax template for a company without hardcoding a
	country. Returns ``(template_name_or_None, warning_or_None)``.

	Order: the company's default template, else its only template. No template,
	or several with none default -> return none and a warning, so taxes are
	validated by a human rather than guessed. Correct for both the AE and OM
	companies.
	"""
	if not company:
		return None, "No company on the deal cost sheet; taxes cannot be applied."

	default_template = frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": company, "is_default": 1}, "name"
	)
	if default_template:
		return default_template, None

	templates = frappe.get_all("Sales Taxes and Charges Template", filters={"company": company}, pluck="name")
	if len(templates) == 1:
		return templates[0], None
	if not templates:
		return None, f"No sales-tax template exists for company '{company}'; set taxes on the draft manually."
	return None, f"Company '{company}' has multiple sales-tax templates and no default; choose the tax template manually."


def _build_quotation_doc(dcs, tax_template):
	"""Build (but do not insert) a Quotation from the DCS.

	Figure-for-figure with the existing
	``deal_cost_sheet.make_quotation``, with three deliberate differences that
	address reviewed blockers: the tax template is resolved per company (passed
	in), each additional charge is preserved as its own line rather than
	collapsed into one total, and nothing is committed here.

	Returns ``(quotation_doc, warnings)``.
	"""
	warnings = []
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

	# Additional charges: preserve EVERY charge as its own line (description +
	# amount), not one summed total, so nothing is lost on the quotation.
	charges = [c for c in (dcs.addtional_charges or []) if flt(c.amount)]
	if charges:
		dcs_addtional_item = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
		if dcs_addtional_item:
			ai = frappe.db.get_value("Item", dcs_addtional_item, ["item_name", "stock_uom"], as_dict=True) or {}
			for c in charges:
				amt = flt(c.amount)
				quotation.append("items", {
					"item_code": dcs_addtional_item,
					"item_name": ai.get("item_name") or dcs_addtional_item,
					"uom": ai.get("stock_uom"),
					"stock_uom": ai.get("stock_uom"),
					"description": (c.description or "").strip() or ai.get("item_name") or dcs_addtional_item,
					"qty": 1,
					"price_list_rate": amt,
					"discount_percentage": 0,
					"rate": amt,
					"amount": amt,
				})
		else:
			# Readiness flags this as a missing cost and blocks by default; if an
			# override brought us here, do not silently drop the charges.
			warnings.append("Additional charges present but 'DCS Addtional Item' is not configured; they were NOT transferred.")

	return quotation, warnings


def _apply_item_descriptions(quotation, dcs_items, item_updates, overwrite):
	"""Map context line numbers (over all DCS items) to the quotation's product
	rows and write descriptions onto matching rows only, walking both in order
	and verifying item_code so a description never lands on the wrong product."""
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
		if result.get("applied_overrides"):
			lines.append("Overrides applied: " + "; ".join(result["applied_overrides"]))
		if result.get("warnings"):
			lines.append("Warnings: " + "; ".join(result["warnings"]))
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
