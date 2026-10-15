# dcs_screen3 - Negotiation Workspace data service.
# READ ONLY. This service never writes. All movement goes through dcs_apply_revision.
# Revision identity comes from one state source: DCS Revision + custom_dcs_revision_no.

CUSTOMER_SIDE = ["Sales User", "Sales Manager", "Commercial Controller", "Managing Director"]
VENDOR_SIDE = ["Presales", "Sales Manager", "Commercial Controller", "Managing Director"]
TECHNICAL_ROLES = ["Technical Engineer", "Project Engineer", "Project Manager", "Operations Manager"]

MD_THRESHOLD = 16.0
CEILING = 26.0
MARGIN_FLOOR = 20.0

def pct(numer, denom):
	if not denom:
		return 0.0
	return int((((numer * 1.0) / denom) * 100000.0) + 0.5) / 1000.0

def r2(v):
	return int((v * 100.0) + 0.5) / 100.0

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

def matched(roles, wanted):
	out = []
	for r in wanted:
		if r in roles:
			out.append(r)
	return out

def requirement(c):
	if c > CEILING:
		return "Blocked"
	if c >= MD_THRESHOLD:
		return "Managing Director"
	return "None"

def gate_for(m):
	if m < MARGIN_FLOOR:
		return "Blocked"
	return "Clear"

def advisory_win(c, m, req):
	p = 55 + int(c * 1.6)
	if req == "Managing Director":
		p = p - 8
	if req == "Blocked":
		return 0
	if m < MARGIN_FLOOR:
		p = p - 15
	if p > 92:
		p = 92
	if p < 3:
		p = 3
	return p

def scenario(key, label, cost, sell, baseline, rationale):
	m = pct((sell - cost), sell)
	c = pct((baseline - sell), baseline)
	req = requirement(c)
	g = gate_for(m)
	blocker = ""
	if req == "Blocked":
		blocker = "Concession exceeds the 26% ceiling. No approver may authorise this position."
	elif g == "Blocked":
		blocker = "Margin is below the 20% floor. The margin gate is independent of approval routing."
	return {"key": key, "label": label, "total_cost": r2(cost), "total_selling": r2(sell), "gp": r2(sell - cost), "margin_percent": m, "concession_percent": c, "approval_required": req, "margin_gate": g, "advisory_win_probability": advisory_win(c, m, req), "blocker": blocker, "rationale": rationale, "submittable": 0 if req == "Blocked" else 1}

result = {"ok": 0, "error": "", "user": frappe.session.user, "capability": {}}

dcs_name = frappe.form_dict.get("dcs")
roles = get_user_roles(frappe.session.user)
can_cust = has_any(roles, CUSTOMER_SIDE)
can_vend = has_any(roles, VENDOR_SIDE)
is_tech = has_any(roles, TECHNICAL_ROLES)

cap = {"can_customer_side": can_cust, "can_vendor_side": can_vend, "can_negotiate": 0, "roles_matched": matched(roles, ["Sales User", "Presales", "Sales Manager", "Commercial Controller", "Managing Director"]), "denial_reason": ""}
if can_cust == 1 or can_vend == 1:
	cap["can_negotiate"] = 1
elif is_tech == 1:
	cap["denial_reason"] = "The Negotiation Workspace is a commercial workspace. Technical roles may record technical impact against a revision but may never move a commercial position."
else:
	cap["denial_reason"] = "You do not hold a commercial negotiation role. System Manager administration does not imply commercial authority."
result["capability"] = cap

if not dcs_name:
	result["error"] = "dcs is required."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
	result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif cap["can_negotiate"] == 0:
	result["error"] = cap["denial_reason"]
