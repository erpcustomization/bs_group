"""Award & Handover Workspace services.

* ``dcs_set_delivery_owner`` (write) - a named delivery owner is mandatory
  for every release, including a Managing Director override.
* ``dcs_handover_action``     (write) - Chase / Assign / Hold / Return / Clear /
  Accept Risk on one ``DCS Handover Condition``.
* ``dcs_delivery_release``    (write) - release the awarded deal to delivery,
  normally or with a Managing Director override.
* ``dcs_screen5``             (read)  - the commercial or technical projection
  of the workspace, technical narrative governed by NRC-1.

Ported from the production Server Scripts of the same names
(``bsgroup/dcs/server_script_export``). Business rules, refusal texts and
result shapes are unchanged; authority is derived from the session only.
"""

import frappe
from frappe.utils import now_datetime

from bsgroup.api.dcs._common import (
	CC, COMMERCIAL_ROLES, MARGIN_FLOOR, MD, NRC_UNAVAILABLE, TECHNICAL_ROLES, absf, audit_event,
	dcs_exists_and_open, emit_timeline, find_condition, get_user_roles, governed_endpoint, has_any,
	nrc_batch, nrc_entry_check, nrc_govern, open_blockers, r2, truthy_flag,
)
from bsgroup.dcs.governance import diff_changes, snapshot

RELEASED_STATES = ["Released", "Released with MD Override"]


def _release_state_after(sheet_name):
	"""Recompute Pending/Blocked from open blockers unless already released. Returns (old, new|None)."""
	blk = open_blockers(sheet_name)
	cur = frappe.db.get_value("Deal Cost Sheet", sheet_name, "custom_delivery_release_state")
	if cur in RELEASED_STATES:
		return cur, None, blk
	rel = "Blocked" if len(blk) > 0 else "Pending"
	frappe.db.set_value("Deal Cost Sheet", sheet_name, {"custom_delivery_release_state": rel}, update_modified=True)
	return cur, rel, blk


# ---------------------------------------------------------------------------
# dcs_set_delivery_owner
# ---------------------------------------------------------------------------
@governed_endpoint("dcs_set_delivery_owner", ptype="write")
def dcs_set_delivery_owner(args):
	result = {"ok": 0, "error": "", "state": {}}
	dcs_name = args.get("dcs")
	owner_user = args.get("delivery_owner")
	roles = get_user_roles()

	if not dcs_exists_and_open(dcs_name, result):
		return result
	if has_any(roles, COMMERCIAL_ROLES) == 0 and has_any(roles, TECHNICAL_ROLES) == 0:
		result["error"] = "You hold neither a commercial nor a technical role."
		return result
	if not owner_user:
		result["error"] = "delivery_owner is required. Delivery can never be released without a named owner."
		return result
	if not frappe.db.exists("User", owner_user):
		result["error"] = "User " + str(owner_user) + " does not exist. The delivery owner must be a real named user."
		return result

	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("write")
	if not s.custom_baseline_frozen:
		result["error"] = "No award has been recorded. There is nothing to hand over yet."
		return result

	prev_owner = s.custom_delivery_owner
	hc_ref = ""
	frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_delivery_owner": owner_user}, update_modified=True)

	c = find_condition(dcs_name, "delivery_owner")
	if c is not None and c.get("state") == "Open":
		d = frappe.get_doc("DCS Handover Condition", c.get("name"))
		d.state = "Cleared"
		d.cleared_by = frappe.session.user
		d.cleared_on = now_datetime()
		d.clearance_note = "Named delivery owner recorded as " + str(owner_user) + "."
		d.assigned_to = owner_user
		d.flags.dcs_api_write = 1
		d.save()
		hc_ref = c.get("name")

	cur, rel, blk = _release_state_after(dcs_name)
	if rel:
		result["state"] = {"delivery_owner": owner_user, "delivery_release_state": rel, "open_blockers": len(blk)}
	else:
		result["state"] = {"delivery_owner": owner_user, "delivery_release_state": cur}

	changes = [{"field": "custom_delivery_owner", "old": prev_owner, "new": owner_user}]
	if rel:
		changes.append({"field": "custom_delivery_release_state", "old": cur, "new": rel})
	result["governance_event"] = audit_event(
		dcs_name, "DCS_DELIVERY_OWNER_ASSIGNED", "Assign the delivery owner", "dcs_set_delivery_owner", "",
		s.custom_dcs_revision_no, s.custom_revision_reference, hc_ref, changes,
	)
	result["ok"] = 1
	return result


