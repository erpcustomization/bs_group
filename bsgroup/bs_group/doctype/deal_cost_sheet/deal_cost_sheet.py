# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
import json
import re
from frappe.model.document import Document


class DealCostSheet(Document):
	def autoname(self):
		if self.customer:
			customer = re.sub(r'[^a-zA-Z0-9\s]', '', self.customer)
			customer = re.sub(r'\s+', '-', customer.strip())

			self.name = frappe.model.naming.make_autoname(f"DCS-{customer}-.###")

	def before_insert(self):
		dcs_company_default_insert(self)
		dcs_one_active_guard_insert(self)

	def before_save(self):
		calculate_deal_financials(self)
		dcs_governed_field_guard(self)
		dcs_record_authority_guard(self)

	def before_submit(self):
		validate_deal_cost(self)
		dcs_one_active_guard_submit(self)
		dcs_submit_advance_presales_status(self)

	def on_update(self):
		dcs_margin_canonicalisation(self)

	def validate(self):
		# if not self.project:
		# 	frappe.throw("Project is mandatory on the Deal Cost Sheet before it can be used as a Project Cost Baseline source.")

		if self.presales_request:
			site_visit_required = frappe.db.get_value(
				"Presales Request", self.presales_request, "site_visit_required"
			)
			if site_visit_required and not self.site_visit:
				frappe.throw(
					"Site Visit is mandatory: the linked Presales Request requires a completed site visit."
				)


@frappe.whitelist()
def make_quotation(source_name):
	source = frappe.get_doc("Deal Cost Sheet", source_name)

	opp = frappe.db.get_value(
		"Opportunity",
		source.opportunity,
		["opportunity_from", "party_name", "custom_contact_person_name", "custom_organization_name"],
		as_dict=True,
	) or {}

	company_currency = frappe.db.get_value("Company", source.company, "default_currency") if source.company else None

	quotation = frappe.new_doc("Quotation")
	quotation.ignore_pricing_rule = 1
	quotation.opportunity = source.opportunity
	quotation.company = source.company
	if company_currency:
		quotation.currency = company_currency

	if source.company:
		vat_template = frappe.db.get_value(
			"Sales Taxes and Charges Template",
			{"company": source.company, "name": ["like", "%UAE VAT 5%%"]},
			"name"
		)
		if vat_template:
			quotation.taxes_and_charges = vat_template
			tax_rows = frappe.get_all(
				"Sales Taxes and Charges",
				filters={"parent": vat_template},
				fields=["charge_type", "account_head", "description", "rate", "included_in_print_rate"],
				order_by="idx"
			)
			for tax in tax_rows:
				quotation.append("taxes", tax)
	quotation.quotation_to = "Customer" if opp.get("opportunity_from") == "Customer" else "Lead"
	quotation.party_name = opp.get("party_name")
	quotation.custom_contact_person_name = opp.get("custom_contact_person_name") or opp.get("party_name")
	quotation.custom_organization_name = opp.get("custom_organization_name") or ""

	quotation.custom_subject = source.subject
	quotation.custom_customer_notes = source.customer_notes
	quotation.custom_scope_overview = source.scope_overview


	for row in source.items or []:
		if row.item_code:
			item = frappe.db.get_value(
				"Item",
				row.item_code,
				["item_name", "stock_uom", "description"],
				as_dict=True
			) or {}

			if row.description:
				description = row.description
			elif row.exclude_item_name_and_brand:
				description = row.item_name or item.get("item_name") or row.item_code
			else:
				parts = [p for p in [row.brand, row.item_code, row.item_name or item.get("item_name")] if p]
				description = " - ".join(parts) if parts else row.item_code

			selling_rate = frappe.utils.flt(row.selling_rate)
			qty = frappe.utils.flt(row.qty)
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
				"custom_cost_rate": frappe.utils.flt(row.cost_rate),
				"custom_selling_rate": selling_rate,
				"price_list_rate": selling_rate,
				"discount_percentage": 0,
				"rate": selling_rate,
				"amount": qty * selling_rate,
			})

	additional_charges_total = sum(frappe.utils.flt(c.amount) for c in source.addtional_charges or [])
	if additional_charges_total:
		dcs_addtional_item = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
		if not dcs_addtional_item:
			frappe.throw("Please configure 'DCS Addtional Item' in BS Group Settings to transfer Additional Charges.")

		item = frappe.db.get_value(
			"Item",
			dcs_addtional_item,
			["item_name", "stock_uom"],
			as_dict=True
		) or {}

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

	quotation.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.commit()
	return quotation.name


