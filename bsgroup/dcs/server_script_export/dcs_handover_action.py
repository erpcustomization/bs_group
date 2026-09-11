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

# dcs_handover_action
# Actions on a single handover condition.
# Domain separation is enforced server side:
#   Technical conditions can only be cleared by a technical role.
#   Commercial, Finance and Delivery conditions can only be cleared by a commercial role.
# Only the Managing Director may accept a blocker as a risk. The Commercial Controller may never override a blocker.

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

COMM_DOMAINS = ["Commercial", "Finance", "Delivery"]

result = {"ok": 0, "error": "", "action": "", "condition": {}}

cond_name = frappe.form_dict.get("condition")
action = frappe.form_dict.get("action")
note = frappe.form_dict.get("note")
assign_to = frappe.form_dict.get("assign_to")
ack = frappe.form_dict.get("acknowledged")
exposure = frappe.form_dict.get("exposure_amount")
exposure_note = frappe.form_dict.get("exposure_note")
follow_up = frappe.form_dict.get("follow_up_date")


# NRC-1: detect likely commercial disclosure in operator-supplied narrative
note_label = "action note"
if action == "Clear":
	note_label = "clearance note"
elif action == "Accept Risk":
	note_label = "acceptance reason"
nrc_chk = nrc_entry_check([note_label, "exposure note"], [note, exposure_note])
nrc_eval = "clean"
if nrc_chk["block"] != "":
	nrc_eval = "high"
elif nrc_chk["warn"] != "":
	nrc_eval = "warn"
result["narrative_guard_eval"] = nrc_eval
result["narrative_guard_delegated"] = nrc_chk["delegated"]

valid = ["Chase", "Assign", "Hold", "Return", "Clear", "Accept Risk"]
roles = get_user_roles(frappe.session.user)
is_md = 0
is_cc = 0
if MD in roles:
	is_md = 1
if CC in roles:
	is_cc = 1
is_comm = has_any(roles, COMMERCIAL_ROLES)
is_tech = has_any(roles, TECHNICAL_ROLES)

if not cond_name:
	result["error"] = "condition is required."
elif action not in valid:
	result["error"] = "action must be one of Chase, Assign, Hold, Return, Clear, Accept Risk."
elif not frappe.db.exists("DCS Handover Condition", cond_name):
	result["error"] = "Handover condition " + str(cond_name) + " does not exist."
elif frappe.db.get_value("Deal Cost Sheet", frappe.db.get_value("DCS Handover Condition", cond_name, "dcs"), "docstatus") == 2:
	result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
elif is_comm == 0 and is_tech == 0:
	result["error"] = "You hold neither a commercial nor a technical role. System Manager administration does not confer handover authority."
