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

# dcs_delivery_release
# Delivery Release is a SEPARATE state from Customer Award and from Commercial Baseline Frozen.
# Commercial Controller: may release only when every blocker is clear. May never override a blocker.
# Managing Director: normal release when clear, or an exceptional override which requires a written
# reason and an explicit acknowledgement. Every overridden blocker becomes an ACCEPTED RISK and
# retains its original blocker identity. It is never marked Clear.
# A named delivery owner is mandatory in every case, including override.

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
	c.insert()
	return c.name

def open_blockers(sheet_name):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "category": "Blocker", "state": "Open"}, fields=["name", "condition_title", "domain"])
	return rows

result = {"ok": 0, "error": "", "state": {}, "accepted_risks": []}

dcs_name = frappe.form_dict.get("dcs")
override = frappe.form_dict.get("override")
reason = frappe.form_dict.get("reason")
ack = frappe.form_dict.get("acknowledged")
note = frappe.form_dict.get("note")
follow_up = frappe.form_dict.get("follow_up_date")
exposure_note = frappe.form_dict.get("exposure_note")

# NRC-1: operator-supplied override / exposure narrative is readable by technical
# and operations roles, so a likely commercial disclosure is refused before write.
nrc_chk = nrc_entry_check(["override reason", "exposure note", "action note"], [reason, exposure_note, note])
nrc_eval = "clean"
if nrc_chk["block"] != "":
	nrc_eval = "high"
elif nrc_chk["warn"] != "":
	nrc_eval = "warn"
result["narrative_guard_eval"] = nrc_eval
result["narrative_contract"] = "NRC-1"

is_override = 0
if override == 1 or override == "1" or override == True or override == "true":
	is_override = 1
is_ack = 0
if ack == 1 or ack == "1" or ack == True or ack == "true":
	is_ack = 1

roles = get_user_roles(frappe.session.user)
is_md = 0
is_cc = 0
if MD in roles:
	is_md = 1
if CC in roles:
	is_cc = 1

if not dcs_name:
	result["error"] = "dcs is required."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
	result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif frappe.db.get_value("Deal Cost Sheet", dcs_name, "docstatus") == 2:
	result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
elif is_md == 0 and is_cc == 0:
	result["error"] = "Releasing to delivery is a Commercial Controller or Managing Director action."
elif nrc_chk["block"] != "":
	result["error"] = nrc_chk["block"]
	result["narrative_guard"] = "blocked"