def dcs_company_default_insert(doc):
	"""Before Insert: a new Deal Cost Sheet with a blank Company inherits the
	Company of its linked Opportunity, exactly as stored on that Opportunity.

	Reproduced from the live-site "dcs_company_default_insert" Server Script
	(see "# DCS Presales Effort Metrics.txt"). Acts only on insert, only when
	Company is blank, and never overwrites or reconciles an existing value.
	Any failure leaves the document exactly as it arrived.
	"""
	try:
		cur = (doc.get("company") or "").strip()
		if cur:
			return
		opp = doc.get("opportunity")
		if not opp:
			return
		oc = frappe.db.get_value("Opportunity", opp, "company")
		if oc and str(oc).strip():
			doc.company = str(oc).strip()
	except Exception:
		pass


def dcs_margin_canonicalisation(doc):
	"""After Save: single server-side authority for the persisted commercial
	margin percentage.

		gross_profit   = total_selling - total_cost
		margin_percent = gross_profit / total_selling * 100

	Reproduced from the live-site "DCS Margin Canonicalisation" Server Script.
	Persists with update_modified=False so no further save/hook/Version entry
	is triggered. Zero or absent selling yields 0. Precision is 3 decimals.

	NOTE: this differs from the markup-style formula
	((total_selling / total_cost) - 1) * 100 used by calculate_deal_financials()
	above (GP / cost, not GP / selling). This after_save hook intentionally
	overwrites that value with the canonical margin formula on every save, to
	match the live site's behaviour. Flagged for review since it changes the
	stored meaning of margin_percent going forward.
	"""
	sell = frappe.utils.flt(doc.total_selling or 0)
	cost = frappe.utils.flt(doc.total_cost or 0)
	if sell:
		canonical = frappe.utils.flt(((sell - cost) / sell) * 100, 3)
	else:
		canonical = frappe.utils.flt(0)
	if frappe.utils.flt(doc.margin_percent or 0, 3) != canonical:
		frappe.db.set_value("Deal Cost Sheet", doc.name, "margin_percent", canonical, update_modified=False)
		doc.margin_percent = canonical


def _dcs_lineage_root(name, amended_from):
	"""Walk amended_from back to the oldest ancestor, guarding against cycles.

	Cancel -> Amend lineage (a cancelled DCS plus its amended successor) shares
	one lineage root and must count as ONE active DCS, never two.
	"""
	root = name
	cur = amended_from
	seen = set()
	while cur and cur not in seen:
		seen.add(cur)
		root = cur
		cur = frappe.db.get_value("Deal Cost Sheet", cur, "amended_from")
	return root


def dcs_one_active_guard_insert(doc):
	"""Before Insert (ODS-1): at most ONE independently active commercial Deal
	Cost Sheet may exist per Opportunity at any one time.

	Reproduced from the live-site "dcs_one_active_guard_insert" Server Script,
	which was created disabled there ("activation is an owner decision").
	Mirrored here behind BS Group Settings.enable_dcs_one_active_guard, which
	defaults to unchecked so behaviour is unchanged until an owner opts in.

	Fires only on insert of a brand new document, so it can never make a
	pre-existing record fail to save, and never cancels/amends/merges/renames/
	relinks/deletes anything. No role bypasses this control.
	"""
	if not frappe.db.get_single_value("BS Group Settings", "enable_dcs_one_active_guard"):
		return

	opp = doc.opportunity
	if not opp:
		return

	frappe.db.get_value("Opportunity", opp, "name", for_update=True)

	my_root = _dcs_lineage_root("(new-lineage)", doc.amended_from)

	siblings = frappe.get_all(
		"Deal Cost Sheet",
		filters={"opportunity": opp, "docstatus": ["<", 2]},
		fields=["name", "amended_from"],
	)

	blockers = [
		s.name for s in siblings
		if _dcs_lineage_root(s.name, s.amended_from) != my_root
	]

	if blockers:
		frappe.throw(
			"Opportunity {0} already has an active Deal Cost Sheet: {1}. "
			"Only one independently active Deal Cost Sheet is permitted per Opportunity. "
			"To change the commercial position, raise a DCS Revision on the existing sheet, "
			"or cancel it and use Amend to create its successor.".format(opp, ", ".join(blockers)),
			title="Duplicate Deal Cost Sheet",
		)