else:
	c = frappe.get_doc("DCS Handover Condition", cond_name)
	c.check_permission("write")
	domain = c.domain
	now = frappe.utils.now_datetime()
	me = frappe.session.user

	domain_ok = 0
	if domain == "Technical":
		if is_tech == 1:
			domain_ok = 1
	else:
		if is_comm == 1:
			domain_ok = 1

	if c.state == "Accepted Risk":
		result["error"] = "Condition " + str(cond_name) + " is a recorded ACCEPTED RISK. It retains its original blocker and can never be cleared, reopened or re-decided."
	elif c.state == "Cleared" and action in ["Clear", "Accept Risk"]:
		result["error"] = "Condition " + str(cond_name) + " is already cleared."
	elif action == "Clear" and domain_ok == 0:
		if domain == "Technical":
			result["error"] = "This is a TECHNICAL condition. Only a technical role may clear it. A commercial role cannot close a technical gate."
		else:
			result["error"] = "This is a " + str(domain).upper() + " condition. Only a commercial role may clear it. A technical role cannot close a commercial or finance gate."
	elif action == "Accept Risk" and is_md == 0:
		if is_cc == 1:
			result["error"] = "The Commercial Controller may chase, assign, hold or return a blocker but may never override it. Only the Managing Director may accept a blocker as a risk."
		else:
			result["error"] = "Only the Managing Director may accept a blocker as a risk."
	elif action == "Accept Risk" and c.category != "Blocker":
		result["error"] = "Only a Blocker may be accepted as a risk. This condition is a " + str(c.category) + "."
	elif action == "Accept Risk" and not note:
		result["error"] = "Accepting a blocker as a risk requires a written reason."
	elif action == "Accept Risk" and not (ack == 1 or ack == "1" or ack == True or ack == "true"):
		result["error"] = "Accepting a blocker as a risk requires an explicit acknowledgement that the blocker is not resolved and the exposure is carried."
	elif action == "Accept Risk" and not c.assigned_to:
		result["error"] = "An accepted risk must retain a named owner. Assign an owner before accepting the risk."
	elif action == "Assign" and not assign_to:
		result["error"] = "assign_to is required to assign a condition."
	elif action in ["Chase", "Hold", "Return"] and not note:
		result["error"] = "A note is required to " + str(action) + " a condition."
	elif action == "Clear" and not note:
		result["error"] = "A clearance note is required. A condition is never cleared silently."
	elif nrc_chk["block"] != "":
		result["error"] = nrc_chk["block"]
		result["narrative_guard"] = "blocked"
	else:
		if action == "Chase":
			c.hold_state = "Chased"
			c.last_action_note = "Chased by " + me + ": " + str(note)
		elif action == "Assign":
			c.assigned_to = assign_to
			c.last_action_note = "Assigned to " + str(assign_to) + " by " + me + ". " + str(note or "")
		elif action == "Hold":
			c.hold_state = "On Hold"
			c.last_action_note = "Placed on hold by " + me + ": " + str(note)
		elif action == "Return":
			c.hold_state = "Returned to Origin"
			c.last_action_note = "Returned by " + me + ": " + str(note)
		elif action == "Clear":
			c.state = "Cleared"
			c.cleared_by = me
			c.cleared_on = now
			c.clearance_note = note
			c.hold_state = "None"
		else:
			c.state = "Accepted Risk"
			c.category = "Accepted Risk"
			c.accepted_by = me
			c.accepted_on = now
			c.acceptance_reason = note
			c.acknowledged = 1
			c.exposure_note = exposure_note
			c.follow_up_date = follow_up
			if exposure:
				c.exposure_amount = float(exposure)
		# D2a Phase 2: snapshot both governed targets server side immediately before the write.
		D2A_HC_FIELDS = ["state", "category", "original_category", "assigned_to", "hold_state", "last_action_note", "cleared_by", "cleared_on", "clearance_note", "accepted_by", "accepted_on", "acceptance_reason", "acknowledged", "exposure_amount", "exposure_note", "follow_up_date"]
		D2A_SHEET_FIELDS = ["custom_delivery_release_state"]
		d2a_sheet = c.dcs
		d2a_hc_before = dcs_audit_snapshot("DCS Handover Condition", c.name, D2A_HC_FIELDS)
		d2a_sheet_before = dcs_audit_snapshot("Deal Cost Sheet", d2a_sheet, D2A_SHEET_FIELDS)
		c.flags.dcs_api_write = 1
		c.save()
		# dcs_governed_exposure_write: exposure_amount is permlevel 1 and no role holds L1 on
		# DCS Handover Condition, so an ORM save resets it. The governed service persists it via
		# the trusted db.set_value channel. Managing Director authority is enforced above.
		if action == "Accept Risk" and exposure:
			frappe.db.set_value("DCS Handover Condition", c.name, "exposure_amount", float(exposure), update_modified=False)
			c.exposure_amount = float(exposure)

		sheet = c.dcs
		blk = open_blockers(sheet)
		cur = frappe.db.get_value("Deal Cost Sheet", sheet, "custom_delivery_release_state")
		if cur not in ["Released", "Released with MD Override"]:
			rel = "Pending"
			if len(blk) > 0:
				rel = "Blocked"
			frappe.db.set_value("Deal Cost Sheet", sheet, {"custom_delivery_release_state": rel}, update_modified=True)

		# D2a Phase 2: the governed writes above have succeeded, so record the committed movement
		# across both targets, the handover condition itself and the sheet release state it drives.
		d2a_hc_after = dcs_audit_snapshot("DCS Handover Condition", c.name, D2A_HC_FIELDS)
		d2a_sheet_after = dcs_audit_snapshot("Deal Cost Sheet", d2a_sheet, D2A_SHEET_FIELDS)
		d2a_moved = dcs_audit_changes(D2A_HC_FIELDS, d2a_hc_before, d2a_hc_after, "DCS Handover Condition", c.name)
		d2a_moved = d2a_moved + dcs_audit_changes(D2A_SHEET_FIELDS, d2a_sheet_before, d2a_sheet_after, "Deal Cost Sheet", d2a_sheet)
		d2a_code = "DCS_HANDOVER_" + str(action).upper().replace(" ", "_")
		d2a_anchor = frappe.db.get_value("Deal Cost Sheet", d2a_sheet, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
		result["governance_event"] = dcs_audit_event(d2a_sheet, d2a_code, "Handover condition action: " + str(action), "dcs_handover_action", note, d2a_anchor.get("custom_dcs_revision_no") or 0, d2a_anchor.get("custom_revision_reference") or "", c.name, d2a_moved)
		result["ok"] = 1
		result["action"] = action
		result["condition"] = {"name": c.name, "title": c.condition_title, "category": c.category, "original_category": c.original_category, "domain": c.domain, "state": c.state, "assigned_to": c.assigned_to, "hold_state": c.hold_state, "accepted_by": c.accepted_by, "accepted_on": c.accepted_on, "acceptance_reason": c.acceptance_reason, "acknowledged": c.acknowledged, "exposure_amount": c.exposure_amount, "follow_up_date": c.follow_up_date}
		result["open_blockers_remaining"] = len(blk)
		result["narrative_contract"] = "NRC-1"
		if nrc_chk["warn"] != "":
			result["narrative_warning"] = nrc_chk["warn"]
		# governed echo: a technical caller never receives raw narrative back
		if is_comm == 0:
			gov = nrc_batch([str(c.condition_title or ""), str(c.acceptance_reason or "")])
			if gov["ok"] == 1:
				result["condition"]["title"] = gov["texts"][0]
				result["condition"]["acceptance_reason"] = gov["texts"][1]
			else:
				result["condition"]["title"] = "[withheld - governed redaction unavailable]"
				result["condition"]["acceptance_reason"] = "[withheld - governed redaction unavailable]"
			# Remove the protected commercial keys outright rather than nulling
			# them. A null key still advertises the existence of a protected
			# field to technical consumers. Commercial callers are unaffected.
			trimmed_condition = {}
			for ck in result["condition"]:
				if ck != "exposure_amount" and ck != "exposure_note":
					trimmed_condition[ck] = result["condition"][ck]
			result["condition"] = trimmed_condition

frappe.response["message"] = result
