"""Award services: ``dcs_record_award``, ``dcs_award_reversal`` and ``dcs_po_reconcile``.

Ported from the production Server Scripts of the same names. Customer Award,
Commercial Baseline Frozen and Delivery Release are three separate states;
recording an award never releases delivery. The award event is immutable:
a reversal writes a separate ``DCS Award Reversal`` record and only moves
service-owned state.
"""

import frappe
from frappe.utils import now_datetime

from bsgroup.api.dcs._common import (
	COMMERCIAL_ROLES, MD, absf, audit_event, clear_auto, dcs_exists_and_open, diff_changes, emit_timeline,
	get_user_roles, governed_endpoint, has_any, next_condition_no, nrc_entry_check, open_blockers,
	raise_condition, snapshot,
)


# ---------------------------------------------------------------------------
# dcs_record_award
# ---------------------------------------------------------------------------
AWARD_FIELDS = [
	"custom_award_state", "custom_award_reference", "custom_award_evidence_type", "custom_award_notes",
	"custom_awarded_by", "custom_awarded_on", "custom_baseline_frozen", "custom_frozen_revision_no",
	"custom_frozen_total_cost", "custom_frozen_total_selling", "custom_frozen_margin_percent", "custom_frozen_by",
	"custom_frozen_on", "custom_delivery_release_state", "custom_po_recon_state", "custom_award_sequence_no",
	"custom_award_reversal_state",
]
VALID_EVIDENCE = ["Customer PO", "Letter of Award", "Email Confirmation", "Verbal - Not Evidenced", "Not Provided"]


def clear_reversal_block(sheet_name, new_ref):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "source_key": "award_reversed", "state": "Open"}, fields=["name"])
	done = []
	for r in rows:
		c = frappe.get_doc("DCS Handover Condition", r.get("name"))
		c.state = "Cleared"
		c.cleared_by = frappe.session.user
		c.cleared_on = now_datetime()
		c.clearance_note = "Cleared automatically because the deal has been re-awarded under a new award event with reference " + str(new_ref) + ". The reversed award remains visible in history."
		c.flags.dcs_api_write = 1
		c.save()
		done.append(c.name)
	return done


NOT_A_COMMERCIAL_ACTOR = (
	"Recording a customer award is a commercial action. Technical roles and System Manager "
	"administration cannot record an award."
)