def dcs_one_active_guard_submit(doc):
	"""Before Submit (ODS-1): companion to dcs_one_active_guard_insert.

	Prevents a draft that predates the control from being promoted into a
	second independently active commercial position. Only already-submitted
	independent siblings block; drafts never block a submit.
	"""
	if not frappe.db.get_single_value("BS Group Settings", "enable_dcs_one_active_guard"):
		return

	opp = doc.opportunity
	if not opp:
		return

	frappe.db.get_value("Opportunity", opp, "name", for_update=True)

	my_root = _dcs_lineage_root(doc.name, doc.amended_from)

	siblings = frappe.get_all(
		"Deal Cost Sheet",
		filters={"opportunity": opp, "docstatus": 1, "name": ["!=", doc.name]},
		fields=["name", "amended_from"],
	)

	blockers = [
		s.name for s in siblings
		if _dcs_lineage_root(s.name, s.amended_from) != my_root
	]

	if blockers:
		frappe.throw(
			"Opportunity {0} already has a submitted, active Deal Cost Sheet: {1}. "
			"Submitting this sheet would create a second independently active commercial position. "
			"Cancel the superseded sheet first, or raise a DCS Revision on it instead.".format(
				opp, ", ".join(blockers)
			),
			title="Duplicate Deal Cost Sheet",
		)


GOVERNED_TEXT = ["custom_approval_state", "custom_approval_required", "custom_approval_reason", "custom_margin_gate", "custom_margin_gate_reason", "custom_award_state", "custom_award_reference", "custom_award_evidence_type", "custom_awarded_by", "custom_awarded_on", "custom_approved_by", "custom_approved_on", "custom_endorsed_by", "custom_endorsed_on", "custom_last_decision_reason", "custom_po_reference", "custom_po_payment_terms", "custom_award_notes", "custom_po_scope_revision", "custom_po_value_match", "custom_po_scope_match", "custom_po_terms_match", "custom_po_recon_state", "custom_po_recon_by", "custom_po_recon_on", "custom_delivery_release_state", "custom_delivery_owner", "custom_delivery_released_by", "custom_delivery_released_on", "custom_delivery_release_note", "custom_delivery_override_reason", "custom_frozen_by", "custom_frozen_on", "custom_revision_reference", "custom_award_reversal_state", "custom_award_reversal_ref", "custom_award_reversed_by", "custom_award_reversed_on", "custom_award_reversal_reason", "custom_operational_review_state"]
GOVERNED_NUM = ["custom_dcs_revision_no", "custom_working_total_cost", "custom_working_total_selling", "custom_working_margin_percent", "custom_baseline_selling", "custom_concession_percent_from_baseline", "custom_approved_revision_no", "custom_approved_total_cost", "custom_approved_total_selling", "custom_approved_margin_percent", "custom_baseline_frozen", "custom_frozen_revision_no", "custom_frozen_total_cost", "custom_frozen_total_selling", "custom_frozen_margin_percent", "custom_po_value", "custom_delivery_override", "custom_handover_condition_no", "custom_award_reversal_count", "custom_award_sequence_no"]


def _dcs_absf(v):
	if v < 0:
		return 0 - v
	return v


