# ---------------- NRC-1 delegating narrative client ----------------
# The canonical narrative redaction contract lives once, in Server Script
# "dcs_narrative_guard" (NRC-1). This surface never re-implements the rules.
# If the contract is unreachable, answers with a different version, or fails
# the idempotency self-audit, this surface FAILS CLOSED and withholds narrative.
NRC_UNAVAILABLE = "[withheld - governed redaction unavailable]"

def nrc_call(items):
	out = {"ok": 0, "texts": [], "levels": [], "err": ""}
	if not items:
		out["ok"] = 1
		return out
	saved = frappe.response.get("message")
	got = None
	try:
		frappe.call("dcs_narrative_guard", mode="redact_batch", items=items)
		got = frappe.response.get("nrc")
		if not got:
			got = frappe.response.get("message")
	except Exception as ne:
		out["err"] = str(ne)
	frappe.response["nrc"] = None
	frappe.response["message"] = saved
	if got and got.get("ok") == 1 and got.get("contract") == "NRC-1" and len(got.get("texts") or []) == len(items):
		out["ok"] = 1
		out["texts"] = got.get("texts")
		out["levels"] = got.get("levels")
	return out

def nrc_govern(items):
	first = nrc_call(items)
	if first["ok"] != 1:
		return {"ok": 0, "texts": [], "redacted": 0, "reason": "The governed redaction service is unavailable. Operational narrative is withheld."}
	red = 0
	for lv in first["levels"]:
		if lv != "clean":
			red = red + 1
	second = nrc_call(first["texts"])
	if second["ok"] != 1:
		return {"ok": 0, "texts": [], "redacted": 0, "reason": "The governed redaction self-audit could not complete. Operational narrative is withheld."}
	for lv in second["levels"]:
		if lv != "clean":
			return {"ok": 0, "texts": [], "redacted": 0, "reason": "The governed redaction self-audit detected residual commercial signal. Operational narrative is withheld."}
	return {"ok": 1, "texts": first["texts"], "redacted": red, "reason": ""}
# ---------------- end NRC-1 delegating narrative client ----------------

# dcs_screen5 - Award and Handover Workspace. READ ONLY. Writes nothing.
# Customer Award, Commercial Baseline Frozen and Delivery Release are three separate states.
# Technical projection returns ZERO commercial values.

COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]
TECHNICAL_ROLES = ["Technical Engineer", "Project Engineer", "Project Manager", "Operations Manager"]
MD = "Managing Director"
CC = "Commercial Controller"

def get_user_roles(u):
	rows = frappe.get_all("Has Role", filters={"parent": u, "parenttype": "User"}, fields=["role"])
	out = []
	for r in rows:
		out.append(r.get("role"))
	return out

def has_any(roles, wanted):
	for r in wanted:
		if r in roles:
			return 1
	return 0

def absf(v):
	if v < 0:
		return 0 - v
	return v

def next_condition_no(sheet_name):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name}, fields=["condition_no"], order_by="condition_no desc", limit_page_length=1)
	n = 0
	for r in rows:
		n = r.get("condition_no") or 0
	return n + 1

def find_condition(sheet_name, key):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "source_key": key}, fields=["name", "state", "category"], limit_page_length=1)
	for r in rows:
		return r
	return None

def raise_condition(sheet_name, key, title, category, domain, detail):
	existing = find_condition(sheet_name, key)
	if existing is not None:
		if existing.get("state") == "Open":
			return existing.get("name")
		if existing.get("state") == "Accepted Risk":
			return existing.get("name")
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
	c.raised_on = frappe.utils.now_datetime()
	c.auto_generated = 1
	c.source_key = key
	c.insert()
	return c.name

def open_blockers(sheet_name):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "category": "Blocker", "state": "Open"}, fields=["name", "condition_title", "domain"])
	return rows

def r2(v):
	x = (v or 0) * 100.0
	if x < 0:
		return int(x - 0.5) / 100.0
	return int(x + 0.5) / 100.0

result = {"ok": 0, "error": "", "projection": "denied", "user": frappe.session.user}

dcs_name = frappe.form_dict.get("dcs")
want = frappe.form_dict.get("projection")
roles = get_user_roles(frappe.session.user)
is_comm = has_any(roles, COMMERCIAL_ROLES)
is_tech = has_any(roles, TECHNICAL_ROLES)
is_md = 0
is_cc = 0
if MD in roles:
	is_md = 1
if CC in roles:
	is_cc = 1

# a caller may explicitly request the technical projection, which is strictly LESS.
# a caller can never request more than their roles allow.
if want == "technical":
	is_comm = 0

