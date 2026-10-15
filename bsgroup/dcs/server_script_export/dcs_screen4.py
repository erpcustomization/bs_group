# dcs_screen4 - Approval Workspace payload. READ ONLY. Writes nothing.
# Exists only to make an approval decision quickly and safely.
# Commercial Controller and Managing Director see the same commercial information.
# The available actions differ by authority. Technical roles have no access.

MD = "Managing Director"
CC = "Commercial Controller"
VIEW_ROLES = [MD, CC, "Sales Manager"]
TECHNICAL_ROLES = ["Technical Engineer", "Project Engineer", "Project Manager", "Operations Manager"]

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

def r2(v):
	x = (v or 0) * 100.0
	if x < 0:
		return int(x - 0.5) / 100.0
	return int(x + 0.5) / 100.0

def r3(v):
	x = (v or 0) * 1000.0
	if x < 0:
		return int(x - 0.5) / 1000.0
	return int(x + 0.5) / 1000.0

def holders(role):
	rows = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, fields=["parent"])
	out = []
	for r in rows:
		out.append(r.get("parent"))
	return out

result = {"ok": 0, "error": "", "user": frappe.session.user, "actions": [], "authority": ""}

dcs_name = frappe.form_dict.get("dcs")
roles = get_user_roles(frappe.session.user)
is_md = 0
is_cc = 0
if MD in roles:
	is_md = 1
