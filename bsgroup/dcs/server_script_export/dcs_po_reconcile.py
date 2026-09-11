# ---------------- NRC-1 delegating client (self-contained) ----------------
# The canonical narrative redaction contract lives in Server Script
# "dcs_narrative_guard" (NRC-1). No surface re-implements the rules.
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
        out["block"] = "The " + str(highs[0]) + " appears to disclose a commercial amount. Handover and delivery narrative is readable by operations, technical and project roles, so commercial figures must be recorded in the governed commercial fields of the Deal Cost Sheet (cost, selling, margin) or in the exposure amount field, not in operational notes. Remove the figure from the " + str(highs[0]) + " and record it against the governed commercial field instead."
    elif len(poss) > 0:
        out["warn"] = "The " + str(poss[0]) + " contains a number that resembles a financial value. It has been accepted, but technical and operations projections will withhold it."
    return out
# -------------- end NRC-1 delegating client --------------

# dcs_po_reconcile
# Reconciles the customer PO against the FROZEN commercial baseline.
# PO value, PO scope/revision and PO payment terms are reconciled INDEPENDENTLY.
# A value match combined with a superseded or mismatched scope is a HARD BLOCKER.

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

def clear_auto(sheet_name, key, note):
	c = find_condition(sheet_name, key)
	if c is None:
		return 0
	if c.get("state") != "Open":
		return 0
	d = frappe.get_doc("DCS Handover Condition", c.get("name"))
	d.state = "Cleared"
	d.cleared_by = frappe.session.user
	d.cleared_on = frappe.utils.now_datetime()
	d.clearance_note = note
	d.flags.dcs_api_write = 1
	d.save()
	return 1

result = {"ok": 0, "error": "", "checks": {}, "state": {}, "hard_blocker": 0}

dcs_name = frappe.form_dict.get("dcs")
po_ref = frappe.form_dict.get("po_reference")
po_val_raw = frappe.form_dict.get("po_value")
po_scope = frappe.form_dict.get("po_scope_revision")
po_terms = frappe.form_dict.get("po_payment_terms")
terms_ok = frappe.form_dict.get("payment_terms_accepted")

# NRC-1: PO payment terms are commercial content recorded by commercial authority,
# so they are not refused here. They are, however, surfaced as a warning because
# the resulting Finance-domain condition narrative is readable by operations and
# technical roles, where the governed contract will withhold the figures.
nrc_chk = nrc_entry_check(["PO payment terms", "PO scope revision"], [po_terms, po_scope])
result["narrative_contract"] = "NRC-1"
if nrc_chk["block"] != "":
	result["narrative_warning"] = "The PO payment terms contain a commercial figure. This is accepted for the commercial record, but operations, technical and project roles will see the figure withheld in the Handover Condition Register and in the operational handover document."
elif nrc_chk["warn"] != "":
	result["narrative_warning"] = nrc_chk["warn"]

roles = get_user_roles(frappe.session.user)

if not dcs_name:
	result["error"] = "dcs is required."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
	result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif frappe.db.get_value("Deal Cost Sheet", dcs_name, "docstatus") == 2:
	result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
elif has_any(roles, COMMERCIAL_ROLES) == 0:
	result["error"] = "PO reconciliation is a commercial and finance action. Technical roles cannot reconcile a customer PO."
