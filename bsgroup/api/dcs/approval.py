"""Approval Workspace services: ``dcs_approval_decision`` (write) and ``dcs_screen4`` (read).

Ported from the production Server Scripts of the same names. Authority is
enforced server side: Commercial Controller may Endorse or Return for
Rework; only the Managing Director may Approve or Reject. A recorded final
decision is never altered.
"""

import frappe
from frappe.utils import now_datetime

from bsgroup.api.dcs._common import (
	CC, MD, TECHNICAL_ROLES, audit_event, dcs_exists_and_open, emit_timeline, get_user_roles,
	governed_endpoint, has_any, r2, r3,
)

VIEW_ROLES = [MD, CC, "Sales Manager"]


def holders(role):
	rows = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, fields=["parent"])
	return [r.get("parent") for r in rows]


@governed_endpoint("dcs_approval_decision", ptype="write")
def dcs_approval_decision(args):
	result = {"ok": 0, "error": "", "action": "", "state": {}}

	dcs_name = args.get("dcs")
	action = args.get("action")
	reason = args.get("reason")
	valid = ["Endorse", "Approve", "Return for Rework", "Reject"]
	needs_reason = ["Return for Rework", "Reject"]

	roles = get_user_roles()
	is_md = 1 if MD in roles else 0
	is_cc = 1 if CC in roles else 0

	if not dcs_name:
		result["error"] = "dcs is required."
	elif action not in valid:
		result["error"] = "action must be one of Endorse, Approve, Return for Rework, Reject."
	elif not dcs_exists_and_open(dcs_name, result):
		pass
	elif is_md == 0 and is_cc == 0:
		result["error"] = "You do not hold an approval authority. Only the Commercial Controller and the Managing Director may act on this screen."
	elif action in needs_reason and not reason:
		result["error"] = "A reason is required to " + str(action) + ". A decision that sends work back or closes a position is never recorded silently."
	elif action == "Approve" and is_md == 0:
		result["error"] = "The Commercial Controller may review and endorse but is never the final approver on an escalated case. Only the Managing Director may approve."
	elif action == "Reject" and is_md == 0:
		result["error"] = "The Commercial Controller may not reject an escalated case. Only the Managing Director may reject."
	elif action == "Endorse" and is_cc == 0:
		result["error"] = "Endorsement is a Commercial Controller action."
	else:
		s = frappe.get_doc("Deal Cost Sheet", dcs_name)
		s.check_permission("write")
		req = s.custom_approval_required
		state = s.custom_approval_state
		rev_ref = s.custom_revision_reference

		if state == "Approved" or state == "Rejected":
			result["error"] = "A final decision (" + str(state) + ") is already recorded on this Deal Cost Sheet. A recorded approval decision cannot be altered."
		elif (s.custom_dcs_revision_no or 0) < 1:
			result["error"] = "The living position has not been initialised. There is nothing to approve."
		elif req == "None" and action in ["Approve", "Endorse"]:
			result["error"] = "No approval is required for the current position. The concession is below the 16% Managing Director threshold."
		elif req == "Blocked" and action in ["Approve", "Endorse"]:
			result["error"] = "This position is above the 26% concession ceiling. No approver may authorise it. It can only be returned for rework or rejected."
		elif not frappe.db.exists("DCS Revision", rev_ref):
			result["error"] = "The current revision reference " + str(rev_ref) + " could not be found."
		else:
			now = now_datetime()
			me = frappe.session.user
			if action == "Endorse":
				new_state = "Endorsed - Pending MD"
				patch = {"custom_approval_state": new_state, "custom_endorsed_by": me, "custom_endorsed_on": now,
						 "custom_last_decision_reason": reason or "Endorsed by the Commercial Controller. The Managing Director remains the final approver."}
			elif action == "Approve":
				new_state = "Approved"
				patch = {"custom_approval_state": new_state, "custom_approved_revision_no": s.custom_dcs_revision_no,
						 "custom_approved_total_cost": s.custom_working_total_cost,
						 "custom_approved_total_selling": s.custom_working_total_selling,
						 "custom_approved_margin_percent": s.custom_working_margin_percent, "custom_approved_by": me,
						 "custom_approved_on": now, "custom_last_decision_reason": reason or "Approved by the Managing Director."}
			elif action == "Return for Rework":
				new_state = "Returned for Rework"
				patch = {"custom_approval_state": new_state, "custom_last_decision_reason": reason}
			else:
				new_state = "Rejected"
				patch = {"custom_approval_state": new_state, "custom_last_decision_reason": reason}

			dcs_keys = ["custom_approval_state", "custom_endorsed_by", "custom_endorsed_on", "custom_approved_revision_no",
						"custom_approved_total_cost", "custom_approved_total_selling", "custom_approved_margin_percent",
						"custom_approved_by", "custom_approved_on", "custom_last_decision_reason"]
			dcs_before = {pk: s.get(pk) for pk in dcs_keys if pk in patch}
			rev_doc = frappe.get_doc("DCS Revision", rev_ref)
			rev_before = {f: rev_doc.get(f) for f in ("approval_state", "decided_by", "decided_on", "decision_reason")}
			rev_reason = reason or ("Recorded by " + str(action) + ".")

			# The decision fields on DCS Revision are locked against document saves
			# (immutability guard); the trusted db.set_value channel is the only writer.
			frappe.db.set_value(
				"DCS Revision", rev_ref,
				{"approval_state": new_state, "decided_by": me, "decided_on": now, "decision_reason": rev_reason},
				update_modified=True,
			)
			frappe.db.set_value("Deal Cost Sheet", dcs_name, patch, update_modified=True)

			codes = {"Endorse": "DCS_APPROVAL_ENDORSED", "Approve": "DCS_APPROVAL_APPROVED",
					 "Return for Rework": "DCS_APPROVAL_RETURNED_FOR_REWORK", "Reject": "DCS_APPROVAL_REJECTED"}
			labels = {"Endorse": "Endorse - Commercial Controller", "Approve": "Approve - Managing Director",
					  "Return for Rework": "Return for Rework", "Reject": "Reject - Managing Director"}
			changes = []
			for pk in dcs_keys:
				if pk in patch:
					changes.append({"field": pk, "old": dcs_before.get(pk), "new": patch.get(pk), "dt": "Deal Cost Sheet", "dn": dcs_name})
			changes.append({"field": "approval_state", "old": rev_before.get("approval_state"), "new": new_state, "dt": "DCS Revision", "dn": rev_ref})
			changes.append({"field": "decided_by", "old": rev_before.get("decided_by"), "new": me, "dt": "DCS Revision", "dn": rev_ref})
			changes.append({"field": "decided_on", "old": rev_before.get("decided_on"), "new": now, "dt": "DCS Revision", "dn": rev_ref})
			changes.append({"field": "decision_reason", "old": rev_before.get("decision_reason"), "new": rev_reason, "dt": "DCS Revision", "dn": rev_ref})
			result["governance_event"] = audit_event(
				dcs_name, codes.get(action) or "DCS_APPROVAL_DECISION", labels.get(action) or str(action),
				"dcs_approval_decision", reason or "", s.custom_dcs_revision_no, rev_ref, rev_ref, changes,
			)

			gate_note = ""
			if s.custom_margin_gate == "Blocked":
				gate_note = "The margin gate remains BLOCKED. This decision does not clear it."
			result["ok"] = 1
			result["action"] = action
			result["state"] = {
				"approval_state": new_state, "revision": rev_ref, "decided_by": me, "decided_on": now,
				"decision_reason": rev_reason, "approval_required": req, "margin_gate": s.custom_margin_gate,
				"margin_gate_note": gate_note, "docstatus_unchanged": s.docstatus,
				"authorised_position": {"total_cost": s.custom_working_total_cost, "total_selling": s.custom_working_total_selling,
										"margin_percent": s.custom_working_margin_percent},
			}

	if result.get("ok"):
		st_ = result.get("state") or {}
		tlas = st_.get("approval_state")
		text = ""
		if tlas == "Returned for Rework":
			text = "Approval returned for rework - revision " + str(st_.get("revision"))
		if tlas == "Approved":
			text = ("APPROVED - " + str(dcs_name) + " revision " + str(st_.get("revision")) + " - decision " + str(result.get("action"))
					+ " - approver " + str(st_.get("decided_by")) + " - at " + str(st_.get("decided_on")) + " - resulting state " + str(tlas))
		if tlas == "Rejected":
			text = ("REJECTED - " + str(dcs_name) + " revision " + str(st_.get("revision")) + " - decision " + str(result.get("action"))
					+ " - approver " + str(st_.get("decided_by")) + " - at " + str(st_.get("decided_on")) + " - reason "
					+ str(st_.get("decision_reason")) + " - resulting state " + str(tlas))
		emit_timeline(dcs_name, text)
	return result