# ---------------------------------------------------------------------------
# dcs_handover_action
# ---------------------------------------------------------------------------
HC_FIELDS = [
	"state", "category", "original_category", "assigned_to", "hold_state", "last_action_note",
	"cleared_by", "cleared_on", "clearance_note", "accepted_by", "accepted_on", "acceptance_reason",
	"acknowledged", "exposure_amount", "exposure_note", "follow_up_date",
]
SHEET_RELEASE_FIELDS = ["custom_delivery_release_state"]
VALID_ACTIONS = ["Chase", "Assign", "Hold", "Return", "Clear", "Accept Risk"]


@governed_endpoint("dcs_handover_action", perm_doctype="DCS Handover Condition", ptype="write")
def dcs_handover_action(args):
	result = {"ok": 0, "error": "", "action": "", "condition": {}}

	cond_name = args.get("condition")
	action = args.get("action")
	note = args.get("note")
	assign_to = args.get("assign_to")
	ack = args.get("acknowledged")
	exposure = args.get("exposure_amount")
	exposure_note = args.get("exposure_note")
	follow_up = args.get("follow_up_date")

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

	roles = get_user_roles()
	is_md = 1 if MD in roles else 0
	is_cc = 1 if CC in roles else 0
	is_comm = has_any(roles, COMMERCIAL_ROLES)
	is_tech = has_any(roles, TECHNICAL_ROLES)

	if not cond_name:
		result["error"] = "condition is required."
		return result
	if action not in VALID_ACTIONS:
		result["error"] = "action must be one of Chase, Assign, Hold, Return, Clear, Accept Risk."
		return result
	if not frappe.db.exists("DCS Handover Condition", cond_name):
		result["error"] = "Handover condition " + str(cond_name) + " does not exist."
		return result
	sheet_of = frappe.db.get_value("DCS Handover Condition", cond_name, "dcs")
	if frappe.db.get_value("Deal Cost Sheet", sheet_of, "docstatus") == 2:
		result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
		return result
	if is_comm == 0 and is_tech == 0:
		result["error"] = "You hold neither a commercial nor a technical role. System Manager administration does not confer handover authority."
		return result

	c = frappe.get_doc("DCS Handover Condition", cond_name)
	c.check_permission("write")
	domain = c.domain
	now = now_datetime()
	me = frappe.session.user

	domain_ok = 0
	if domain == "Technical":
		if is_tech == 1:
			domain_ok = 1
	elif is_comm == 1:
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
	elif action == "Accept Risk" and not truthy_flag(ack):
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
	if result["error"]:
		return result

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

	sheet = c.dcs
	hc_before = snapshot("DCS Handover Condition", c.name, HC_FIELDS)
	sheet_before = snapshot("Deal Cost Sheet", sheet, SHEET_RELEASE_FIELDS)
	c.flags.dcs_api_write = 1
	c.save()
	# exposure_amount is permlevel 1 and no role holds L1 on DCS Handover Condition, so an
	# ORM save resets it. The governed service persists it via the trusted db.set_value channel;
	# Managing Director authority was enforced above.
	if action == "Accept Risk" and exposure:
		frappe.db.set_value("DCS Handover Condition", c.name, "exposure_amount", float(exposure), update_modified=False)
		c.exposure_amount = float(exposure)

	_cur, _rel, blk = _release_state_after(sheet)

	hc_after = snapshot("DCS Handover Condition", c.name, HC_FIELDS)
	sheet_after = snapshot("Deal Cost Sheet", sheet, SHEET_RELEASE_FIELDS)
	moved = diff_changes(HC_FIELDS, hc_before, hc_after, "DCS Handover Condition", c.name)
	moved += diff_changes(SHEET_RELEASE_FIELDS, sheet_before, sheet_after, "Deal Cost Sheet", sheet)
	code = "DCS_HANDOVER_" + str(action).upper().replace(" ", "_")
	anchor = frappe.db.get_value("Deal Cost Sheet", sheet, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
	result["governance_event"] = audit_event(
		sheet, code, "Handover condition action: " + str(action), "dcs_handover_action", note,
		anchor.get("custom_dcs_revision_no") or 0, anchor.get("custom_revision_reference") or "", c.name, moved,
	)
	result["ok"] = 1
	result["action"] = action
	result["condition"] = {
		"name": c.name, "title": c.condition_title, "category": c.category,
		"original_category": c.original_category, "domain": c.domain, "state": c.state,
		"assigned_to": c.assigned_to, "hold_state": c.hold_state, "accepted_by": c.accepted_by,
		"accepted_on": c.accepted_on, "acceptance_reason": c.acceptance_reason,
		"acknowledged": c.acknowledged, "exposure_amount": c.exposure_amount,
		"follow_up_date": c.follow_up_date,
	}
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
			result["condition"]["title"] = NRC_UNAVAILABLE
			result["condition"]["acceptance_reason"] = NRC_UNAVAILABLE
		# Remove the protected commercial keys outright rather than nulling them.
		result["condition"] = {
			k: v for k, v in result["condition"].items() if k not in ("exposure_amount", "exposure_note")
		}
	return result


# ---------------------------------------------------------------------------
# dcs_delivery_release
# ---------------------------------------------------------------------------
RELEASE_FIELDS = [
	"custom_delivery_release_state", "custom_delivery_released_by", "custom_delivery_released_on",
	"custom_delivery_override", "custom_delivery_override_reason", "custom_delivery_release_note",
]


def release_drift(s):
	"""Post-award commercial drift check shared by the release service and the screen-5 readiness note."""
	lv_rev = int(s.custom_dcs_revision_no or 0)
	fz_sell = float(s.custom_frozen_total_selling or 0)
	fz_cost = float(s.custom_frozen_total_cost or 0)
	lv_sell = float(s.custom_working_total_selling or 0)
	lv_cost = float(s.custom_working_total_cost or 0)
	if lv_rev > 0 and (absf(lv_sell - fz_sell) > 0.005 or absf(lv_cost - fz_cost) > 0.005):
		return "living"
	if (
		s.custom_po_recon_state == "Reconciled" and s.custom_po_scope_revision and s.custom_revision_reference
		and s.custom_po_scope_revision != s.custom_revision_reference
	):
		return "po_scope"
	if s.custom_approval_required and s.custom_approval_required != "None" and s.custom_approval_state != "Approved":
		return "approval"
	return ""


def _drift_text(kind, s, with_values):
	if kind == "living":
		if with_values:
			return (
				"The living commercial position (cost " + str(float(s.custom_working_total_cost or 0)) + ", selling "
				+ str(float(s.custom_working_total_selling or 0)) + ") no longer matches the frozen baseline that was awarded (cost "
				+ str(float(s.custom_frozen_total_cost or 0)) + ", selling " + str(float(s.custom_frozen_total_selling or 0))
				+ "). Delivery cannot be released against a commercial position that was never awarded. Reverse the award and re-award on the current position, or return the living position to the awarded baseline."
			)
		return "The living commercial position no longer matches the frozen baseline that was awarded. Delivery cannot be released against a commercial position that was never awarded. Reverse the award and re-award on the current position, or return the living position to the awarded baseline."
	if kind == "po_scope":
		return (
			"The customer PO was reconciled against " + str(s.custom_po_scope_revision) + " but the current commercial position is "
			+ str(s.custom_revision_reference) + ". A value match against a superseded scope is never treated as reconciled. Re-reconcile the customer PO against the current revision before releasing."
		)
	if kind == "approval":
		return (
			"A concession on this deal is awaiting " + str(s.custom_approval_required) + " approval (current approval state "
			+ str(s.custom_approval_state) + "). Delivery cannot be released while an unapproved commercial concession is outstanding."
		)
	return ""


@governed_endpoint("dcs_delivery_release", ptype="write")
def dcs_delivery_release(args):
	result = {"ok": 0, "error": "", "state": {}, "accepted_risks": []}

	dcs_name = args.get("dcs")
	override = args.get("override")
	reason = args.get("reason")
	ack = args.get("acknowledged")
	note = args.get("note")
	follow_up = args.get("follow_up_date")
	exposure_note = args.get("exposure_note")

	# NRC-1: override / exposure narrative is readable by technical and operations roles,
	# so a likely commercial disclosure is refused before write.
	nrc_chk = nrc_entry_check(["override reason", "exposure note", "action note"], [reason, exposure_note, note])
	nrc_eval = "clean"
	if nrc_chk["block"] != "":
		nrc_eval = "high"
	elif nrc_chk["warn"] != "":
		nrc_eval = "warn"
	result["narrative_guard_eval"] = nrc_eval
	result["narrative_contract"] = "NRC-1"

	is_override = 1 if truthy_flag(override) else 0
	is_ack = 1 if truthy_flag(ack) else 0

	roles = get_user_roles()
	is_md = 1 if MD in roles else 0
	is_cc = 1 if CC in roles else 0

	if not dcs_exists_and_open(dcs_name, result):
		return result
	if is_md == 0 and is_cc == 0:
		result["error"] = "Releasing to delivery is a Commercial Controller or Managing Director action."
		return result
	if nrc_chk["block"] != "":
		result["error"] = nrc_chk["block"]
		result["narrative_guard"] = "blocked"
		return result

	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("write")
	blk = open_blockers(dcs_name)
	names = [str(b.get("condition_title")) + " (" + str(b.get("domain")) + ")" for b in blk]
	drift = _drift_text(release_drift(s), s, with_values=True)

	if s.custom_award_state != "Awarded":
		result["error"] = "No customer award has been recorded. Delivery cannot be released before an award is recorded and the commercial baseline is frozen."
	elif not s.custom_baseline_frozen:
		result["error"] = "The commercial baseline is not frozen. Delivery cannot be released."
	elif s.custom_delivery_release_state in RELEASED_STATES:
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
	if result["error"]:
		return result

	now = now_datetime()
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
			accepted.append({
				"condition": d.name, "title": d.condition_title, "original_category": d.original_category,
				"domain": d.domain, "state": d.state, "accepted_by": me, "accepted_on": now, "reason": reason,
				"owner": d.assigned_to, "follow_up_date": follow_up,
			})

	new_state = "Released with MD Override" if is_override == 1 else "Released"

	before = snapshot("Deal Cost Sheet", dcs_name, RELEASE_FIELDS)
	frappe.db.set_value(
		"Deal Cost Sheet", dcs_name,
		{
			"custom_delivery_release_state": new_state, "custom_delivery_released_by": me,
			"custom_delivery_released_on": now, "custom_delivery_override": is_override,
			"custom_delivery_override_reason": reason, "custom_delivery_release_note": note,
		},
		update_modified=True,
	)
	after = snapshot("Deal Cost Sheet", dcs_name, RELEASE_FIELDS)
	moved = diff_changes(RELEASE_FIELDS, before, after, "Deal Cost Sheet", dcs_name)
	code = "DCS_DELIVERY_RELEASED_MD_OVERRIDE" if is_override == 1 else "DCS_DELIVERY_RELEASED"
	anchor = frappe.db.get_value("Deal Cost Sheet", dcs_name, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
	result["governance_event"] = audit_event(
		dcs_name, code, "Release the awarded deal to delivery", "dcs_delivery_release", reason,
		anchor.get("custom_dcs_revision_no") or 0, anchor.get("custom_revision_reference") or "", "", moved,
	)
	result["ok"] = 1
	result["accepted_risks"] = accepted
	result["state"] = {
		"delivery_release_state": new_state, "delivery_owner": s.custom_delivery_owner, "released_by": me,
		"override_used": is_override, "override_reason": reason, "accepted_risk_count": len(accepted),
		"award_state": s.custom_award_state, "baseline_frozen": s.custom_baseline_frozen,
		"docstatus_unchanged": s.docstatus,
		"note": "Customer Award, Commercial Baseline Frozen and Delivery Release remain three separate states. Accepted risks retain their original blocker and are never marked Clear.",
	}

	if new_state == "Released":
		emit_timeline(dcs_name, "Delivery released to " + str(s.custom_delivery_owner))
	else:
		emit_timeline(
			dcs_name,
			"Delivery released with Managing Director override to " + str(s.custom_delivery_owner)
			+ " - accepted risks: " + str(len(accepted))
			+ " - override reason recorded on the Deal Cost Sheet for authorised commercial roles",
		)
	return result


# ---------------------------------------------------------------------------
# dcs_screen5
# ---------------------------------------------------------------------------
COND_FIELDS = [
	"name", "condition_no", "condition_title", "category", "original_category", "domain", "state", "detail",
	"assigned_to", "hold_state", "last_action_note", "raised_by", "raised_on", "cleared_by", "cleared_on",
	"clearance_note", "accepted_by", "accepted_on", "acceptance_reason", "acknowledged", "exposure_amount",
	"exposure_note", "follow_up_date",
]
TECH_NARRATIVE_FIELDS = ["condition_title", "detail", "last_action_note", "clearance_note", "acceptance_reason"]


def _tech_safe(c):
	out = {k: c.get(k) for k in COND_FIELDS if k not in ("exposure_amount", "exposure_note")}
	out["exposure_withheld"] = "Commercial exposure is withheld from the technical projection."
	return out


@governed_endpoint("dcs_screen5", ptype="read", idempotent=False)
def dcs_screen5(args):
	result = {"ok": 0, "error": "", "projection": "denied", "user": frappe.session.user}

	dcs_name = args.get("dcs")
	want = args.get("projection")
	roles = get_user_roles()
	is_comm = has_any(roles, COMMERCIAL_ROLES)
	is_tech = has_any(roles, TECHNICAL_ROLES)
	is_md = 1 if MD in roles else 0
	is_cc = 1 if CC in roles else 0

	# a caller may explicitly request the technical projection, which is strictly LESS;
	# a caller can never request more than their roles allow.
	if want == "technical":
		is_comm = 0

	if not dcs_name:
		result["error"] = "dcs is required."
		return result
	if not frappe.db.exists("Deal Cost Sheet", dcs_name):
		result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
		return result
	if is_comm == 0 and is_tech == 0:
		result["error"] = "You hold neither a commercial nor a technical role. System Manager administration does not confer access to the Award and Handover Workspace."
		return result

	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("read")
	conds = frappe.get_all("DCS Handover Condition", filters={"dcs": dcs_name}, fields=COND_FIELDS, order_by="condition_no asc")

	blockers, watch, risks = [], [], []
	for c in conds:
		if c.get("state") == "Accepted Risk":
			risks.append(c)
		elif c.get("category") == "Blocker":
			blockers.append(c)
		else:
			watch.append(c)
	open_blk = sum(1 for b in blockers if b.get("state") == "Open")

	# --- release readiness (same rule the delivery release service enforces) ---
	lv_rev = int(s.custom_dcs_revision_no or 0)
	lv_sell = float(s.custom_working_total_selling or 0)
	eff_sell = lv_sell if lv_rev > 0 else float(s.total_selling or 0)
	eff_margin = float(s.custom_working_margin_percent or 0) if lv_rev > 0 else float(s.margin_percent or 0)
	below_floor = 0
	if s.custom_margin_gate == "Blocked":
		below_floor = 1
	elif eff_sell > 0 and eff_margin < MARGIN_FLOOR:
		below_floor = 1
	rr_note = _drift_text(release_drift(s), s, with_values=False)
	if rr_note == "" and below_floor > 0:
		rr_note = "Not commercially aligned — margin below floor"
	rr_ready = 1 if rr_note == "" else 0
	result["release_readiness"] = {
		"commercially_aligned": rr_ready, "note": rr_note,
		"basis": "Frozen baseline, reconciled customer PO and living position must still agree at the moment of release.",
	}
	result["states"] = {
		"customer_award": s.custom_award_state or "Not Awarded",
		"commercial_baseline_frozen": s.custom_baseline_frozen or 0,
		"delivery_release": s.custom_delivery_release_state or "Not Applicable",
		"separation_note": "These are three separate states. Recording an award never releases to delivery.",
		"delivery_owner": s.custom_delivery_owner, "awarded_on": s.custom_awarded_on, "frozen_on": s.custom_frozen_on,
		"released_on": s.custom_delivery_released_on, "override_used": s.custom_delivery_override or 0,
		"award_sequence_no": s.custom_award_sequence_no or 0,
		"award_reversal_state": s.custom_award_reversal_state or "",
		"award_reversal_count": s.custom_award_reversal_count or 0,
		"award_reversal_ref": s.custom_award_reversal_ref,
	}
	result["legacy"] = {
		"workflow_state": s.workflow_state, "label": "LEGACY / INACTIVE",
		"note": "This value comes from the superseded Deal Cost Sheet workflow, which is inactive. It is not authoritative. The living DCS state above is authoritative.",
	}
	result["deal"] = {
		"name": s.name, "customer": s.customer, "subject": s.subject, "opportunity": s.opportunity,
		"deal_owner": s.deal_owner, "docstatus": s.docstatus, "revision_reference": s.custom_revision_reference,
	}

	if is_comm == 1:
		result["projection"] = "commercial"
		result["authority"] = {
			"can_record_award": 1, "can_reconcile_po": 1, "can_release": is_cc + is_md, "can_override": is_md,
			"can_clear_technical": 0, "can_clear_commercial": 1,
			"role_label": "Managing Director" if is_md == 1 else ("Commercial Controller" if is_cc == 1 else "Commercial"),
			"note": "Commercial users cannot close technical gates.",
		}
		result["award"] = {
			"state": s.custom_award_state or "Not Awarded", "reference": s.custom_award_reference,
			"evidence_type": s.custom_award_evidence_type, "notes": s.custom_award_notes,
			"recorded_by": s.custom_awarded_by, "recorded_on": s.custom_awarded_on,
		}
		result["frozen_baseline"] = {
			"frozen": s.custom_baseline_frozen or 0, "revision_no": s.custom_frozen_revision_no or 0,
			"total_cost": r2(s.custom_frozen_total_cost), "total_selling": r2(s.custom_frozen_total_selling),
			"gp": r2((s.custom_frozen_total_selling or 0) - (s.custom_frozen_total_cost or 0)),
			"margin_percent": s.custom_frozen_margin_percent or 0, "frozen_by": s.custom_frozen_by,
			"frozen_on": s.custom_frozen_on, "currency": s.currency,
			"note": "The frozen baseline is the authorised commercial position at the moment of award. It does not move with later negotiation.",
		}
		result["living"] = {
			"revision_no": s.custom_dcs_revision_no or 0, "total_cost": r2(s.custom_working_total_cost),
			"total_selling": r2(s.custom_working_total_selling), "margin_percent": s.custom_working_margin_percent or 0,
			"approval_state": s.custom_approval_state, "approval_required": s.custom_approval_required,
			"margin_gate": s.custom_margin_gate,
		}
		result["po"] = {
			"reference": s.custom_po_reference, "value": r2(s.custom_po_value), "scope_revision": s.custom_po_scope_revision,
			"payment_terms": s.custom_po_payment_terms, "value_check": s.custom_po_value_match or "Not Checked",
			"scope_check": s.custom_po_scope_match or "Not Checked", "terms_check": s.custom_po_terms_match or "Not Checked",
			"reconciliation_state": s.custom_po_recon_state or "Not Started", "reconciled_by": s.custom_po_recon_by,
			"reconciled_on": s.custom_po_recon_on,
			"basis": "PO value, PO scope or revision and PO payment terms are reconciled independently. A value match against a superseded or different scope is a hard blocker and is never treated as reconciled.",
		}
		exposure = (s.custom_frozen_total_cost or 0) if s.custom_baseline_frozen else 0.0
		result["supplier_exposure"] = {
			"amount": r2(exposure), "currency": s.currency, "label": "Cost exposure not yet committed",
			"note": "This is the buying cost of the awarded position. It is a cost exposure not yet committed. It is not a realised loss and must never be reported as one.",
		}
		result["conditions"] = {"blockers": blockers, "watch_items": watch, "accepted_risks": risks, "open_blockers": open_blk}
		result["ok"] = 1
		return result

	# ---- technical projection: explicit safe field list, NRC-1 governed narrative ----
	result["projection"] = "technical"
	result["authority"] = {
		"can_record_award": 0, "can_reconcile_po": 0, "can_release": 0, "can_override": 0,
		"can_clear_technical": 1, "can_clear_commercial": 0, "role_label": "Technical",
		"note": "Technical users cannot close commercial or finance gates. No commercial value is returned to this projection.",
	}
	lines = frappe.get_all(
		"Deal Cost Item", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"},
		fields=["idx", "item_code", "item_name", "customer_item_name", "brand", "item_category", "qty", "description"],
		order_by="idx asc",
	)
	res_rows = frappe.get_all(
		"Deal Cost Resource", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"},
		fields=["idx", "resource_type", "role", "no_of_persons", "no_of_days", "hours", "linked_project", "remarks"],
		order_by="idx asc",
	)
	tech_conds, mine = [], []
	for c in conds:
		if c.get("domain") == "Technical":
			tech_conds.append(_tech_safe(c))
		if c.get("assigned_to") == frappe.session.user:
			mine.append({
				"name": c.get("name"), "title": c.get("condition_title"), "domain": c.get("domain"),
				"category": c.get("category"), "state": c.get("state"),
				"can_clear": 1 if c.get("domain") == "Technical" else 0,
			})

	payload = []
	for c in tech_conds:
		for f in TECH_NARRATIVE_FIELDS:
			payload.append(c.get(f))
	for mm in mine:
		payload.append(mm.get("title"))
	for ln in lines:
		payload.append(ln.get("description"))
		payload.append(ln.get("customer_item_name"))
	for rr in res_rows:
		payload.append(rr.get("remarks"))
	nrc_out = nrc_govern(payload)
	if nrc_out["ok"] == 1:
		kk = 0
		for c in tech_conds:
			for f in TECH_NARRATIVE_FIELDS:
				c[f] = nrc_out["texts"][kk]
				kk += 1
		for mm in mine:
			mm["title"] = nrc_out["texts"][kk]
			kk += 1
		for ln in lines:
			ln["description"] = nrc_out["texts"][kk]
			kk += 1
			ln["customer_item_name"] = nrc_out["texts"][kk]
			kk += 1
		for rr in res_rows:
			rr["remarks"] = nrc_out["texts"][kk]
			kk += 1
	else:
		for c in tech_conds:
			for f in TECH_NARRATIVE_FIELDS:
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
	result["narrative_governance"] = {
		"contract": "NRC-1", "delegated": nrc_out["ok"], "cells": len(payload),
		"redacted": nrc_out.get("redacted") or 0,
		"note": nrc_out.get("reason") or "Operational narrative is governed by contract NRC-1.",
	}
	result["awarded_scope"] = {
		"award_state": s.custom_award_state or "Not Awarded",
		"released": s.custom_delivery_release_state or "Not Applicable", "lines": lines,
		"approved_quantities_basis": "Quantities are taken from the awarded Deal Cost Sheet lines at the frozen revision. No rate, amount, margin or gross profit is returned to a technical user.",
		"resources": res_rows,
	}
	result["delivery_requirements"] = {
		"delivery_owner": s.custom_delivery_owner, "customer": s.customer, "subject": s.subject,
		"award_reference": s.custom_award_reference,
		"release_state": s.custom_delivery_release_state or "Not Applicable",
		"note": "Work may only start once Delivery Release shows Released or Released with MD Override.",
	}
	result["technical_conditions"] = tech_conds
	result["my_actions"] = mine
	result["technical_dependencies"] = res_rows
	result["unavailable"] = [
		{"key": "site_readiness", "label": "Site readiness", "reason": "No site readiness field exists on the Deal Cost Sheet or on any linked record. Not fabricated."},
		{"key": "drawings_submittals", "label": "Drawings and submittal status", "reason": "No drawing or submittal register exists on this instance. Not fabricated."},
		{"key": "models_specs", "label": "Models and specifications", "reason": "Item code, brand and line description are returned where present. There is no separate model or specification register on Deal Cost Item."},
	]
	result["ok"] = 1
	return result