def nrc_narrative_verdict(txt):
	"""NRC-1 narrative guard, protected-field-name channel only.

	Reproduced from the live-site "dcs_narrative_guard" logic's first half
	(see "# DCS Presales Effort Metrics.txt" section 101-167). The second
	half of the live logic delegates to a "dcs_narrative_guard" classifier
	Server Script endpoint (contract NRC-1, mode=inspect) whose scoring rules
	for free-text commercial-figure leakage are NEVER given anywhere in the
	source file. That half is intentionally NOT implemented here pending the
	real NRC-1 classifier rules -- do not invent them. As a result this guard
	only catches the protected-field-name channel; it does not catch narrative
	text that leaks commercial figures without naming a protected field.
	"""
	scope = ["Deal Cost Sheet", "Deal Cost Item", "DCS Handover Condition"]
	pre_existing = ["products_selling_total", "services_selling_total", "total_selling", "selling_rate", "selling_amount"]
	verdict = {"reject": 0, "why": "", "level": "clean", "err": ""}
	t = str(txt or "").strip()
	if t == "":
		return verdict

	# (1) protected field-name channel
	low = t.lower()
	names = []
	try:
		for r in frappe.get_all("Custom Field", filters={"dt": ["in", scope], "permlevel": [">", 0]}, fields=["fieldname"], limit_page_length=0):
			names.append(str(r.get("fieldname") or "").lower())
		for r in frappe.get_all("Property Setter", filters={"doc_type": ["in", scope], "property": "permlevel", "value": ["!=", "0"]}, fields=["field_name"], limit_page_length=0):
			names.append(str(r.get("field_name") or "").lower())
	except Exception as me:
		verdict["err"] = "protected register unavailable: " + str(me)
		return verdict
	for x in pre_existing:
		names.append(x)
	hits = []
	for n in names:
		if len(n) > 6:
			if n in low:
				hits.append(n)
	if len(hits) > 0:
		verdict["reject"] = 1
		verdict["why"] = "protected field names: " + ", ".join(hits[0:4])
		return verdict

	# (2) canonical NRC-1 classifier, delegated -- NOT IMPLEMENTED. See docstring.

	return verdict


def dcs_governed_field_guard(doc):
	"""Before Save: refuse direct edits to the commercial control fields that
	are owned by the DCS workspaces (Negotiation, Approval, Award, Handover),
	plus the NRC-1 protected-field-name channel on custom_closure_notes.

	Reproduced from the live-site "Deal Cost Sheet - Governed Field Guard"
	Server Script. Opt-in via BS Group Settings.enable_dcs_governed_field_guard
	(default unchecked) since this is a real behavioural change: it can block
	edits to fields that may currently be freely editable.
	"""
	if not frappe.db.get_single_value("BS Group Settings", "enable_dcs_governed_field_guard"):
		return

	prev = doc.get_doc_before_save()
	if prev is not None:
		changed = []
		for f in GOVERNED_TEXT:
			a = prev.get(f)
			b = doc.get(f)
			if str(a or "") != str(b or ""):
				changed.append(f)
		for f in GOVERNED_NUM:
			a = frappe.utils.flt(prev.get(f) or 0)
			b = frappe.utils.flt(doc.get(f) or 0)
			if _dcs_absf(a - b) > 0.0001:
				changed.append(f)
		if len(changed) > 0:
			frappe.throw("These Deal Cost Sheet fields are governed by the commercial workspaces and cannot be edited directly: " + "; ".join(changed) + ". Use the Negotiation Workspace, the Approval Workspace or the Award and Handover Workspace. Direct edits are refused so that every commercial movement keeps an audit trail.")

	# NRC-1 narrative enforcement -- evaluated only when the narrative actually changes.
	narr_bad = []
	for nf in ["custom_closure_notes"]:
		newv = doc.get(nf)
		oldv = None
		if prev is not None:
			oldv = prev.get(nf)
		if str(newv or "") != str(oldv or ""):
			v = nrc_narrative_verdict(newv)
			if v.get("err"):
				frappe.throw("The narrative guard (NRC-1) could not be reached, so this note was not saved: " + str(v.get("err")))
			if v.get("reject") == 1:
				narr_bad.append(nf + " -> " + str(v.get("why")))

	if len(narr_bad) > 0:
		frappe.throw("NRC-1 refused this Deal Cost Sheet narrative: " + " | ".join(narr_bad) + ". Commercial figures belong in the governed commercial fields, which are permission-level protected and audited. Describe the outcome in words instead of restating amounts or field names.")