else:
	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("read")

	initialised = 1
	wc = s.custom_working_total_cost or 0
	ws = s.custom_working_total_selling or 0
	wm = s.custom_working_margin_percent or 0
	if (s.custom_dcs_revision_no or 0) < 1:
		initialised = 0
		wc = s.total_cost or 0
		ws = s.total_selling or 0
		wm = s.margin_percent or 0
	baseline = s.custom_baseline_selling or ws

	revisions = frappe.get_all("DCS Revision", filters={"dcs": dcs_name}, fields=["name", "revision_no", "source", "reason", "changed_by", "changed_on", "prev_total_cost", "prev_total_selling", "prev_margin_percent", "prev_concession_percent", "new_total_cost", "new_total_selling", "new_margin_percent", "new_concession_percent", "gp_movement", "margin_movement", "technical_impact", "approval_requirement", "approval_state", "margin_gate"], order_by="revision_no asc")

	# ---- four question header ----
	decision = "Decide the next negotiation movement on the living commercial position."
	if s.custom_approval_required == "Blocked":
		decision = "Recover this position. It is above the concession ceiling and cannot be authorised by anyone."
	elif s.custom_approval_required == "Managing Director":
		decision = "Decide whether to hold, counter, or send the current position to the Managing Director."
	if_nothing = "The customer receives no response and the position stays where it is. No revision is recorded."
	if s.custom_margin_gate == "Blocked":
		if_nothing = "The margin gate stays blocked. The deal cannot proceed to award on this position."
	result["header"] = {"decision": decision, "money": {"total_cost": r2(wc), "total_selling": r2(ws), "gp": r2(ws - wc), "margin_percent": wm, "currency": s.currency}, "if_nothing": if_nothing, "resolvable_here": 1}

	result["dcs"] = {"name": s.name, "customer": s.customer, "subject": s.subject, "deal_owner": s.deal_owner, "opportunity": s.opportunity, "docstatus": s.docstatus, "currency": s.currency, "initialised": initialised, "revision_no": s.custom_dcs_revision_no or 0, "revision_reference": s.custom_revision_reference, "baseline_selling": r2(baseline), "working_total_cost": r2(wc), "working_total_selling": r2(ws), "working_gp": r2(ws - wc), "working_margin_percent": wm, "concession_percent_from_baseline": s.custom_concession_percent_from_baseline or 0, "approval_required": s.custom_approval_required, "approval_state": s.custom_approval_state, "approval_reason": s.custom_approval_reason, "margin_gate": s.custom_margin_gate, "margin_gate_reason": s.custom_margin_gate_reason, "cancel_amend_required": 0, "cancel_amend_note": "This workspace never cancels and never amends. Every movement is an immutable DCS Revision against the same submitted document."}

	result["policy"] = {"md_threshold_percent": MD_THRESHOLD, "concession_ceiling_percent": CEILING, "margin_floor_percent": MARGIN_FLOOR, "basis": "Approval routing is driven by concession from baseline only. The 20% margin floor is an independent commercial gate and is never cleared by an approval decision."}

	result["revisions"] = revisions
	result["lines"] = frappe.get_all("Deal Cost Item", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"}, fields=["idx", "item_code", "item_name", "customer_item_name", "brand", "item_category", "qty", "cost_rate", "cost_amount", "selling_rate", "selling_amount", "gp_value", "gp_percent"], order_by="idx asc")
	result["resources"] = frappe.get_all("Deal Cost Resource", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"}, fields=["idx", "resource_type", "role", "no_of_persons", "no_of_days", "hours", "cost_rate", "cost_amount", "linked_project", "remarks"], order_by="idx asc")

	# ---- conversation timeline, built only from real revision records ----
	conv = []
	for rv in revisions:
		conv.append({"revision_no": rv.get("revision_no"), "party": rv.get("source"), "who": rv.get("changed_by"), "when": rv.get("changed_on"), "message": rv.get("reason"), "technical_impact": rv.get("technical_impact"), "selling_from": rv.get("prev_total_selling"), "selling_to": rv.get("new_total_selling"), "cost_from": rv.get("prev_total_cost"), "cost_to": rv.get("new_total_cost"), "approval_requirement": rv.get("approval_requirement"), "margin_gate": rv.get("margin_gate")})
	result["conversation"] = conv

	# ---- scenarios: Hold / Counter / Accept. Advisory only. ----
	target_raw = frappe.form_dict.get("customer_target")
	target = None
	if target_raw:
		if target_raw != "":
			target = float(target_raw)
	scn = []
	scn.append(scenario("hold", "Hold", wc, ws, baseline, "Do not move. Defend the current position on value."))
	if target is not None:
		if target > 0:
			mid = (ws + target) / 2.0
			scn.append(scenario("counter", "Counter", wc, mid, baseline, "Meet the customer approximately half way between the current position and their target."))
			scn.append(scenario("accept", "Accept customer target", wc, target, baseline, "Concede fully to the stated customer target."))
	else:
		scn.append(scenario("counter", "Counter (indicative 5% move)", wc, ws * 0.95, baseline, "Indicative only. Enter a customer target to model a real counter."))
	result["scenarios"] = scn
	result["scenario_notice"] = "Scenarios are advisory modelling only. They are not decisions, are not recorded, and no revision exists until Apply and Continue is used."

	# ---- live preview for the form the user is typing into ----
	p_cost = frappe.form_dict.get("probe_cost")
	p_sell = frappe.form_dict.get("probe_selling")
	if p_sell or p_cost:
		pc = wc
		ps = ws
		if p_cost:
			pc = float(p_cost)
		if p_sell:
			ps = float(p_sell)
		if ps > 0:
			result["preview"] = scenario("preview", "Proposed position", pc, ps, baseline, "Live impact of the values currently entered.")

	# ---- customer intelligence, real records only ----
	ci = {"customer": s.customer, "available": 0}
	if s.customer:
		prior = frappe.get_all("Deal Cost Sheet", filters={"customer": s.customer}, fields=["name", "custom_deal_status", "total_selling", "total_cost", "margin_percent"], order_by="creation desc")
		won = 0
		lost = 0
		tot = 0
		msum = 0.0
		mcount = 0
		for p in prior:
			tot = tot + 1
			st = p.get("custom_deal_status")
			if st == "Won":
				won = won + 1
			elif st == "Lost":
				lost = lost + 1
			elif st == "Dropped / No Bid":
				lost = lost + 1
			mv = p.get("margin_percent")
			if mv:
				msum = msum + float(mv)
				mcount = mcount + 1
		avg = 0.0
		if mcount > 0:
			avg = int(((msum / mcount) * 1000.0) + 0.5) / 1000.0
		ci = {"customer": s.customer, "available": 1, "total_deal_cost_sheets": tot, "won": won, "lost_or_dropped": lost, "decided": won + lost, "average_margin_percent": avg, "basis": "Counted from real Deal Cost Sheet records for this customer. Win rate is only meaningful once decided deals exist."}
	result["customer_intelligence"] = ci

	# ---- honest unavailability. Never fabricated. ----
	result["unavailable"] = [
		{"key": "vendor_intelligence", "label": "Vendor intelligence (response time, historical discount, reliability, alternatives)", "reason": "No supplier or vendor field exists on Deal Cost Item or Deal Cost Resource, and no vendor quotation evidence is captured. There is no real source for vendor behaviour."},
		{"key": "payment_behaviour", "label": "Customer payment behaviour", "reason": "Not sourced from Accounts Receivable in this step. Not fabricated."},
		{"key": "technical_signoff", "label": "Technical sign-off state", "reason": "No technical approval field exists on the Deal Cost Sheet. Technical impact is recorded as free text on each revision only."}
	]
	result["ok"] = 1

frappe.response["message"] = result
