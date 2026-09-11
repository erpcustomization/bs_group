# dcs_award_reversal
# Controlled reversal of a recorded customer award.
# The Award Event is IMMUTABLE. This service never cancels, never amends, never deletes.
# It never edits custom_award_reference, custom_awarded_by, custom_awarded_on,
# custom_award_evidence_type or any custom_frozen_* baseline field.
# It writes a separate DCS Award Reversal record and moves only service-owned state.

MD = "Managing Director"

def get_user_roles(u):
	rows = frappe.get_all("Has Role", filters={"parent": u, "parenttype": "User"}, fields=["role"])
	out = []
	for r in rows:
		out.append(r.get("role"))
	return out

def next_reversal_no(sheet_name):
	rows = frappe.get_all("DCS Award Reversal", filters={"dcs": sheet_name}, fields=["reversal_no"], order_by="reversal_no desc", limit_page_length=1)
	n = 0
	for r in rows:
		n = r.get("reversal_no") or 0
	return n + 1

def next_condition_no(sheet_name):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name}, fields=["condition_no"], order_by="condition_no desc", limit_page_length=1)
	n = 0
	for r in rows:
		n = r.get("condition_no") or 0
	return n + 1

def raise_reversal_condition(sheet_name, detail):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "source_key": "award_reversed", "state": "Open"}, fields=["name"], limit_page_length=1)
	for r in rows:
		return r.get("name")
	c = frappe.new_doc("DCS Handover Condition")
	c.dcs = sheet_name
	c.condition_no = next_condition_no(sheet_name)
	c.condition_title = "Award reversed - delivery release is stopped"
	c.category = "Blocker"
	c.original_category = "Blocker"
	c.domain = "Commercial"
	c.state = "Open"
	c.detail = detail
	c.raised_by = frappe.session.user
	c.raised_on = frappe.utils.now_datetime()
	c.auto_generated = 1
	c.source_key = "award_reversed"
	c.flags.dcs_api_write = 1
	c.insert(ignore_permissions=True)
	return c.name

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
result = {"ok": 0, "error": "", "user": frappe.session.user, "authority": "", "mode": "", "state": {}, "reversal": "", "condition": ""}

dcs_name = frappe.form_dict.get("dcs")
reason = frappe.form_dict.get("reason") or ""
ack = str(frappe.form_dict.get("acknowledge") or "")
evidence_ref = frappe.form_dict.get("evidence_reference") or ""
requested_by = frappe.form_dict.get("requested_by") or ""
mode = frappe.form_dict.get("mode") or "check"

reason = reason.strip()
ack = ack.strip().upper()
ack_ok = 0
if ack == "1" or ack == "YES" or ack == "TRUE":
	ack_ok = 1

roles = get_user_roles(frappe.session.user)
is_md = 0
if MD in roles:
	is_md = 1
	result["authority"] = MD
result["mode"] = mode

if not dcs_name:
	result["error"] = "dcs is required."
elif not reason:
	result["error"] = "A reversal reason is mandatory. An award is never reversed without a stated commercial reason recorded against the reversal."
elif ack_ok == 0:
	result["error"] = "Acknowledgement is mandatory. The Managing Director must acknowledge that delivery release is stopped, that the original award event remains immutable in history, and that delivery already performed is not rolled back automatically."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
	result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif frappe.db.get_value("Deal Cost Sheet", dcs_name, "docstatus") == 2:
	result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