def dcs_record_authority_guard(doc):
	"""Before Save: validates custom_record_authority / custom_superseded_by
	supersession metadata and, on a real change, writes a DCS Governance
	Event audit record.

	Reproduced from the live-site "DCS Record Authority Guard" Server Script
	(present twice, byte-identical, in the source file with no distinguishing
	detail -- implemented once here). Never infers authority; never touches
	financial, lifecycle, award, workflow or docstatus values. Opt-in via
	BS Group Settings.enable_dcs_record_authority_guard (default unchecked),
	as a distinct, independently-activatable control from the Governed Field
	Guard.
	"""
	if not frappe.db.get_single_value("BS Group Settings", "enable_dcs_record_authority_guard"):
		return

	auth = doc.custom_record_authority or ""
	sup = doc.custom_superseded_by or ""

	if not (auth or sup):
		return

	if auth == "Superseded" and not sup:
		frappe.throw("Record Authority Superseded requires a Superseded By record.")
	if auth == "Current" and sup:
		frappe.throw("Record Authority Current must not carry a Superseded By link.")
	if auth == "Undetermined" and sup:
		frappe.throw("Record Authority Undetermined must not carry a Superseded By link.")
	if not auth and sup:
		frappe.throw("Superseded By cannot be set unless Record Authority is Superseded.")
	if sup:
		if sup == doc.name:
			frappe.throw("A Deal Cost Sheet cannot supersede itself.")
		tgt = frappe.db.get_value("Deal Cost Sheet", sup, ["opportunity", "custom_record_authority"], as_dict=True)
		if not tgt:
			frappe.throw("Superseded By target does not exist: " + sup)
		if (tgt.get("opportunity") or "") != (doc.opportunity or ""):
			frappe.throw("Supersession must stay within one Opportunity. Cross-Opportunity links are rejected.")
		if tgt.get("custom_record_authority") == "Superseded":
			frappe.throw("The nominated target is itself Superseded. Point at the authoritative record.")
		seen = [doc.name]
		cur = sup
		for hop in range(25):
			if not cur:
				break
			if cur in seen:
				frappe.throw("Circular supersession chain detected at " + cur)
			seen.append(cur)
			cur = frappe.db.get_value("Deal Cost Sheet", cur, "custom_superseded_by")

	before = doc.get_doc_before_save()
	if before:
		oldauth = before.get("custom_record_authority") or ""
		oldsup = before.get("custom_superseded_by") or ""
		if oldauth != auth or oldsup != sup:
			doc.custom_authority_decided_by = frappe.session.user
			doc.custom_authority_decided_on = frappe.utils.now()
			chg = []
			if oldauth != auth:
				chg.append({"fieldname": "custom_record_authority", "field_label": "Record Authority", "target_doctype": "Deal Cost Sheet", "target_name": doc.name, "old_value": oldauth or "(blank)", "new_value": auth or "(blank)", "value_type": "Select"})
			if oldsup != sup:
				chg.append({"fieldname": "custom_superseded_by", "field_label": "Superseded By", "target_doctype": "Deal Cost Sheet", "target_name": doc.name, "old_value": oldsup or "(none)", "new_value": sup or "(none)", "value_type": "Link"})
			ev = frappe.get_doc({"doctype": "DCS Governance Event", "dcs": doc.name, "event_code": "RECORD_AUTHORITY_SET", "action_label": "Record authority / supersession decision", "source_endpoint": "DCS Record Authority Guard", "actor": frappe.session.user, "event_timestamp": frappe.utils.now(), "outcome": "Success", "correlation_id": "AUTH-" + doc.name, "change_count": len(chg), "reason": doc.custom_supersession_reason or "(no reason recorded)", "changes": json.dumps(chg)})
			ev.flags.dcs_audit_write = 1
			ev.insert(ignore_permissions=True)