else:
	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("write")
	if not s.custom_baseline_frozen:
		result["error"] = "There is no frozen commercial baseline to reconcile against. Record the award first."
	elif not po_ref:
		result["error"] = "A customer PO reference is required."
	elif po_val_raw is None or po_val_raw == "":
		result["error"] = "A PO value is required. PO value is reconciled independently of PO scope."
	elif not po_scope:
		result["error"] = "The PO must cite a scope or revision. PO scope is reconciled independently of PO value."
	else:
		po_val = float(po_val_raw)
		frozen_sell = s.custom_frozen_total_selling or 0
		frozen_ref = s.custom_revision_reference or ""
		frozen_no = s.custom_frozen_revision_no or 0

		# ---- check 1: value, independent ----
		v_state = "Mismatch"
		if absf(po_val - frozen_sell) <= 0.01:
			v_state = "Match"

		# ---- check 2: scope / revision, independent ----
		cited = str(po_scope).strip()
		s_state = "Mismatch - Different Scope"
		if cited == str(frozen_ref):
			s_state = "Match"
		else:
			known = frappe.get_all("DCS Revision", filters={"dcs": dcs_name, "name": cited}, fields=["revision_no"], limit_page_length=1)
			for k in known:
				if (k.get("revision_no") or 0) < frozen_no:
					s_state = "Mismatch - Superseded"

		# ---- check 3: payment terms, independent ----
		t_state = "Not Checked"
		if terms_ok == 1 or terms_ok == "1" or terms_ok == "true" or terms_ok == True:
			t_state = "Accepted"
		elif po_terms:
			t_state = "Mismatch"

		all_ok = 0
		if v_state == "Match" and s_state == "Match" and t_state == "Accepted":
			all_ok = 1
		recon = "Mismatch"
		if all_ok == 1:
			recon = "Reconciled"

		# ---- HARD BLOCKER: value agrees but scope does not ----
		hard = 0
		if v_state == "Match" and s_state != "Match":
			hard = 1
			raise_condition(dcs_name, "po_scope_hard", "HARD BLOCKER - PO value reconciles but PO scope does not", "Blocker", "Finance", "The recorded customer PO value reconciles with the approved and frozen commercial position, but the PO cites scope reference '" + cited + "' against the frozen commercial reference '" + str(frozen_ref) + "' (" + s_state + "). A value match against a superseded or different scope is treated as a hard blocker because the customer may be buying a different deliverable at the agreed price. This must be reconciled with the customer, or formally accepted through the Managing Director override path. Commercial figures are deliberately not restated here; they remain available to authorised commercial roles on the Deal Cost Sheet.")
		if v_state != "Match":
			raise_condition(dcs_name, "po_value", "PO value does not reconcile with the frozen commercial position", "Blocker", "Finance", "The recorded customer PO value does not reconcile with the approved and frozen commercial position. Reconciliation is required before delivery release, and commercial review is required to determine whether the PO, the frozen position, or both must change. Commercial figures are deliberately not restated here; they remain available to authorised commercial roles on the Deal Cost Sheet.")
		else:
			clear_auto(dcs_name, "po_value", "PO value agrees with the frozen commercial baseline.")
		if t_state == "Mismatch":
			raise_condition(dcs_name, "po_terms", "PO payment terms not accepted", "Watch Item", "Finance", "Customer PO payment terms have been recorded against this deal but have not been accepted by the commercial owner. Commercial review and acceptance are required before this condition can be cleared. The recorded terms are deliberately not restated here; they remain available to authorised commercial roles on the Deal Cost Sheet.")
		elif t_state == "Accepted":
			clear_auto(dcs_name, "po_terms", "PO payment terms accepted by the commercial owner.")

		if all_ok == 1:
			clear_auto(dcs_name, "po_reconciliation", "PO value, PO scope and PO payment terms each reconciled against the frozen commercial baseline.")

		# D2a Phase 2: snapshot the governed fields server side immediately before the write.
		D2A_FIELDS = ["custom_po_reference", "custom_po_value", "custom_po_scope_revision", "custom_po_payment_terms", "custom_po_value_match", "custom_po_scope_match", "custom_po_terms_match", "custom_po_recon_state", "custom_po_recon_by", "custom_po_recon_on", "custom_delivery_release_state"]
		d2a_before = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
		frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_po_reference": po_ref, "custom_po_value": po_val, "custom_po_scope_revision": cited, "custom_po_payment_terms": po_terms, "custom_po_value_match": v_state, "custom_po_scope_match": s_state, "custom_po_terms_match": t_state, "custom_po_recon_state": recon, "custom_po_recon_by": frappe.session.user, "custom_po_recon_on": frappe.utils.now_datetime()}, update_modified=True)

		blk = open_blockers(dcs_name)
		rel = "Pending"
		if len(blk) > 0:
			rel = "Blocked"
		if s.custom_delivery_release_state not in ["Released", "Released with MD Override"]:
			frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_delivery_release_state": rel}, update_modified=True)

		# D2a Phase 2: both governed writes above have succeeded, so record the committed movement.
		d2a_after = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
		d2a_moved = dcs_audit_changes(D2A_FIELDS, d2a_before, d2a_after, "Deal Cost Sheet", dcs_name)
		d2a_anchor = frappe.db.get_value("Deal Cost Sheet", dcs_name, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
		result["governance_event"] = dcs_audit_event(dcs_name, "DCS_PO_RECONCILED", "Reconcile the customer purchase order against the frozen commercial baseline", "dcs_po_reconcile", "", d2a_anchor.get("custom_dcs_revision_no") or 0, d2a_anchor.get("custom_revision_reference") or "", po_ref, d2a_moved)
		result["ok"] = 1
		result["hard_blocker"] = hard
		result["checks"] = {"value": {"state": v_state, "po_value": po_val, "frozen_selling": frozen_sell, "basis": "Reconciled independently of scope and terms."}, "scope": {"state": s_state, "po_cites": cited, "frozen_revision": frozen_ref, "basis": "Reconciled independently of value. A value match with a superseded or different scope is a hard blocker."}, "payment_terms": {"state": t_state, "terms": po_terms, "basis": "Reconciled independently of value and scope."}}
		result["state"] = {"po_reconciliation_state": recon, "delivery_release_state": rel, "open_blockers": len(blk), "docstatus_unchanged": s.docstatus}

frappe.response["message"] = result

# --- Native timeline + notification emit (go-live Day 2) ---
try:
    if result.get("ok"):
        tlname = frappe.form_dict.get("dcs")
        tlstate = result.get("state") or {}
        tltext = ""
        tlpo = tlstate.get("po_reconciliation_state")
        if tlpo:
            if tlpo != "Reconciled":
                tltext = "Customer PO mismatch - reconciliation " + str(tlpo) + " - open blockers " + str(tlstate.get("open_blockers"))
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