@governed_endpoint("dcs_record_award", ptype="write", denied_message=NOT_A_COMMERCIAL_ACTOR)
def dcs_record_award(args):
	result = {"ok": 0, "error": "", "state": {}, "conditions_raised": []}

	dcs_name = args.get("dcs")
	award_ref = args.get("award_reference")
	evidence = args.get("evidence_type")
	notes = args.get("notes")

	nrc_chk = nrc_entry_check(["award note"], [notes], scope="Handover")
	result["narrative_guard_eval"] = "high" if nrc_chk["block"] else ("warn" if nrc_chk["warn"] else "clean")
	result["narrative_guard_delegated"] = nrc_chk["delegated"]
	result["narrative_guard_warning"] = nrc_chk["warn"]

	roles = get_user_roles()

	if not dcs_exists_and_open(dcs_name, result):
		pass
	elif has_any(roles, COMMERCIAL_ROLES) == 0:
		result["error"] = NOT_A_COMMERCIAL_ACTOR
	elif evidence not in VALID_EVIDENCE:
		result["error"] = "evidence_type must be one of Customer PO, Letter of Award, Email Confirmation, Verbal - Not Evidenced, Not Provided."
	elif nrc_chk["block"] != "":
		result["error"] = nrc_chk["block"]
	else:
		s = frappe.get_doc("Deal Cost Sheet", dcs_name)
		s.check_permission("write")
		req = s.custom_approval_required
		appr = s.custom_approval_state
		authorised = 1 if (req == "None" or appr == "Approved") else 0

		if s.custom_award_state == "Awarded":
			result["error"] = "An award is already recorded on this Deal Cost Sheet on " + str(s.custom_awarded_on) + ". The commercial baseline is frozen and an award event cannot be recorded twice."
		elif (s.custom_dcs_revision_no or 0) < 1:
			result["error"] = "The living commercial position has not been initialised. There is nothing to freeze."
		elif req == "Blocked":
			result["error"] = "The current commercial position is above the 26% concession ceiling and was never authorised. An award cannot be recorded against an unauthorised position."
		elif authorised == 0:
			result["error"] = "The current position requires Managing Director approval and is in state '" + str(appr) + "'. Record the award only against an authorised commercial position."
		else:
			now = now_datetime()
			me = frappe.session.user
			raised = []
			frozen_cost = s.custom_working_total_cost or 0
			frozen_sell = s.custom_working_total_selling or 0
			frozen_margin = s.custom_working_margin_percent or 0
			frozen_rev = s.custom_dcs_revision_no or 0

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
			release_state = "Blocked" if len(blk) > 0 else "Pending"
			aseq = (s.custom_award_sequence_no or 0) + 1
			cleared_rev_block = clear_reversal_block(dcs_name, award_ref)

			before = snapshot("Deal Cost Sheet", dcs_name, AWARD_FIELDS)
			frappe.db.set_value(
				"Deal Cost Sheet", dcs_name,
				{
					"custom_award_state": "Awarded", "custom_award_reference": award_ref, "custom_award_evidence_type": evidence,
					"custom_award_notes": notes, "custom_awarded_by": me, "custom_awarded_on": now, "custom_baseline_frozen": 1,
					"custom_frozen_revision_no": frozen_rev, "custom_frozen_total_cost": frozen_cost,
					"custom_frozen_total_selling": frozen_sell, "custom_frozen_margin_percent": frozen_margin,
					"custom_frozen_by": me, "custom_frozen_on": now, "custom_delivery_release_state": release_state,
					"custom_po_recon_state": "Not Started", "custom_award_sequence_no": aseq, "custom_award_reversal_state": "",
				},
				update_modified=True,
			)
			after = snapshot("Deal Cost Sheet", dcs_name, AWARD_FIELDS)
			moved = diff_changes(AWARD_FIELDS, before, after, "Deal Cost Sheet", dcs_name)
			anchor = frappe.db.get_value("Deal Cost Sheet", dcs_name, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
			result["governance_event"] = audit_event(
				dcs_name, "DCS_AWARD_RECORDED", "Record a customer award against the frozen commercial baseline", "dcs_record_award",
				notes, anchor.get("custom_dcs_revision_no") or 0, anchor.get("custom_revision_reference") or "", award_ref, moved,
			)
			result["ok"] = 1
			result["conditions_raised"] = raised
			result["state"] = {
				"award_state": "Awarded", "award_sequence_no": aseq, "reversal_block_cleared": cleared_rev_block,
				"award_reference": award_ref, "evidence_type": evidence, "baseline_frozen": 1, "frozen_revision_no": frozen_rev,
				"frozen_total_cost": frozen_cost, "frozen_total_selling": frozen_sell, "frozen_margin_percent": frozen_margin,
				"delivery_release_state": release_state, "open_blockers": len(blk), "docstatus_unchanged": s.docstatus,
				"note": "Award recorded and commercial baseline frozen. Delivery has NOT been released. Delivery Release is a separate state and is currently " + release_state + ".",
			}

	if result.get("ok"):
		st_ = result.get("state") or {}
		emit_timeline(dcs_name, "Award recorded - reference " + str(st_.get("award_reference")) + " (" + str(st_.get("evidence_type")) + ") - baseline frozen at revision " + str(st_.get("frozen_revision_no")))
	return result


# ---------------------------------------------------------------------------
# dcs_award_reversal
# ---------------------------------------------------------------------------
REVERSAL_FIELDS = [
	"custom_award_state", "custom_award_reversal_state", "custom_award_reversal_ref", "custom_award_reversal_count",
	"custom_award_reversed_by", "custom_award_reversed_on", "custom_award_reversal_reason",
	"custom_operational_review_state", "custom_delivery_release_state", "custom_approval_state",
]


def next_reversal_no(sheet_name):
	rows = frappe.get_all("DCS Award Reversal", filters={"dcs": sheet_name}, fields=["reversal_no"], order_by="reversal_no desc", limit_page_length=1)
	n = 0
	for r in rows:
		n = r.get("reversal_no") or 0
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
	c.raised_on = now_datetime()
	c.auto_generated = 1
	c.source_key = "award_reversed"
	c.flags.dcs_api_write = 1
	c.insert(ignore_permissions=True)
	return c.name


@governed_endpoint("dcs_award_reversal", ptype="write")
def dcs_award_reversal(args):
	result = {"ok": 0, "error": "", "user": frappe.session.user, "authority": "", "mode": "", "state": {}, "reversal": "", "condition": ""}

	dcs_name = args.get("dcs")
	reason = (args.get("reason") or "").strip()
	ack = str(args.get("acknowledge") or "").strip().upper()
	evidence_ref = args.get("evidence_reference") or ""
	requested_by = args.get("requested_by") or ""
	mode = args.get("mode") or "check"
	ack_ok = 1 if ack in ("1", "YES", "TRUE") else 0

	roles = get_user_roles()
	is_md = 1 if MD in roles else 0
	if is_md:
		result["authority"] = MD
	result["mode"] = mode

	if not dcs_name:
		result["error"] = "dcs is required."
	elif not reason:
		result["error"] = "A reversal reason is mandatory. An award is never reversed without a stated commercial reason recorded against the reversal."
	elif ack_ok == 0:
		result["error"] = "Acknowledgement is mandatory. The Managing Director must acknowledge that delivery release is stopped, that the original award event remains immutable in history, and that delivery already performed is not rolled back automatically."
	elif not dcs_exists_and_open(dcs_name, result):
		pass
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
			now = now_datetime()
			me = frappe.session.user
			rel_state = s.custom_delivery_release_state or "Not Applicable"
			was_released = 1 if rel_state in ("Released", "Released with MD Override") else 0
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
				result["state"] = {
					"preview": 1, "award_reference": s.custom_award_reference, "awarded_on": str(s.custom_awarded_on),
					"delivery_release_state_now": rel_state, "delivery_release_state_after": new_rel, "operational_review_after": op_state,
					"approval_state_now": appr_at, "approval_state_after": returned_to,
					"note": "Preview only. Nothing has been written. Call again with mode=reverse to record the reversal.",
				}
			else:
				s.check_permission("write")
				req_by = me
				if requested_by and frappe.db.exists("User", requested_by):
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
				# Created under the authority of this service only (MD authority, mandatory
				# reason and acknowledgement enforced above). No role holds `create`.
				rv.insert(ignore_permissions=True)
				cond = raise_reversal_condition(dcs_name, "The customer award recorded on " + str(s.custom_awarded_on) + " was reversed by the Managing Director under " + str(rv.name) + ". Delivery release is stopped. This condition must be cleared only after the deal is re-awarded or formally closed.")
				before = snapshot("Deal Cost Sheet", dcs_name, REVERSAL_FIELDS)
				frappe.db.set_value(
					"Deal Cost Sheet", dcs_name,
					{
						"custom_award_state": "Not Awarded", "custom_award_reversal_state": "Reversed", "custom_award_reversal_ref": rv.name,
						"custom_award_reversal_count": (s.custom_award_reversal_count or 0) + 1, "custom_award_reversed_by": me,
						"custom_award_reversed_on": now, "custom_award_reversal_reason": reason, "custom_operational_review_state": op_state,
						"custom_delivery_release_state": new_rel, "custom_approval_state": returned_to,
					},
					update_modified=True,
				)
				after = snapshot("Deal Cost Sheet", dcs_name, REVERSAL_FIELDS)
				moved = diff_changes(REVERSAL_FIELDS, before, after, "Deal Cost Sheet", dcs_name)
				anchor = frappe.db.get_value("Deal Cost Sheet", dcs_name, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
				result["governance_event"] = audit_event(
					dcs_name, "DCS_AWARD_REVERSED", "Reverse a recorded customer award under Managing Director authority", "dcs_award_reversal",
					reason, anchor.get("custom_dcs_revision_no") or 0, anchor.get("custom_revision_reference") or "", rv.name, moved,
				)
				result["ok"] = 1
				result["reversal"] = rv.name
				result["condition"] = cond
				result["state"] = {
					"derived_award_state": "Reversed", "award_pointer_state": "Not Awarded",
					"original_award_reference_preserved": s.custom_award_reference, "original_awarded_on_preserved": str(s.custom_awarded_on),
					"frozen_baseline_preserved": 1, "delivery_release_state": new_rel, "operational_review_state": op_state,
					"operational_review_required": was_released, "approval_state": returned_to,
					"reversal_count": (s.custom_award_reversal_count or 0) + 1, "docstatus_unchanged": s.docstatus,
					"note": "Award reversed. The original award event is unchanged and remains visible in history. Delivery release is stopped. The deal has returned to a living commercial state for correction or re-award. A future re-award will create a new award event.",
				}

	if result.get("ok") and result.get("mode") == "reverse":
		st_ = result.get("state") or {}
		emit_timeline(dcs_name, "Award reversed - reversal " + str(st_.get("reversal_count")) + " (" + str(result.get("reversal")) + ") - delivery " + str(st_.get("delivery_release_state")))
	return result


# ---------------------------------------------------------------------------
# dcs_po_reconcile
# ---------------------------------------------------------------------------
PO_FIELDS = [
	"custom_po_reference", "custom_po_value", "custom_po_scope_revision", "custom_po_payment_terms", "custom_po_value_match",
	"custom_po_scope_match", "custom_po_terms_match", "custom_po_recon_state", "custom_po_recon_by", "custom_po_recon_on",
	"custom_delivery_release_state",
]


@governed_endpoint("dcs_po_reconcile", ptype="write")
def dcs_po_reconcile(args):
	result = {"ok": 0, "error": "", "checks": {}, "state": {}, "hard_blocker": 0}

	dcs_name = args.get("dcs")
	po_ref = args.get("po_reference")
	po_val_raw = args.get("po_value")
	po_scope = args.get("po_scope_revision")
	po_terms = args.get("po_payment_terms")
	terms_ok = args.get("payment_terms_accepted")

	nrc_chk = nrc_entry_check(["PO payment terms", "PO scope revision"], [po_terms, po_scope])
	result["narrative_contract"] = "NRC-1"
	if nrc_chk["block"] != "":
		result["narrative_warning"] = "The PO payment terms contain a commercial figure. This is accepted for the commercial record, but operations, technical and project roles will see the figure withheld in the Handover Condition Register and in the operational handover document."
	elif nrc_chk["warn"] != "":
		result["narrative_warning"] = nrc_chk["warn"]

	roles = get_user_roles()

	if not dcs_exists_and_open(dcs_name, result):
		pass
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

			v_state = "Match" if absf(po_val - frozen_sell) <= 0.01 else "Mismatch"

			cited = str(po_scope).strip()
			s_state = "Mismatch - Different Scope"
			if cited == str(frozen_ref):
				s_state = "Match"
			else:
				known = frappe.get_all("DCS Revision", filters={"dcs": dcs_name, "name": cited}, fields=["revision_no"], limit_page_length=1)
				for k in known:
					if (k.get("revision_no") or 0) < frozen_no:
						s_state = "Mismatch - Superseded"

			t_state = "Not Checked"
			if terms_ok in (1, "1", "true", True):
				t_state = "Accepted"
			elif po_terms:
				t_state = "Mismatch"

			all_ok = 1 if (v_state == "Match" and s_state == "Match" and t_state == "Accepted") else 0
			recon = "Reconciled" if all_ok == 1 else "Mismatch"

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

			before = snapshot("Deal Cost Sheet", dcs_name, PO_FIELDS)
			frappe.db.set_value(
				"Deal Cost Sheet", dcs_name,
				{
					"custom_po_reference": po_ref, "custom_po_value": po_val, "custom_po_scope_revision": cited,
					"custom_po_payment_terms": po_terms, "custom_po_value_match": v_state, "custom_po_scope_match": s_state,
					"custom_po_terms_match": t_state, "custom_po_recon_state": recon, "custom_po_recon_by": frappe.session.user,
					"custom_po_recon_on": now_datetime(),
				},
				update_modified=True,
			)
			blk = open_blockers(dcs_name)
			rel = "Blocked" if len(blk) > 0 else "Pending"
			if s.custom_delivery_release_state not in ["Released", "Released with MD Override"]:
				frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_delivery_release_state": rel}, update_modified=True)
			after = snapshot("Deal Cost Sheet", dcs_name, PO_FIELDS)
			moved = diff_changes(PO_FIELDS, before, after, "Deal Cost Sheet", dcs_name)
			anchor = frappe.db.get_value("Deal Cost Sheet", dcs_name, ["custom_dcs_revision_no", "custom_revision_reference"], as_dict=True) or {}
			result["governance_event"] = audit_event(
				dcs_name, "DCS_PO_RECONCILED", "Reconcile the customer purchase order against the frozen commercial baseline", "dcs_po_reconcile",
				"", anchor.get("custom_dcs_revision_no") or 0, anchor.get("custom_revision_reference") or "", po_ref, moved,
			)
			result["ok"] = 1
			result["hard_blocker"] = hard
			result["checks"] = {
				"value": {"state": v_state, "po_value": po_val, "frozen_selling": frozen_sell, "basis": "Reconciled independently of scope and terms."},
				"scope": {"state": s_state, "po_cites": cited, "frozen_revision": frozen_ref, "basis": "Reconciled independently of value. A value match with a superseded or different scope is a hard blocker."},
				"payment_terms": {"state": t_state, "terms": po_terms, "basis": "Reconciled independently of value and scope."},
			}
			result["state"] = {"po_reconciliation_state": recon, "delivery_release_state": rel, "open_blockers": len(blk), "docstatus_unchanged": s.docstatus}

	if result.get("ok"):
		st_ = result.get("state") or {}
		tlpo = st_.get("po_reconciliation_state")
		if tlpo and tlpo != "Reconciled":
			emit_timeline(dcs_name, "Customer PO mismatch - reconciliation " + str(tlpo) + " - open blockers " + str(st_.get("open_blockers")))
	return result