else:
	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("read")
	if is_md == 0:
		result["error"] = "Award reversal is a Managing Director action. No other role, including the Commercial Controller, the Sales Manager and System Manager administration, may reverse a recorded award."
	elif s.custom_award_reversal_state == "Reversed":
		result["error"] = "The award on this Deal Cost Sheet was already reversed on " + str(s.custom_award_reversed_on) + " under reversal " + str(s.custom_award_reversal_ref) + ". An award reversal cannot be applied twice. A new award must be recorded before a further reversal is possible."
	elif s.custom_award_state != "Awarded":
		result["error"] = "There is no active award on this Deal Cost Sheet to reverse. The current award state is '" + str(s.custom_award_state or "Not Awarded") + "'."
	else:
		now = frappe.utils.now_datetime()
		me = frappe.session.user
		rel_state = s.custom_delivery_release_state or "Not Applicable"
		was_released = 0
		if rel_state == "Released" or rel_state == "Released with MD Override":
			was_released = 1
		op_state = "Not Required"
		op_note = "Delivery had not been released when the award was reversed. No operational work was authorised by this award."
		if was_released == 1:
			op_state = "Required - Delivery Already Released"
			op_note = "Delivery was already released in state '" + str(rel_state) + "' when this award was reversed. Operational work already performed is NOT rolled back by this reversal. A named operational review must decide what is stood down, what is retained and what is recoverable."
		appr_at = s.custom_approval_state or ""
		returned_to = "In Negotiation"
		new_rel = "Blocked"
		if mode != "reverse":
			result["ok"] = 1
			result["state"] = {"preview": 1, "award_reference": s.custom_award_reference, "awarded_on": str(s.custom_awarded_on), "delivery_release_state_now": rel_state, "delivery_release_state_after": new_rel, "operational_review_after": op_state, "approval_state_now": appr_at, "approval_state_after": returned_to, "note": "Preview only. Nothing has been written. Call again with mode=reverse to record the reversal."}
		else:
			s.check_permission("write")
			req_by = me
			if requested_by:
				if frappe.db.exists("User", requested_by):
					req_by = requested_by
			rn = next_reversal_no(dcs_name)
			rv = frappe.new_doc("DCS Award Reversal")
			rv.dcs = dcs_name
			rv.reversal_no = rn
			rv.status = "Reversed"
			rv.original_award_reference = s.custom_award_reference
			rv.original_award_evidence_type = s.custom_award_evidence_type
			rv.original_awarded_by = s.custom_awarded_by
			rv.original_awarded_on = s.custom_awarded_on
			rv.original_frozen_revision_no = s.custom_frozen_revision_no or 0
			rv.original_frozen_total_cost = s.custom_frozen_total_cost or 0
			rv.original_frozen_total_selling = s.custom_frozen_total_selling or 0
			rv.original_frozen_margin_percent = s.custom_frozen_margin_percent or 0
			rv.reversal_reason = reason
			rv.acknowledged = 1
			rv.acknowledgement_text = "The Managing Director acknowledged that the award is reversed, that delivery release is stopped, that the original award event remains immutable in history, and that delivery already performed requires explicit operational review."
			rv.evidence_reference = evidence_ref
			rv.requested_by = req_by
			rv.requested_on = now
			rv.approved_by = me
			rv.approved_on = now
			rv.approver_authority = MD
			rv.delivery_release_state_at_reversal = rel_state
			rv.delivery_already_released = was_released
			rv.operational_review_required = was_released
			rv.operational_review_note = op_note
			rv.approval_state_at_reversal = appr_at
			rv.returned_to_state = returned_to
			rv.flags.dcs_api_write = 1
			# Created under the authority of this service only. Managing Director authority,
			# mandatory reason and mandatory acknowledgement are all enforced above. The DocType
			# therefore grants create to no role, so no user can ever author one directly.
			rv.insert(ignore_permissions=True)
			cond = raise_reversal_condition(dcs_name, "The customer award recorded on " + str(s.custom_awarded_on) + " was reversed by the Managing Director under " + str(rv.name) + ". Delivery release is stopped. This condition must be cleared only after the deal is re-awarded or formally closed.")
			# D2a Phase 2: snapshot the governed fields server side immediately before the write.
			D2A_FIELDS = ["custom_award_state", "custom_award_reversal_state", "custom_award_reversal_ref", "custom_award_reversal_count", "custom_award_reversed_by", "custom_award_reversed_on", "custom_award_reversal_reason", "custom_operational_review_state", "custom_delivery_release_state", "custom_approval_state"]
			d2a_before = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
			frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_award_state": "Not Awarded", "custom_award_reversal_state": "Reversed", "custom_award_reversal_ref": rv.name, "custom_award_reversal_count": (s.custom_award_reversal_count or 0) + 1, "custom_award_reversed_by": me, "custom_award_reversed_on": now, "custom_award_reversal_reason": reason, "custom_operational_review_state": op_state, "custom_delivery_release_state": new_rel, "custom_approval_state": returned_to}, update_modified=True)
			# D2a Phase 2: the governed write above has succeeded, so record the committed movement.
			d2a_after = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
			d2a_moved = dcs_audit_changes(D2A_FIELDS, d2a_before, d2a_after, "Deal Cost Sheet", dcs_name)
			d2a_anchor = frappe.db.get_value("Deal Cost Sheet", dcs_name, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
			result["governance_event"] = dcs_audit_event(dcs_name, "DCS_AWARD_REVERSED", "Reverse a recorded customer award under Managing Director authority", "dcs_award_reversal", reason, d2a_anchor.get("custom_dcs_revision_no") or 0, d2a_anchor.get("custom_revision_reference") or "", rv.name, d2a_moved)
			result["ok"] = 1
			result["reversal"] = rv.name
			result["condition"] = cond
			result["state"] = {"derived_award_state": "Reversed", "award_pointer_state": "Not Awarded", "original_award_reference_preserved": s.custom_award_reference, "original_awarded_on_preserved": str(s.custom_awarded_on), "frozen_baseline_preserved": 1, "delivery_release_state": new_rel, "operational_review_state": op_state, "operational_review_required": was_released, "approval_state": returned_to, "reversal_count": (s.custom_award_reversal_count or 0) + 1, "docstatus_unchanged": s.docstatus, "note": "Award reversed. The original award event is unchanged and remains visible in history. Delivery release is stopped. The deal has returned to a living commercial state for correction or re-award. A future re-award will create a new award event."}

frappe.response["message"] = result

# --- Native timeline + notification emit (go-live Day 2) ---
try:
    if result.get("ok"):
        tlname = frappe.form_dict.get("dcs")
        tlstate = result.get("state") or {}
        tltext = ""
        if result.get("mode") == "reverse":
            tltext = "Award reversed - reversal " + str(tlstate.get("reversal_count")) + " (" + str(result.get("reversal")) + ") - delivery " + str(tlstate.get("delivery_release_state"))
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