def dcs_submit_advance_presales_status(doc):
	"""Before Submit: advance the Deal Cost Sheet's own deal status, and the
	linked Presales Request's status when it is still in an early stage.

	Reproduced from the live-site "DCS Submit - Advance Presales Status"
	Server Script (see "# DCS Presales Effort Metrics.txt" lines 60-91),
	minus its trailing fan-out call to the canonical "dcs_presales_sync"
	endpoint (mode unspecified, "source=submit"), whose projection/mapping
	formula is NEVER given anywhere in the source file. That fan-out is
	intentionally NOT implemented here pending the real dcs_presales_sync
	formula -- do not invent it. The two business-status transitions below
	do not depend on that endpoint and are implemented verbatim.
	"""
	frappe.db.set_value("Deal Cost Sheet", doc.name, "custom_deal_status", "Submitted to Sales", update_modified=False)
	doc.custom_deal_status = "Submitted to Sales"

	if not doc.presales_request:
		return

	cur = frappe.db.get_value("Presales Request", doc.presales_request, "status")
	early = ["Draft", "Open", "Assigned", "In Progress", "Awaiting Sales Input", "Awaiting Customer Input", "Costing in Progress"]
	if cur in early:
		frappe.db.set_value("Presales Request", doc.presales_request, "status", "Submitted to Sales", update_modified=False)
	# Canonical projection synchronisation (dcs_presales_sync fan-out) intentionally
	# omitted -- see docstring above.


def validate_deal_cost(doc):
	if not doc.opportunity:
		frappe.throw("Opportunity is mandatory before submit.")

	if not doc.items:
		frappe.throw("At least one item is required before submit.")

	for d in doc.items:
		if not d.item_code:
			frappe.throw("Item Code is mandatory in all rows.")

	# 	if frappe.utils.flt(d.selling_rate) <= 0:
	# 		frappe.throw(f"Selling Rate is required before submit for item {d.item_code}.")

	# if frappe.utils.flt(doc.total_selling) <= 0:
	# 	frappe.throw("Total Selling must be greater than zero.")

	# if frappe.utils.flt(doc.margin_value) < 0:
	# 	frappe.throw("Margin cannot be negative.")


def calculate_deal_financials(doc):
	products_cost_total = 0
	products_selling_total = 0
	services_cost_total = 0
	services_selling_total = 0

	for d in doc.items or []:
		qty = frappe.utils.flt(d.qty)
		cost_rate = frappe.utils.flt(d.cost_rate)
		selling_rate = frappe.utils.flt(d.selling_rate)

		d.cost_amount = qty * cost_rate
		d.selling_amount = qty * selling_rate
		d.gp_value = d.selling_amount - d.cost_amount
		d.gp_percent = (d.gp_value / d.selling_amount) * 100 if d.selling_amount else 0

		is_stock_item = frappe.db.get_value("Item", d.item_code, "is_stock_item") if d.item_code else 1

		if not is_stock_item:
			d.item_category = "Professional Services"
			services_cost_total += d.cost_amount
			services_selling_total += d.selling_amount
		else:
			d.item_category = "Products"
			products_cost_total += d.cost_amount
			products_selling_total += d.selling_amount

	total_resource_cost = 0
	for r in doc.resources or []:
		persons = frappe.utils.flt(r.no_of_persons)
		days = frappe.utils.flt(r.no_of_days)
		hours = frappe.utils.flt(r.hours)
		rate = frappe.utils.flt(r.cost_rate)

		if persons and days:
			r.cost_amount = persons * days * rate
		elif hours:
			r.cost_amount = hours * rate
		else:
			r.cost_amount = 0

		total_resource_cost += r.cost_amount

	additional_charges_total = 0
	for c in doc.addtional_charges or []:
		additional_charges_total += frappe.utils.flt(c.amount)

	doc.products_cost_total = products_cost_total
	doc.products_selling_total = products_selling_total
	doc.services_cost_total = services_cost_total
	doc.services_selling_total = services_selling_total
	doc.total_resource_cost = total_resource_cost

	doc.total_cost = products_cost_total + services_cost_total + additional_charges_total + total_resource_cost
	doc.total_selling = products_selling_total + services_selling_total
	doc.margin_value = doc.total_selling - doc.total_cost
	doc.margin_percent = ((doc.total_selling / doc.total_cost) - 1) * 100 if doc.total_cost else 0