@governed_endpoint("dcs_screen4", ptype="read", idempotent=False)
def dcs_screen4(args):
	result = {"ok": 0, "error": "", "user": frappe.session.user, "actions": [], "authority": ""}

	dcs_name = args.get("dcs")
	roles = get_user_roles()
	is_md = 1 if MD in roles else 0
	is_cc = 1 if CC in roles else 0
	can_view = has_any(roles, VIEW_ROLES)

	if not dcs_name:
		result["error"] = "dcs is required."
	elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
		result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
	elif can_view == 0:
		if has_any(roles, TECHNICAL_ROLES) == 1:
			result["error"] = "The Approval Workspace is a commercial approval screen. Technical roles have no access to it."
		else:
			result["error"] = "You do not hold a commercial approval or commercial review role. System Manager administration does not imply approval authority."
	else:
		s = frappe.get_doc("Deal Cost Sheet", dcs_name)
		s.check_permission("read")

		result["authority"] = "Managing Director" if is_md == 1 else ("Commercial Controller" if is_cc == 1 else "Viewer")

		req = s.custom_approval_required
		state = s.custom_approval_state
		final = 1 if state in ("Approved", "Rejected") else 0

		acts = []
		if final == 0:
			if is_md == 1:
				if req == "Managing Director":
					acts.append({"key": "Approve", "label": "Approve", "needs_reason": 0, "note": "Authorises the negotiated commercial position."})
				acts.append({"key": "Return for Rework", "label": "Return for Rework", "needs_reason": 1, "note": "Sends the position back to negotiation."})
				acts.append({"key": "Reject", "label": "Reject", "needs_reason": 1, "note": "Closes this commercial position."})
			elif is_cc == 1:
				if req == "Managing Director":
					acts.append({"key": "Endorse", "label": "Endorse to Managing Director", "needs_reason": 0, "note": "Commercial Controller may review and endorse. The Managing Director remains the final approver."})
				acts.append({"key": "Return for Rework", "label": "Return for Rework", "needs_reason": 1, "note": "Sends the position back to negotiation."})
		result["actions"] = acts

		blockers = []
		if req == "None":
			blockers.append("No approval is required. The current concession is below the 16% Managing Director threshold, so there is nothing to decide here.")
		if req == "Blocked":
			blockers.append("Concession is above the 26% ceiling. No approver may authorise this position. It can only be returned for rework or rejected.")
		if final == 1:
			blockers.append("A final decision (" + str(state) + ") is already recorded. It cannot be altered.")
		result["blockers"] = blockers

		result["deal"] = {
			"name": s.name, "customer": s.customer, "subject": s.subject, "deal_owner": s.deal_owner, "opportunity": s.opportunity,
			"currency": s.currency, "docstatus": s.docstatus, "revision_no": s.custom_dcs_revision_no,
			"revision_reference": s.custom_revision_reference, "approval_required": req, "approval_state": state,
			"requested_decision": "Authorise the negotiated commercial position at revision " + str(s.custom_revision_reference or "-") + ".",
		}

		cur = {"total_cost": r2(s.custom_working_total_cost), "total_selling": r2(s.custom_working_total_selling),
			   "gp": r2((s.custom_working_total_selling or 0) - (s.custom_working_total_cost or 0)),
			   "margin_percent": s.custom_working_margin_percent or 0, "concession_percent": s.custom_concession_percent_from_baseline or 0}
		has_prev = 1 if (s.custom_approved_revision_no or 0) > 0 else 0
		prev = {"available": has_prev, "revision_no": s.custom_approved_revision_no or 0, "total_cost": r2(s.custom_approved_total_cost),
				"total_selling": r2(s.custom_approved_total_selling),
				"gp": r2((s.custom_approved_total_selling or 0) - (s.custom_approved_total_cost or 0)),
				"margin_percent": s.custom_approved_margin_percent or 0, "approved_by": s.custom_approved_by, "approved_on": s.custom_approved_on}
		if has_prev == 0:
			base_rows = frappe.get_all("DCS Revision", filters={"dcs": dcs_name, "revision_no": 1}, fields=["new_total_cost", "new_total_selling", "new_margin_percent"])
			bc, bs, bm = 0.0, s.custom_baseline_selling or 0, 0.0
			for b in base_rows:
				bc = b.get("new_total_cost") or 0
				bs = b.get("new_total_selling") or 0
				bm = b.get("new_margin_percent") or 0
			prev["basis"] = "No commercial position has been approved on this Deal Cost Sheet before. The comparison is against the commercial baseline recorded at R1."
			prev["comparison_basis"] = "R1 baseline"
			prev["total_cost"] = r2(bc)
			prev["total_selling"] = r2(bs)
			prev["gp"] = r2(bs - bc)
			prev["margin_percent"] = bm
		else:
			prev["comparison_basis"] = "Last approved position"
		result["current"] = cur
		result["previous_approved"] = prev
		result["delta"] = {"total_cost": r2(cur["total_cost"] - prev["total_cost"]), "total_selling": r2(cur["total_selling"] - prev["total_selling"]),
						   "gp": r2(cur["gp"] - prev["gp"]), "margin_points": r3(cur["margin_percent"] - prev["margin_percent"]), "basis": prev["comparison_basis"]}

		result["why"] = {
			"approval_reason": s.custom_approval_reason,
			"threshold_crossed": "Concession from baseline " + str(s.custom_concession_percent_from_baseline or 0) + "% against a 16% Managing Director threshold and a 26% ceiling.",
			"policy_basis": "Approval routing is driven by concession from baseline only. The Commercial Controller may review and endorse but is never the final approver on an escalated case.",
			"margin_gate": s.custom_margin_gate, "margin_gate_reason": s.custom_margin_gate_reason,
			"margin_gate_note": "The 20% margin floor is an independent commercial gate. Approving this position does not clear it.",
		}

		since = s.custom_approved_revision_no or 0
		revs = frappe.get_all(
			"DCS Revision", filters={"dcs": dcs_name},
			fields=["name", "revision_no", "source", "reason", "changed_by", "changed_on", "prev_total_cost", "prev_total_selling",
					"new_total_cost", "new_total_selling", "new_margin_percent", "new_concession_percent", "gp_movement", "margin_movement",
					"technical_impact", "approval_requirement", "approval_state", "margin_gate", "decided_by", "decided_on", "decision_reason"],
			order_by="revision_no asc",
		)
		cust_move = vend_move = 0.0
		scope = []
		for rv in revs:
			if rv.get("revision_no") > since:
				if rv.get("source") == "Customer":
					cust_move += ((rv.get("new_total_selling") or 0) - (rv.get("prev_total_selling") or 0))
				if rv.get("source") == "Vendor":
					vend_move += ((rv.get("new_total_cost") or 0) - (rv.get("prev_total_cost") or 0))
				ti = rv.get("technical_impact")
				if ti:
					scope.append({"revision_no": rv.get("revision_no"), "source": rv.get("source"), "impact": ti})
		result["customer_concession_impact"] = {"selling_movement": r2(cust_move), "basis": "Net movement of the customer-side selling position across all Customer-source revisions since the last approved position."}
		result["vendor_recovery_impact"] = {"cost_movement": r2(vend_move), "recovered": r2(0 - vend_move), "basis": "Net movement of the vendor-side buying cost across all Vendor-source revisions since the last approved position. A negative cost movement is recovery."}
		result["scope_impact"] = scope
		result["technical_block"] = {"available": 0, "reason": "No technical approval or technical block field exists on the Deal Cost Sheet. Technical impact is recorded as free text on individual revisions only and is listed above. This is shown as unavailable rather than estimated."}

		ctx = {"customer": s.customer, "available": 0}
		if s.customer:
			prior = frappe.get_all("Deal Cost Sheet", filters={"customer": s.customer}, fields=["name", "custom_deal_status", "margin_percent"], order_by="creation desc")
			won = lost = mc = 0
			msum = 0.0
			for p in prior:
				st2 = p.get("custom_deal_status")
				if st2 == "Won":
					won += 1
				elif st2 in ("Lost", "Dropped / No Bid"):
					lost += 1
				if p.get("margin_percent"):
					msum += float(p.get("margin_percent"))
					mc += 1
			avg = int(((msum / mc) * 1000.0) + 0.5) / 1000.0 if mc > 0 else 0.0
			ctx = {"customer": s.customer, "available": 1, "cost_sheets": len(prior), "won": won, "lost_or_dropped": lost,
				   "average_margin_percent": avg, "basis": "Counted from real Deal Cost Sheet records for this customer."}
		result["customer_context"] = ctx

		conc = s.custom_concession_percent_from_baseline or 0
		mar = s.custom_working_margin_percent or 0
		rec, conf, why = "Approve", "Medium", "Concession is within the ceiling and the margin is above the floor."
		if req == "Blocked":
			rec, conf, why = "Do not authorise", "High", "The position is above the 26% concession ceiling. No approver may authorise it."
		elif s.custom_margin_gate == "Blocked":
			rec, conf, why = "Return for Rework", "High", "Margin " + str(mar) + "% is below the 20% floor. Approval would authorise the price but would leave the margin gate outstanding."
		elif conc >= 22:
			rec, conf, why = "Return for Rework", "Medium", "Concession " + str(conc) + "% is close to the 26% ceiling with limited room for further movement."
		result["recommendation"] = {"recommended_action": rec, "confidence": conf, "reasoning": why, "advisory_only": 1,
									"notice": "Advisory only. This is a recommendation, not a decision. No action is taken until an authorised approver presses a decision button."}

		hist = []
		for rv in revs:
			if rv.get("decided_by") or rv.get("approval_state") not in ["Not Required", "Blocked"]:
				hist.append({"revision_no": rv.get("revision_no"), "name": rv.get("name"), "requirement": rv.get("approval_requirement"),
							 "state": rv.get("approval_state"), "decided_by": rv.get("decided_by"), "decided_on": rv.get("decided_on"),
							 "decision_reason": rv.get("decision_reason"), "source": rv.get("source"), "reason": rv.get("reason")})
		result["approval_history"] = hist
		result["endorsement"] = {"endorsed_by": s.custom_endorsed_by, "endorsed_on": s.custom_endorsed_on, "last_decision_reason": s.custom_last_decision_reason}

		approved_txt = "The negotiated commercial position becomes authorised. This does not itself mean the project is awarded. Any unresolved technical or customer-evidence gate remains outstanding."
		if s.custom_margin_gate == "Blocked":
			approved_txt += " The margin gate is currently BLOCKED and approval does not clear it."
		result["consequences"] = {
			"approved": approved_txt,
			"returned": "The negotiation reopens at the current revision. No commercial position is authorised and the deal owner is expected to move the position again.",
			"rejected": "This commercial position is closed. Nothing is authorised. A new negotiation would have to start from the current living position.",
			"endorsed": "The position is recorded as reviewed and endorsed and passes to the Managing Director, who remains the final approver. Endorsement authorises nothing on its own.",
		}
		result["approvers"] = {"managing_director": holders(MD), "commercial_controller": holders(CC), "basis": "Read from real Has Role assignments. No approver name is hard coded."}
		result["ok"] = 1

	return result
