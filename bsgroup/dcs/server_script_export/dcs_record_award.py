# ---------------- NRC-1 delegating client (self-contained) ----------------
# The canonical narrative redaction contract lives in Server Script
# "dcs_narrative_guard" (NRC-1). No surface re-implements the rules.
# Note: Script Reports run safe_exec with an explicit locals mapping, so
# module-level constants are NOT visible inside functions. Everything this
# helper needs is therefore declared inside the function body.
def nrc_batch(items):
    out = {"ok": 0, "texts": [], "levels": [], "err": ""}
    if items is None:
        return out
    if len(items) == 0:
        out["ok"] = 1
        return out
    try:
        frappe.call("dcs_narrative_guard", mode="redact_batch", items=items)
        got = frappe.response.get("message")
        if got:
            if got.get("ok") == 1 and got.get("contract") == "NRC-1" and got.get("count") == len(items):
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
# -------------- end NRC-1 delegating client --------------

# ---- NRC-1 entry-time narrative disclosure guard ----
def nrc_entry_check(labels, values):
    out = {"block": "", "warn": "", "delegated": 0}
    keys = []
    items = []
    i = 0
    while i < len(values):
        v = values[i]
        if v is not None and str(v) != "":
            items.append(str(v))
            keys.append(labels[i])
        i = i + 1
    if len(items) == 0:
        return out
    got = nrc_batch(items)
    if got["ok"] != 1:
        out["warn"] = "The governed narrative check (NRC-1) could not be executed for this note. Technical and operations projections withhold narrative values while the check is unavailable."
        return out
    out["delegated"] = 1
    highs = []
    poss = []
    k = 0
    while k < len(got["levels"]):
        if got["levels"][k] == "high":
            highs.append(keys[k])
        elif got["levels"][k] == "possible":
            poss.append(keys[k])
        k = k + 1
    if len(highs) > 0:
        out["block"] = "The " + str(highs[0]) + " appears to disclose a commercial amount. Handover narrative is readable by operations, technical and project roles, so commercial figures must be recorded in the governed commercial fields of the Deal Cost Sheet (cost, selling, margin) or in the exposure amount field, not in operational notes. Remove the figure from the " + str(highs[0]) + " and record it against the governed commercial field instead."
    elif len(poss) > 0:
        out["warn"] = "The " + str(poss[0]) + " contains a number that resembles a financial value. It has been accepted, but technical and operations projections will withhold it."
    return out
# ---- end NRC-1 entry-time guard ----

# dcs_record_award
# RECORD AWARD ONLY. Records the customer award event and freezes the approved
# commercial baseline. It NEVER releases to delivery. Delivery Release is a
# separate state and is always left Pending or Blocked by this action.

# --- D2a CANONICAL GOVERNED AUDIT HELPER (shared, byte identical across instrumented endpoints) ---
# Builds and inserts one append-only DCS Governance Event plus one child row per genuinely
# changed field. Trusted, server-derived inputs only: no caller supplied actor, role or
# authority is accepted here or anywhere downstream. Actor, timestamp, outcome and
# correlation id are derived by the DCS Governance Event Insert Guard, which also drops
# unchanged rows and resolves field labels and value types from live metadata.
# This helper never commits. It participates in the caller transaction so that a business
# mutation and its audit event either both survive or both roll back.
def dcs_audit_event(a_dcs, a_code, a_label, a_endpoint, a_reason, a_rev_no, a_rev_ref, a_evid, a_changes):
	kept = []
	for ch in a_changes:
		ov = ch.get("old")
		nv = ch.get("new")
		if ov is None:
			ov = ""
		if nv is None:
			nv = ""
		if str(ov) == str(nv):
			continue
		kept.append({"fieldname": ch.get("field"), "target_doctype": ch.get("dt") or "Deal Cost Sheet", "target_name": ch.get("dn") or a_dcs, "old_value": str(ov), "new_value": str(nv)})
	if len(kept) < 1:
		return ""
	ev = frappe.new_doc("DCS Governance Event")
	ev.dcs = a_dcs
	ev.event_code = a_code
	ev.action_label = a_label
	ev.source_endpoint = a_endpoint
	ev.reason = a_reason
	ev.revision_no = a_rev_no
	ev.revision_reference = a_rev_ref
	ev.evidence_reference = a_evid
	ev.changes = json.dumps(kept)
	ev.change_count = len(kept)
	ev.flags.dcs_audit_write = 1
	ev.insert(ignore_permissions=True)
	return ev.name