if CC in roles:
	is_cc = 1
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

	if is_md == 1:
		result["authority"] = "Managing Director"
	elif is_cc == 1:
		result["authority"] = "Commercial Controller"
	else:
		result["authority"] = "Viewer"

	req = s.custom_approval_required
	state = s.custom_approval_state
	final = 0
	if state == "Approved":
		final = 1
	if state == "Rejected":
		final = 1

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

	# ---- 1. deal and requested decision ----
	result["deal"] = {"name": s.name, "customer": s.customer, "subject": s.subject, "deal_owner": s.deal_owner, "opportunity": s.opportunity, "currency": s.currency, "docstatus": s.docstatus, "revision_no": s.custom_dcs_revision_no, "revision_reference": s.custom_revision_reference, "approval_required": req, "approval_state": state, "requested_decision": "Authorise the negotiated commercial position at revision " + str(s.custom_revision_reference or "-") + "."}

	# ---- 2 & 3. current negotiated vs previous approved ----
	cur = {"total_cost": r2(s.custom_working_total_cost), "total_selling": r2(s.custom_working_total_selling), "gp": r2((s.custom_working_total_selling or 0) - (s.custom_working_total_cost or 0)), "margin_percent": s.custom_working_margin_percent or 0, "concession_percent": s.custom_concession_percent_from_baseline or 0}
	has_prev = 0
	if (s.custom_approved_revision_no or 0) > 0:
		has_prev = 1
	prev = {"available": has_prev, "revision_no": s.custom_approved_revision_no or 0, "total_cost": r2(s.custom_approved_total_cost), "total_selling": r2(s.custom_approved_total_selling), "gp": r2((s.custom_approved_total_selling or 0) - (s.custom_approved_total_cost or 0)), "margin_percent": s.custom_approved_margin_percent or 0, "approved_by": s.custom_approved_by, "approved_on": s.custom_approved_on}
	if has_prev == 0:
		base_rows = frappe.get_all("DCS Revision", filters={"dcs": dcs_name, "revision_no": 1}, fields=["new_total_cost", "new_total_selling", "new_margin_percent"])
		bc = 0.0
		bs = s.custom_baseline_selling or 0
		bm = 0.0
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
	result["delta"] = {"total_cost": r2(cur["total_cost"] - prev["total_cost"]), "total_selling": r2(cur["total_selling"] - prev["total_selling"]), "gp": r2(cur["gp"] - prev["gp"]), "margin_points": r3(cur["margin_percent"] - prev["margin_percent"]), "basis": prev["comparison_basis"]}

	# ---- 4. why this approver is required ----
	result["why"] = {"approval_reason": s.custom_approval_reason, "threshold_crossed": "Concession from baseline " + str(s.custom_concession_percent_from_baseline or 0) + "% against a 16% Managing Director threshold and a 26% ceiling.", "policy_basis": "Approval routing is driven by concession from baseline only. The Commercial Controller may review and endorse but is never the final approver on an escalated case.", "margin_gate": s.custom_margin_gate, "margin_gate_reason": s.custom_margin_gate_reason, "margin_gate_note": "The 20% margin floor is an independent commercial gate. Approving this position does not clear it."}

	# ---- 5. movement since the last approved position, split by side ----
	since = s.custom_approved_revision_no or 0
	revs = frappe.get_all("DCS Revision", filters={"dcs": dcs_name}, fields=["name", "revision_no", "source", "reason", "changed_by", "changed_on", "prev_total_cost", "prev_total_selling", "new_total_cost", "new_total_selling", "new_margin_percent", "new_concession_percent", "gp_movement", "margin_movement", "technical_impact", "approval_requirement", "approval_state", "margin_gate", "decided_by", "decided_on", "decision_reason"], order_by="revision_no asc")
	cust_move = 0.0
	vend_move = 0.0
	scope = []
	for rv in revs:
		if rv.get("revision_no") > since:
			if rv.get("source") == "Customer":
				cust_move = cust_move + ((rv.get("new_total_selling") or 0) - (rv.get("prev_total_selling") or 0))
			if rv.get("source") == "Vendor":
				vend_move = vend_move + ((rv.get("new_total_cost") or 0) - (rv.get("prev_total_cost") or 0))
			ti = rv.get("technical_impact")
			if ti:
				scope.append({"revision_no": rv.get("revision_no"), "source": rv.get("source"), "impact": ti})
	result["customer_concession_impact"] = {"selling_movement": r2(cust_move), "basis": "Net movement of the customer-side selling position across all Customer-source revisions since the last approved position."}
	result["vendor_recovery_impact"] = {"cost_movement": r2(vend_move), "recovered": r2(0 - vend_move), "basis": "Net movement of the vendor-side buying cost across all Vendor-source revisions since the last approved position. A negative cost movement is recovery."}
	result["scope_impact"] = scope
	result["technical_block"] = {"available": 0, "reason": "No technical approval or technical block field exists on the Deal Cost Sheet. Technical impact is recorded as free text on individual revisions only and is listed above. This is shown as unavailable rather than estimated."}

	# ---- 6. customer context ----
	ctx = {"customer": s.customer, "available": 0}
	if s.customer:
		prior = frappe.get_all("Deal Cost Sheet", filters={"customer": s.customer}, fields=["name", "custom_deal_status", "margin_percent"], order_by="creation desc")
		won = 0
		lost = 0
		msum = 0.0
		mc = 0
		for p in prior:
			st2 = p.get("custom_deal_status")
			if st2 == "Won":
				won = won + 1
			elif st2 == "Lost":
				lost = lost + 1
			elif st2 == "Dropped / No Bid":
				lost = lost + 1
			if p.get("margin_percent"):
				msum = msum + float(p.get("margin_percent"))
				mc = mc + 1
		avg = 0.0
		if mc > 0:
			avg = int(((msum / mc) * 1000.0) + 0.5) / 1000.0
		ctx = {"customer": s.customer, "available": 1, "cost_sheets": len(prior), "won": won, "lost_or_dropped": lost, "average_margin_percent": avg, "basis": "Counted from real Deal Cost Sheet records for this customer."}
	result["customer_context"] = ctx

	# ---- 7. advisory recommendation. Never a decision. ----
	conc = s.custom_concession_percent_from_baseline or 0
	mar = s.custom_working_margin_percent or 0
	rec = "Approve"
	conf = "Medium"
	why = "Concession is within the ceiling and the margin is above the floor."
	if req == "Blocked":
		rec = "Do not authorise"
		conf = "High"
		why = "The position is above the 26% concession ceiling. No approver may authorise it."
	elif s.custom_margin_gate == "Blocked":
		rec = "Return for Rework"
		conf = "High"
		why = "Margin " + str(mar) + "% is below the 20% floor. Approval would authorise the price but would leave the margin gate outstanding."
	elif conc >= 22:
		rec = "Return for Rework"
		conf = "Medium"
		why = "Concession " + str(conc) + "% is close to the 26% ceiling with limited room for further movement."
	result["recommendation"] = {"recommended_action": rec, "confidence": conf, "reasoning": why, "advisory_only": 1, "notice": "Advisory only. This is a recommendation, not a decision. No action is taken until an authorised approver presses a decision button."}

	# ---- 8. approval history ----
	hist = []
	for rv in revs:
		if rv.get("decided_by") or rv.get("approval_state") not in ["Not Required", "Blocked"]:
			hist.append({"revision_no": rv.get("revision_no"), "name": rv.get("name"), "requirement": rv.get("approval_requirement"), "state": rv.get("approval_state"), "decided_by": rv.get("decided_by"), "decided_on": rv.get("decided_on"), "decision_reason": rv.get("decision_reason"), "source": rv.get("source"), "reason": rv.get("reason")})
	result["approval_history"] = hist
	result["endorsement"] = {"endorsed_by": s.custom_endorsed_by, "endorsed_on": s.custom_endorsed_on, "last_decision_reason": s.custom_last_decision_reason}

	# ---- 9. consequence summary ----
	approved_txt = "The negotiated commercial position becomes authorised. This does not itself mean the project is awarded. Any unresolved technical or customer-evidence gate remains outstanding."
	if s.custom_margin_gate == "Blocked":
		approved_txt = approved_txt + " The margin gate is currently BLOCKED and approval does not clear it."
	result["consequences"] = {"approved": approved_txt, "returned": "The negotiation reopens at the current revision. No commercial position is authorised and the deal owner is expected to move the position again.", "rejected": "This commercial position is closed. Nothing is authorised. A new negotiation would have to start from the current living position.", "endorsed": "The position is recorded as reviewed and endorsed and passes to the Managing Director, who remains the final approver. Endorsement authorises nothing on its own."}

	# ---- 10. actual assigned approvers from ERPNext ----
	result["approvers"] = {"managing_director": holders(MD), "commercial_controller": holders(CC), "basis": "Read from real Has Role assignments. No approver name is hard coded."}
	result["ok"] = 1

frappe.response["message"] = result