@frappe.whitelist()
def get_site_visit_evidence(site_visit):
	if not site_visit:
		return {}

	doc = frappe.get_doc("Site Visit", site_visit)

	return {
		"status": doc.status,
		"planned_visit_date": doc.planned_visit_date,
		"site_conditions": doc.site_conditions,
		"technical_observations": doc.technical_observations,
		"requirements_identified": doc.requirements_identified,
		"constraints_issues": doc.constraints_issues,
		"findings": doc.findings,
		"recommendations": doc.recommendations,
		"visit_result": doc.visit_result,
		"measurements": [
			{
				"measurement_type": m.measurement_type,
				"value": m.value,
				"unit": m.unit,
				"remarks": m.remarks,
			}
			for m in doc.measurements or []
		],
		"evidence": [
			{
				"evidence_type": e.evidence_type,
				"description": e.description,
				"attachment": e.attachment,
			}
			for e in doc.evidence or []
		],
	}


@frappe.whitelist()
def read_deal_cost_sheet(file_url, docname):
	import csv
	import os
	import openpyxl
	from frappe.utils.file_manager import get_file_path

	if docname.startswith("new-"):
		frappe.throw("Please save the document before importing.")

	doc = frappe.get_doc("Deal Cost Sheet", docname)
	doc.set("items", [])

	file_name = frappe.db.get_value("File", {"file_url": file_url}, "file_name")
	if not file_name:
		frappe.throw(f"File not found for URL: {file_url}")
	file_path = get_file_path(file_name)

	ext = os.path.splitext(file_path)[1].lower()

	if ext not in (".xlsx", ".csv"):
		frappe.throw("Only .xlsx or .csv files are supported")

	def read_rows():
		if ext == ".csv":
			with open(file_path, newline="", encoding="utf-8-sig") as f:
				reader = csv.reader(f)
				for row in reader:
					yield row
		else:
			wb = openpyxl.load_workbook(file_path, data_only=True)
			sheet = wb.active
			for row in sheet.iter_rows(values_only=True):
				yield list(row)

	column_map = {}

	for row in read_rows():
		if not row:
			continue

		row = [str(c).strip() if c is not None else "" for c in row]

		# Detect header row
		if not column_map:
			column_map = {col: idx for idx, col in enumerate(row)}
			continue

		def get_val(col):
			idx = column_map.get(col)
			return row[idx] if idx is not None and idx < len(row) else ""

		def to_float(col):
			try:
				return float(get_val(col) or 0)
			except (ValueError, TypeError):
				return 0.0

		def to_int(col):
			try:
				return int(float(get_val(col) or 0))
			except (ValueError, TypeError):
				return 0

		child = doc.append("items", {})

		child.header = get_val("Header (Items)")
		child.item_code = get_val("Item Code (Items)")
		child.item_name = get_val("Item Name (Items)")
		child.brand = get_val("Brand (Items)")
		child.customer_item_name = get_val("Customer Item Name (Items)")
		child.exclude_item_name_and_brand = to_int("Exclude Item Name and Brand (Items)")

		child.qty = to_float("Qty (Items)")
		child.cost_rate = to_float("Cost Rate (Items)")
		child.cost_amount = to_float("Cost Amount (Items)")

		child.item_category = get_val("Item Category (Items)")

		child.selling_rate = to_float("Selling Rate (Items)")
		child.selling_amount = to_float("Selling Amount (Items)")

		child.gp_value = to_float("GP Value (Items)")
		child.gp_percent = to_float("GP % (Items)")

	doc.save(ignore_permissions=True)

	return "Success"
	