# --- END D2a CANONICAL GOVERNED AUDIT HELPER ---
# --- D2a PHASE 2 SNAPSHOT COMPANIONS (shared, byte identical across Phase 2 endpoints) ---
# Pure read helpers used to prove the actual committed movement. A snapshot is taken server
# side immediately before the governed mutation and a second one immediately after it has
# succeeded, so every recorded before -> after pair is a real committed change rather than an
# intention. Fields that did not move are dropped, so a true no-op produces no event at all.
def dcs_audit_snapshot(a_dt, a_dn, a_fields):
	snap = {}
	if not a_dn:
		return snap
	row = frappe.db.get_value(a_dt, a_dn, a_fields, as_dict=True)
	if row is None:
		return snap
	for f in a_fields:
		v = row.get(f)
		if v is None:
			v = ""
		snap[f] = str(v)
	return snap
def dcs_audit_changes(a_fields, a_before, a_after, a_dt, a_dn):
	moved = []
	for f in a_fields:
		ov = a_before.get(f)
		nv = a_after.get(f)
		if ov is None:
			ov = ""
		if nv is None:
			nv = ""
		if str(ov) == str(nv):
			continue
		moved.append({"field": f, "old": ov, "new": nv, "dt": a_dt, "dn": a_dn})
	return moved
# --- END D2a PHASE 2 SNAPSHOT COMPANIONS ---
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
	c.flags.dcs_api_write = 1
	c.insert(ignore_permissions=True)
	return c.name

def open_blockers(sheet_name):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "category": "Blocker", "state": "Open"}, fields=["name", "condition_title", "domain"])
	return rows
def clear_reversal_block(sheet_name, new_ref):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "source_key": "award_reversed", "state": "Open"}, fields=["name"])
	done = []
	for r in rows:
		c = frappe.get_doc("DCS Handover Condition", r.get("name"))
		c.state = "Cleared"
		c.cleared_by = frappe.session.user
		c.cleared_on = frappe.utils.now_datetime()
		c.clearance_note = "Cleared automatically because the deal has been re-awarded under a new award event with reference " + str(new_ref) + ". The reversed award remains visible in history."
		c.flags.dcs_api_write = 1
		c.save()
		done.append(c.name)
	return done


result = {"ok": 0, "error": "", "state": {}, "conditions_raised": []}

dcs_name = frappe.form_dict.get("dcs")
award_ref = frappe.form_dict.get("award_reference")
evidence = frappe.form_dict.get("evidence_type")
notes = frappe.form_dict.get("notes")

# NRC-1: detect likely commercial disclosure in the operator-supplied award note.
# custom_award_notes is a permlevel-0 field surfaced to operational roles through
# dcs_screen5 and the technical handover document, so it is entry-validated here.
nrc_chk = nrc_entry_check(["award note"], [notes])
nrc_eval = "clean"
if nrc_chk["block"] != "":
	nrc_eval = "high"
elif nrc_chk["warn"] != "":
	nrc_eval = "warn"
result["narrative_guard_eval"] = nrc_eval
result["narrative_guard_delegated"] = nrc_chk["delegated"]
result["narrative_guard_warning"] = nrc_chk["warn"]
valid_ev = ["Customer PO", "Letter of Award", "Email Confirmation", "Verbal - Not Evidenced", "Not Provided"]

roles = get_user_roles(frappe.session.user)

if not dcs_name:
	result["error"] = "dcs is required."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
	result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif frappe.db.get_value("Deal Cost Sheet", dcs_name, "docstatus") == 2:
	result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
elif has_any(roles, COMMERCIAL_ROLES) == 0:
	result["error"] = "Recording a customer award is a commercial action. Technical roles and System Manager administration cannot record an award."