if not dcs_name:
	result["error"] = "dcs is required."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
	result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif is_comm == 0 and is_tech == 0:
	result["error"] = "You hold neither a commercial nor a technical role. System Manager administration does not confer access to the Award and Handover Workspace."
else:
	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("read")
	conds = frappe.get_all("DCS Handover Condition", filters={"dcs": dcs_name}, fields=["name", "condition_no", "condition_title", "category", "original_category", "domain", "state", "detail", "assigned_to", "hold_state", "last_action_note", "raised_by", "raised_on", "cleared_by", "cleared_on", "clearance_note", "accepted_by", "accepted_on", "acceptance_reason", "acknowledged", "exposure_amount", "exposure_note", "follow_up_date"], order_by="condition_no asc")

	blockers = []
	watch = []
	risks = []
	for c in conds:
		if c.get("state") == "Accepted Risk":
			risks.append(c)
		elif c.get("category") == "Blocker":
			blockers.append(c)
		else:
			watch.append(c)
	open_blk = 0
	for b in blockers:
		if b.get("state") == "Open":
			open_blk = open_blk + 1

	# ---- the three separate states, shown to every role ----
	# Award reversal state is process metadata, not a commercial value, so it is projected to every role like the other three states.

	# --- release readiness (same rule the delivery release service enforces) ---
	# Shown so the workspace can explain a refusal before the user attempts it. This is a read-only
	# projection. The authoritative refusal lives in dcs_delivery_release.
	rr_note = ""
	lv_rev = int(s.custom_dcs_revision_no or 0)
	fz_sell = float(s.custom_frozen_total_selling or 0)
	fz_cost = float(s.custom_frozen_total_cost or 0)
	lv_sell = float(s.custom_working_total_selling or 0)
	lv_cost = float(s.custom_working_total_cost or 0)
	# EFFECTIVE COMMERCIAL POSITION: living values when revisions exist, otherwise the base sheet build-up.
	# MARGIN_FLOOR mirrors dcs_screen1.MARGIN_FLOOR and the gate_for() floor in dcs_apply_revision.
	# Safe-Exec namespaces cannot share constants and no configurable floor field exists.
	MARGIN_FLOOR = 20.0
	eff_sell = lv_sell if lv_rev > 0 else float(s.total_selling or 0)
	eff_margin = float(s.custom_working_margin_percent or 0) if lv_rev > 0 else float(s.margin_percent or 0)
	below_floor = 0
	if s.custom_margin_gate == "Blocked":
		below_floor = 1
	elif eff_sell > 0 and eff_margin < MARGIN_FLOOR:
		below_floor = 1
	if lv_rev > 0 and (absf(lv_sell - fz_sell) > 0.005 or absf(lv_cost - fz_cost) > 0.005):
		rr_note = "The living commercial position no longer matches the frozen baseline that was awarded. Delivery cannot be released against a commercial position that was never awarded. Reverse the award and re-award on the current position, or return the living position to the awarded baseline."
	elif s.custom_po_recon_state == "Reconciled" and s.custom_po_scope_revision and s.custom_revision_reference and s.custom_po_scope_revision != s.custom_revision_reference:
		rr_note = "The customer PO was reconciled against " + str(s.custom_po_scope_revision) + " but the current commercial position is " + str(s.custom_revision_reference) + ". A value match against a superseded scope is never treated as reconciled. Re-reconcile the customer PO against the current revision before releasing."
	elif s.custom_approval_required and s.custom_approval_required != "None" and s.custom_approval_state != "Approved":
		rr_note = "A concession on this deal is awaiting " + str(s.custom_approval_required) + " approval (current approval state " + str(s.custom_approval_state) + "). Delivery cannot be released while an unapproved commercial concession is outstanding."
	elif below_floor > 0:
		rr_note = "Not commercially aligned — margin below floor"
	rr_ready = 1 if rr_note == "" else 0
	result["release_readiness"] = {"commercially_aligned": rr_ready, "note": rr_note, "basis": "Frozen baseline, reconciled customer PO and living position must still agree at the moment of release."}
	result["states"] = {"customer_award": s.custom_award_state or "Not Awarded", "commercial_baseline_frozen": s.custom_baseline_frozen or 0, "delivery_release": s.custom_delivery_release_state or "Not Applicable", "separation_note": "These are three separate states. Recording an award never releases to delivery.", "delivery_owner": s.custom_delivery_owner, "awarded_on": s.custom_awarded_on, "frozen_on": s.custom_frozen_on, "released_on": s.custom_delivery_released_on, "override_used": s.custom_delivery_override or 0, "award_sequence_no": s.custom_award_sequence_no or 0, "award_reversal_state": s.custom_award_reversal_state or "", "award_reversal_count": s.custom_award_reversal_count or 0, "award_reversal_ref": s.custom_award_reversal_ref}
	result["legacy"] = {"workflow_state": s.workflow_state, "label": "LEGACY / INACTIVE", "note": "This value comes from the superseded Deal Cost Sheet workflow, which is inactive. It is not authoritative. The living DCS state above is authoritative."}
	result["deal"] = {"name": s.name, "customer": s.customer, "subject": s.subject, "opportunity": s.opportunity, "deal_owner": s.deal_owner, "docstatus": s.docstatus, "revision_reference": s.custom_revision_reference}

	if is_comm == 1:
		result["projection"] = "commercial"
		result["authority"] = {"can_record_award": 1, "can_reconcile_po": 1, "can_release": is_cc + is_md, "can_override": is_md, "can_clear_technical": 0, "can_clear_commercial": 1, "role_label": "Managing Director" if is_md == 1 else ("Commercial Controller" if is_cc == 1 else "Commercial"), "note": "Commercial users cannot close technical gates."}
		result["award"] = {"state": s.custom_award_state or "Not Awarded", "reference": s.custom_award_reference, "evidence_type": s.custom_award_evidence_type, "notes": s.custom_award_notes, "recorded_by": s.custom_awarded_by, "recorded_on": s.custom_awarded_on}
		result["frozen_baseline"] = {"frozen": s.custom_baseline_frozen or 0, "revision_no": s.custom_frozen_revision_no or 0, "total_cost": r2(s.custom_frozen_total_cost), "total_selling": r2(s.custom_frozen_total_selling), "gp": r2((s.custom_frozen_total_selling or 0) - (s.custom_frozen_total_cost or 0)), "margin_percent": s.custom_frozen_margin_percent or 0, "frozen_by": s.custom_frozen_by, "frozen_on": s.custom_frozen_on, "currency": s.currency, "note": "The frozen baseline is the authorised commercial position at the moment of award. It does not move with later negotiation."}
		result["living"] = {"revision_no": s.custom_dcs_revision_no or 0, "total_cost": r2(s.custom_working_total_cost), "total_selling": r2(s.custom_working_total_selling), "margin_percent": s.custom_working_margin_percent or 0, "approval_state": s.custom_approval_state, "approval_required": s.custom_approval_required, "margin_gate": s.custom_margin_gate}
		result["po"] = {"reference": s.custom_po_reference, "value": r2(s.custom_po_value), "scope_revision": s.custom_po_scope_revision, "payment_terms": s.custom_po_payment_terms, "value_check": s.custom_po_value_match or "Not Checked", "scope_check": s.custom_po_scope_match or "Not Checked", "terms_check": s.custom_po_terms_match or "Not Checked", "reconciliation_state": s.custom_po_recon_state or "Not Started", "reconciled_by": s.custom_po_recon_by, "reconciled_on": s.custom_po_recon_on, "basis": "PO value, PO scope or revision and PO payment terms are reconciled independently. A value match against a superseded or different scope is a hard blocker and is never treated as reconciled."}
		exposure = 0.0
		if s.custom_baseline_frozen:
			exposure = s.custom_frozen_total_cost or 0
		result["supplier_exposure"] = {"amount": r2(exposure), "currency": s.currency, "label": "Cost exposure not yet committed", "note": "This is the buying cost of the awarded position. It is a cost exposure not yet committed. It is not a realised loss and must never be reported as one."}
		result["conditions"] = {"blockers": blockers, "watch_items": watch, "accepted_risks": risks, "open_blockers": open_blk}
	else:
		result["projection"] = "technical"
		result["authority"] = {"can_record_award": 0, "can_reconcile_po": 0, "can_release": 0, "can_override": 0, "can_clear_technical": 1, "can_clear_commercial": 0, "role_label": "Technical", "note": "Technical users cannot close commercial or finance gates. No commercial value is returned to this projection."}
		lines = frappe.get_all("Deal Cost Item", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"}, fields=["idx", "item_code", "item_name", "customer_item_name", "brand", "item_category", "qty", "description"], order_by="idx asc")
		res_rows = frappe.get_all("Deal Cost Resource", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"}, fields=["idx", "resource_type", "role", "no_of_persons", "no_of_days", "hours", "linked_project", "remarks"], order_by="idx asc")
		# technical projection returns an explicit safe field list only.
		# exposure_amount and exposure_note are commercial values and are never returned here.
		def tech_safe(c):
			return {"name": c.get("name"), "condition_no": c.get("condition_no"), "condition_title": c.get("condition_title"), "category": c.get("category"), "original_category": c.get("original_category"), "domain": c.get("domain"), "state": c.get("state"), "detail": c.get("detail"), "assigned_to": c.get("assigned_to"), "hold_state": c.get("hold_state"), "last_action_note": c.get("last_action_note"), "raised_by": c.get("raised_by"), "raised_on": c.get("raised_on"), "cleared_by": c.get("cleared_by"), "cleared_on": c.get("cleared_on"), "clearance_note": c.get("clearance_note"), "accepted_by": c.get("accepted_by"), "accepted_on": c.get("accepted_on"), "acceptance_reason": c.get("acceptance_reason"), "acknowledged": c.get("acknowledged"), "follow_up_date": c.get("follow_up_date"), "exposure_withheld": "Commercial exposure is withheld from the technical projection."}
		tech_conds = []
		mine = []
		for c in conds:
			if c.get("domain") == "Technical":
				tech_conds.append(tech_safe(c))
			if c.get("assigned_to") == frappe.session.user:
				mine.append({"name": c.get("name"), "title": c.get("condition_title"), "domain": c.get("domain"), "category": c.get("category"), "state": c.get("state"), "can_clear": 1 if c.get("domain") == "Technical" else 0})
		result["awarded_scope"] = {"award_state": s.custom_award_state or "Not Awarded", "released": s.custom_delivery_release_state or "Not Applicable", "lines": lines, "approved_quantities_basis": "Quantities are taken from the awarded Deal Cost Sheet lines at the frozen revision. No rate, amount, margin or gross profit is returned to a technical user.", "resources": res_rows}
		result["delivery_requirements"] = {"delivery_owner": s.custom_delivery_owner, "customer": s.customer, "subject": s.subject, "award_reference": s.custom_award_reference, "release_state": s.custom_delivery_release_state or "Not Applicable", "note": "Work may only start once Delivery Release shows Released or Released with MD Override."}
		# ---- NRC-1 governed narrative for the technical projection ----
		# Field permlevel cannot protect a commercial figure that a human, or an
		# auto-generated governance note, typed into free text. Every narrative
		# string leaving this projection is passed through contract NRC-1 first.
		nrc_fields = ["condition_title", "detail", "last_action_note", "clearance_note", "acceptance_reason"]
		nrc_payload = []
		for c in tech_conds:
			for f in nrc_fields:
				nrc_payload.append(c.get(f))
		for mm in mine:
			nrc_payload.append(mm.get("title"))
		for ln in lines:
			nrc_payload.append(ln.get("description"))
			nrc_payload.append(ln.get("customer_item_name"))
		for rr in res_rows:
			nrc_payload.append(rr.get("remarks"))
		nrc_out = nrc_govern(nrc_payload)
		if nrc_out["ok"] == 1:
			kk = 0
			for c in tech_conds:
				for f in nrc_fields:
					c[f] = nrc_out["texts"][kk]
					kk = kk + 1
			for mm in mine:
				mm["title"] = nrc_out["texts"][kk]
				kk = kk + 1
			for ln in lines:
				ln["description"] = nrc_out["texts"][kk]
				kk = kk + 1
				ln["customer_item_name"] = nrc_out["texts"][kk]
				kk = kk + 1
			for rr in res_rows:
				rr["remarks"] = nrc_out["texts"][kk]
				kk = kk + 1
		else:
			for c in tech_conds:
				for f in nrc_fields:
					if c.get(f):
						c[f] = NRC_UNAVAILABLE
			for mm in mine:
				if mm.get("title"):
					mm["title"] = NRC_UNAVAILABLE
			for ln in lines:
				if ln.get("description"):
					ln["description"] = NRC_UNAVAILABLE
				if ln.get("customer_item_name"):
					ln["customer_item_name"] = NRC_UNAVAILABLE
			for rr in res_rows:
				if rr.get("remarks"):
					rr["remarks"] = NRC_UNAVAILABLE
		result["narrative_governance"] = {"contract": "NRC-1", "delegated": nrc_out["ok"], "cells": len(nrc_payload), "redacted": nrc_out.get("redacted") or 0, "note": nrc_out.get("reason") or "Operational narrative is governed by contract NRC-1."}
		result["technical_conditions"] = tech_conds
		result["my_actions"] = mine
		result["technical_dependencies"] = res_rows
		result["unavailable"] = [
			{"key": "site_readiness", "label": "Site readiness", "reason": "No site readiness field exists on the Deal Cost Sheet or on any linked record. Not fabricated."},
			{"key": "drawings_submittals", "label": "Drawings and submittal status", "reason": "No drawing or submittal register exists on this instance. Not fabricated."},
			{"key": "models_specs", "label": "Models and specifications", "reason": "Item code, brand and line description are returned where present. There is no separate model or specification register on Deal Cost Item."}
		]
	result["ok"] = 1

frappe.response["message"] = result