else:
	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("write")
	blk = open_blockers(dcs_name)
	names = []
	for b in blk:
		names.append(str(b.get("condition_title")) + " (" + str(b.get("domain")) + ")")

	# --- post-award commercial drift check (defect fix, E2E regression) ---
	# The frozen baseline, the reconciled customer PO and the living position must still agree at the
	# moment of release. If negotiation continued after the award, releasing would hand delivery a
	# commercial position that was never awarded, never reconciled and possibly never approved.
	# This is refused for every role. An override is not the remedy, because there is no open blocker
	# to override. The remedy is to reverse the award and re-award on the current position.
	drift = ""
	lv_rev = int(s.custom_dcs_revision_no or 0)
	fz_sell = float(s.custom_frozen_total_selling or 0)
	fz_cost = float(s.custom_frozen_total_cost or 0)
	lv_sell = float(s.custom_working_total_selling or 0)
	lv_cost = float(s.custom_working_total_cost or 0)
	if lv_rev > 0 and (absf(lv_sell - fz_sell) > 0.005 or absf(lv_cost - fz_cost) > 0.005):
		drift = "The living commercial position (cost " + str(lv_cost) + ", selling " + str(lv_sell) + ") no longer matches the frozen baseline that was awarded (cost " + str(fz_cost) + ", selling " + str(fz_sell) + "). Delivery cannot be released against a commercial position that was never awarded. Reverse the award and re-award on the current position, or return the living position to the awarded baseline."
	elif s.custom_po_recon_state == "Reconciled" and s.custom_po_scope_revision and s.custom_revision_reference and s.custom_po_scope_revision != s.custom_revision_reference:
		drift = "The customer PO was reconciled against " + str(s.custom_po_scope_revision) + " but the current commercial position is " + str(s.custom_revision_reference) + ". A value match against a superseded scope is never treated as reconciled. Re-reconcile the customer PO against the current revision before releasing."
	elif s.custom_approval_required and s.custom_approval_required != "None" and s.custom_approval_state != "Approved":
		drift = "A concession on this deal is awaiting " + str(s.custom_approval_required) + " approval (current approval state " + str(s.custom_approval_state) + "). Delivery cannot be released while an unapproved commercial concession is outstanding."

	if s.custom_award_state != "Awarded":
		result["error"] = "No customer award has been recorded. Delivery cannot be released before an award is recorded and the commercial baseline is frozen."
	elif not s.custom_baseline_frozen:
		result["error"] = "The commercial baseline is not frozen. Delivery cannot be released."
	elif s.custom_delivery_release_state in ["Released", "Released with MD Override"]:
		result["error"] = "Delivery has already been released on this Deal Cost Sheet (" + str(s.custom_delivery_release_state) + ")."
	elif not s.custom_delivery_owner:
		result["error"] = "A named delivery owner is mandatory for every release, including a Managing Director override. Delivery cannot be released with no named owner."
	elif drift != "":
		result["error"] = drift
	elif len(blk) > 0 and is_override == 0:
		result["error"] = "Delivery cannot be released normally. " + str(len(blk)) + " blocker(s) remain open: " + "; ".join(names) + "."
	elif len(blk) > 0 and is_override == 1 and is_md == 0:
		result["error"] = "The Commercial Controller may release only when every blocker is clear and may never override a blocker. Only the Managing Director may release with an override."
	elif is_override == 1 and len(blk) == 0:
		result["error"] = "There are no open blockers. Release normally rather than recording an exceptional override."
	elif is_override == 1 and not reason:
		result["error"] = "A Managing Director override requires a written reason."
	elif is_override == 1 and is_ack == 0:
		result["error"] = "A Managing Director override requires an explicit acknowledgement that each overridden blocker remains unresolved and is carried as an accepted risk."
	else:
		now = frappe.utils.now_datetime()
		me = frappe.session.user
		accepted = []
		if is_override == 1:
			for b in blk:
				d = frappe.get_doc("DCS Handover Condition", b.get("name"))
				d.state = "Accepted Risk"
				d.category = "Accepted Risk"
				d.accepted_by = me
				d.accepted_on = now
				d.acceptance_reason = reason
				d.acknowledged = 1
				d.follow_up_date = follow_up
				d.exposure_note = exposure_note
				if not d.assigned_to:
					d.assigned_to = s.custom_delivery_owner
				d.flags.dcs_api_write = 1
				d.save()
				accepted.append({"condition": d.name, "title": d.condition_title, "original_category": d.original_category, "domain": d.domain, "state": d.state, "accepted_by": me, "accepted_on": now, "reason": reason, "owner": d.assigned_to, "follow_up_date": follow_up})

		new_state = "Released"
		if is_override == 1:
			new_state = "Released with MD Override"

		# D2a Phase 2: snapshot the governed fields server side immediately before the write.
		D2A_FIELDS = ["custom_delivery_release_state", "custom_delivery_released_by", "custom_delivery_released_on", "custom_delivery_override", "custom_delivery_override_reason", "custom_delivery_release_note"]
		d2a_before = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
		frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_delivery_release_state": new_state, "custom_delivery_released_by": me, "custom_delivery_released_on": now, "custom_delivery_override": is_override, "custom_delivery_override_reason": reason, "custom_delivery_release_note": note}, update_modified=True)

		# D2a Phase 2: the governed write above has succeeded, so record the committed movement.
		d2a_after = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
		d2a_moved = dcs_audit_changes(D2A_FIELDS, d2a_before, d2a_after, "Deal Cost Sheet", dcs_name)
		d2a_code = "DCS_DELIVERY_RELEASED"
		if is_override == 1:
			d2a_code = "DCS_DELIVERY_RELEASED_MD_OVERRIDE"
		d2a_anchor = frappe.db.get_value("Deal Cost Sheet", dcs_name, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
		result["governance_event"] = dcs_audit_event(dcs_name, d2a_code, "Release the awarded deal to delivery", "dcs_delivery_release", reason, d2a_anchor.get("custom_dcs_revision_no") or 0, d2a_anchor.get("custom_revision_reference") or "", "", d2a_moved)
		result["ok"] = 1
		result["accepted_risks"] = accepted
		result["state"] = {"delivery_release_state": new_state, "delivery_owner": s.custom_delivery_owner, "released_by": me, "override_used": is_override, "override_reason": reason, "accepted_risk_count": len(accepted), "award_state": s.custom_award_state, "baseline_frozen": s.custom_baseline_frozen, "docstatus_unchanged": s.docstatus, "note": "Customer Award, Commercial Baseline Frozen and Delivery Release remain three separate states. Accepted risks retain their original blocker and are never marked Clear."}

frappe.response["message"] = result

# --- Native timeline + notification emit (go-live Day 2) ---
try:
    if result.get("ok"):
        tlname = frappe.form_dict.get("dcs")
        tlstate = result.get("state") or {}
        tltext = ""
        tldr = tlstate.get("delivery_release_state")
        if tldr == "Released":
            tltext = "Delivery released to " + str(tlstate.get("delivery_owner"))
        if tldr == "Released with MD Override":
            tltext = "Delivery released with Managing Director override to " + str(tlstate.get("delivery_owner")) + " - accepted risks: " + str(tlstate.get("accepted_risk_count")) + " - override reason recorded on the Deal Cost Sheet for authorised commercial roles"
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