elif evidence not in valid_ev:
	result["error"] = "evidence_type must be one of Customer PO, Letter of Award, Email Confirmation, Verbal - Not Evidenced, Not Provided."
elif nrc_chk["block"] != "":
	result["error"] = nrc_chk["block"]
else:
	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("write")
	req = s.custom_approval_required
	appr = s.custom_approval_state

	authorised = 0
	if req == "None":
		authorised = 1
	if appr == "Approved":
		authorised = 1

	if s.custom_award_state == "Awarded":
		result["error"] = "An award is already recorded on this Deal Cost Sheet on " + str(s.custom_awarded_on) + ". The commercial baseline is frozen and an award event cannot be recorded twice."
	elif (s.custom_dcs_revision_no or 0) < 1:
		result["error"] = "The living commercial position has not been initialised. There is nothing to freeze."
	elif req == "Blocked":
		result["error"] = "The current commercial position is above the 26% concession ceiling and was never authorised. An award cannot be recorded against an unauthorised position."
	elif authorised == 0:
		result["error"] = "The current position requires Managing Director approval and is in state '" + str(appr) + "'. Record the award only against an authorised commercial position."
	else:
		now = frappe.utils.now_datetime()
		me = frappe.session.user
		raised = []

		# ---- freeze the approved commercial baseline ----
		frozen_cost = s.custom_working_total_cost or 0
		frozen_sell = s.custom_working_total_selling or 0
		frozen_margin = s.custom_working_margin_percent or 0
		frozen_rev = s.custom_dcs_revision_no or 0

		# ---- conditions that must exist before any delivery release ----
		raised.append(raise_condition(dcs_name, "po_reconciliation", "Customer PO not reconciled", "Blocker", "Finance", "The customer PO has not been reconciled against the frozen commercial baseline. PO value, PO scope or revision, and PO payment terms must each be reconciled independently."))
		if s.custom_margin_gate == "Blocked":
			raised.append(raise_condition(dcs_name, "margin_gate", "Margin floor gate is blocked", "Blocker", "Commercial", "The commercial margin floor gate is currently blocked for this deal. The margin gate is independent of approval routing and is not cleared by an approval or by an award; it must be resolved commercially or formally overridden. The evaluated margin figures and the commercial gate reason are deliberately not restated here; they remain available to authorised commercial roles on the Deal Cost Sheet."))
		if evidence == "Not Provided":
			raised.append(raise_condition(dcs_name, "award_evidence", "No customer award evidence provided", "Blocker", "Commercial", "The award was recorded without any customer evidence. Written customer award evidence must be obtained and attached before delivery is released."))
		elif evidence == "Verbal - Not Evidenced":
			raised.append(raise_condition(dcs_name, "award_evidence", "Award is verbal and not yet evidenced in writing", "Blocker", "Commercial", "The award was recorded as verbal. Written customer award evidence must be obtained before delivery is released."))
		elif not award_ref:
			raised.append(raise_condition(dcs_name, "award_evidence", "Award evidence reference missing", "Watch Item", "Commercial", "An evidence type of " + str(evidence) + " was recorded but no customer reference was captured."))
		raised.append(raise_condition(dcs_name, "delivery_owner", "No named delivery owner", "Blocker", "Delivery", "A named delivery owner is mandatory for every delivery release, including a Managing Director override. Delivery cannot be released while this is open."))
		raised.append(raise_condition(dcs_name, "technical_readiness", "Technical readiness not confirmed", "Blocker", "Technical", "Awarded technical scope, approved quantities, site readiness and submittal status must be confirmed by a technical owner. This condition can only be cleared by a technical role."))

		blk = open_blockers(dcs_name)
		release_state = "Pending"
		if len(blk) > 0:
			release_state = "Blocked"

		aseq = (s.custom_award_sequence_no or 0) + 1
		cleared_rev_block = clear_reversal_block(dcs_name, award_ref)
		# D2a Phase 2: snapshot the governed fields server side immediately before the write.
		D2A_FIELDS = ["custom_award_state", "custom_award_reference", "custom_award_evidence_type", "custom_award_notes", "custom_awarded_by", "custom_awarded_on", "custom_baseline_frozen", "custom_frozen_revision_no", "custom_frozen_total_cost", "custom_frozen_total_selling", "custom_frozen_margin_percent", "custom_frozen_by", "custom_frozen_on", "custom_delivery_release_state", "custom_po_recon_state", "custom_award_sequence_no", "custom_award_reversal_state"]
		d2a_before = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
		frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_award_state": "Awarded", "custom_award_reference": award_ref, "custom_award_evidence_type": evidence, "custom_award_notes": notes, "custom_awarded_by": me, "custom_awarded_on": now, "custom_baseline_frozen": 1, "custom_frozen_revision_no": frozen_rev, "custom_frozen_total_cost": frozen_cost, "custom_frozen_total_selling": frozen_sell, "custom_frozen_margin_percent": frozen_margin, "custom_frozen_by": me, "custom_frozen_on": now, "custom_delivery_release_state": release_state, "custom_po_recon_state": "Not Started", "custom_award_sequence_no": aseq, "custom_award_reversal_state": ""}, update_modified=True)

		# D2a Phase 2: the governed write above has succeeded, so record the committed movement.
		d2a_after = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
		d2a_moved = dcs_audit_changes(D2A_FIELDS, d2a_before, d2a_after, "Deal Cost Sheet", dcs_name)
		d2a_anchor = frappe.db.get_value("Deal Cost Sheet", dcs_name, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
		result["governance_event"] = dcs_audit_event(dcs_name, "DCS_AWARD_RECORDED", "Record a customer award against the frozen commercial baseline", "dcs_record_award", notes, d2a_anchor.get("custom_dcs_revision_no") or 0, d2a_anchor.get("custom_revision_reference") or "", award_ref, d2a_moved)
		result["ok"] = 1
		result["conditions_raised"] = raised
		result["state"] = {"award_state": "Awarded", "award_sequence_no": aseq, "reversal_block_cleared": cleared_rev_block, "award_reference": award_ref, "evidence_type": evidence, "baseline_frozen": 1, "frozen_revision_no": frozen_rev, "frozen_total_cost": frozen_cost, "frozen_total_selling": frozen_sell, "frozen_margin_percent": frozen_margin, "delivery_release_state": release_state, "open_blockers": len(blk), "docstatus_unchanged": s.docstatus, "note": "Award recorded and commercial baseline frozen. Delivery has NOT been released. Delivery Release is a separate state and is currently " + release_state + "."}

frappe.response["message"] = result

# --- Native timeline + notification emit (go-live Day 2) ---
try:
    if result.get("ok"):
        tlname = frappe.form_dict.get("dcs")
        tlstate = result.get("state") or {}
        tltext = ""
        if tlstate.get("award_state") == "Awarded":
            tltext = "Award recorded - reference " + str(tlstate.get("award_reference")) + " (" + str(tlstate.get("evidence_type")) + ") - baseline frozen at revision " + str(tlstate.get("frozen_revision_no"))
        if tlname:
            if tltext:
                tlc = frappe.new_doc("Comment")
                tlc.comment_type = "Info"
                tlc.reference_doctype = "Deal Cost Sheet"
                tlc.reference_name = tlname
                tlc.content = tltext
                tlc.insert(ignore_permissions=True)
                tlusers = []
                tlo = frappe.db.get_value("Deal Cost Sheet", tlname, "deal_owner")
                tld = frappe.db.get_value("Deal Cost Sheet", tlname, "custom_delivery_owner")
                if tlo:
                    tlusers.append(tlo)
                if tld:
                    if tld not in tlusers:
                        tlusers.append(tld)
                for tlu in tlusers:
                    if tlu != frappe.session.user:
                        tln = frappe.new_doc("Notification Log")
                        tln.for_user = tlu
                        tln.from_user = frappe.session.user
                        tln.type = "Alert"
                        tln.document_type = "Deal Cost Sheet"
                        tln.document_name = tlname
                        tln.subject = tltext
                        tln.insert(ignore_permissions=True)
except Exception as e:
    pass
