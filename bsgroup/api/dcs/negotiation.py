"""Negotiation Workspace services: ``dcs_apply_revision`` (write) and ``dcs_screen3`` (read).

Ported from the production Server Scripts of the same names
(``bsgroup/dcs/server_script_export/dcs_apply_revision.py`` and
``dcs_screen3.py``). Business rules are unchanged:

* approval routing is driven by concession from baseline only
  (>= 16 % Managing Director, > 26 % Blocked);
* the 20 % margin floor is an independent gate, never cleared by approval;
* every movement is an immutable DCS Revision; the sheet is never cancelled
  or amended.
"""

import frappe
from frappe.utils import now_datetime

from bsgroup.api.dcs._common import (
	CEILING, CUSTOMER_SIDE, MARGIN_FLOOR, MD_THRESHOLD, TECHNICAL_ROLES, VENDOR_SIDE,
	audit_event, dcs_exists_and_open, diff_changes, emit_timeline, get_user_roles,
	governed_endpoint, has_any, matched, snapshot,
)


def pct(numer, denom):
	if not denom:
		return 0.0
	return int((((numer * 1.0) / denom) * 100000.0) + 0.5) / 1000.0


def r2(v):
	return int((v * 100.0) + 0.5) / 100.0


def num(v, fallback):
	if v is None or v == "":
		return fallback
	return float(v)


def requirement(concession):
	if concession > CEILING:
		return "Blocked"
	if concession >= MD_THRESHOLD:
		return "Managing Director"
	return "None"


def why_approval(concession):
	if concession > CEILING:
		return "Concession " + str(concession) + "% from baseline is above the 26% ceiling. No approver may authorise this position."
	if concession >= MD_THRESHOLD:
		return "Concession " + str(concession) + "% from baseline is at or above 16%, which requires Managing Director approval."
	return "Concession " + str(concession) + "% from baseline is below 16%. No discount sign-off is required."


def gate_for(margin):
	return "Blocked" if margin < MARGIN_FLOOR else "Clear"


def why_gate(margin):
	if margin < MARGIN_FLOOR:
		return "MARGIN GATE BLOCKED. Margin " + str(margin) + "% is below the 20% commercial floor. This gate is evaluated independently of approval routing and is not cleared by an approval decision."
	return "Margin " + str(margin) + "% is at or above the 20% commercial floor."


def state_for(req):
	if req == "Blocked":
		return "Blocked"
	if req == "Managing Director":
		return "Pending Endorsement"
	return "In Negotiation"


def rev_state_for(req):
	if req == "Blocked":
		return "Blocked"
	if req == "Managing Director":
		return "Pending Endorsement"
	return "Not Required"


def write_revision(sheet_name, no, src, rsn, pc, ps, pm, pcon, nc, ns, nm, ncon, ti, req, st, mg):
	rev = frappe.new_doc("DCS Revision")
	rev.dcs = sheet_name
	rev.revision_no = no
	rev.changed_by = frappe.session.user
	rev.changed_on = now_datetime()
	rev.source = src
	rev.reason = rsn
	rev.prev_total_cost = pc
	rev.prev_total_selling = ps
	rev.prev_margin_percent = pm
	rev.prev_concession_percent = pcon
	rev.new_total_cost = nc
	rev.new_total_selling = ns
	rev.new_margin_percent = nm
	rev.new_concession_percent = ncon
	rev.gp_movement = (ns - nc) - (ps - pc)
	rev.margin_movement = int(((nm - pm) * 1000.0) + 0.5) / 1000.0
	rev.technical_impact = ti
	rev.approval_requirement = req
	rev.approval_state = st
	rev.margin_gate = mg
	rev.flags.dcs_api_write = 1
	try:
		# No role holds `create` on DCS Revision: negotiation history is written
		# only by this service after the commercial-authority gate above.
		rev.insert(ignore_permissions=True)
	except Exception as e:
		return "COLLISION::" + str(e)
	return rev.name


D2A_FIELDS = [
	"custom_dcs_revision_no", "custom_revision_reference", "custom_working_total_cost",
	"custom_working_total_selling", "custom_working_margin_percent",
	"custom_concession_percent_from_baseline", "custom_baseline_selling", "custom_approval_state",
	"custom_approval_required", "custom_approval_reason", "custom_margin_gate", "custom_margin_gate_reason",
]


NO_COMMERCIAL_EDIT = (
	"You do not hold a commercial-edit role. Technical roles and System Manager "
	"administration cannot revise a commercial position."
)


@governed_endpoint("dcs_apply_revision", ptype="write", denied_message=NO_COMMERCIAL_EDIT)
def dcs_apply_revision(args):
	result = {"ok": 0, "error": "", "revision": "", "initialised": 0, "state": {}}

	dcs_name = args.get("dcs")
	source = args.get("source")
	reason = args.get("reason")
	tech_impact = args.get("technical_impact")
	valid_sources = ["Customer", "Vendor", "Technical", "Internal"]

	if not dcs_name:
		result["error"] = "dcs is required."
	elif not reason:
		result["error"] = "A reason is required for every revision. Revisions are never recorded silently."
	elif source not in valid_sources:
		result["error"] = "source must be one of Customer, Vendor, Technical, Internal."
	elif not dcs_exists_and_open(dcs_name, result):
		pass
	else:
		sheet = frappe.get_doc("Deal Cost Sheet", dcs_name)
		sheet.check_permission("write")

		my_roles = get_user_roles()
		can_customer = has_any(my_roles, CUSTOMER_SIDE)
		can_vendor = has_any(my_roles, VENDOR_SIDE)

		rev_no = sheet.custom_dcs_revision_no or 0
		baseline = sheet.custom_baseline_selling or 0
		init_done = 0

		# The baseline initialisation writes a governed DCS Revision under service
		# authority. It never runs before the commercial authority gate.
		if rev_no < 1 and (can_customer == 1 or can_vendor == 1):
			base_cost = sheet.total_cost or 0
			base_sell = sheet.total_selling or 0
			baseline = base_sell
			base_margin = pct((base_sell - base_cost), base_sell)
			write_revision(
				dcs_name, 1, "Internal",
				"Commercial baseline established from the existing submitted Deal Cost Sheet totals. No commercial change was made by this entry.",
				base_cost, base_sell, base_margin, 0.0, base_cost, base_sell, base_margin, 0.0, "", "None", "Not Required", gate_for(base_margin),
			)
			rev_no = 1
			init_done = 1
			prev_cost, prev_sell, prev_margin, prev_con = base_cost, base_sell, base_margin, 0.0
		else:
			prev_cost = sheet.custom_working_total_cost or 0
			prev_sell = sheet.custom_working_total_selling or 0
			prev_margin = sheet.custom_working_margin_percent or 0
			prev_con = sheet.custom_concession_percent_from_baseline or 0

		new_cost = num(args.get("new_total_cost"), prev_cost)
		new_sell = num(args.get("new_total_selling"), prev_sell)

		sell_moved = 1 if new_sell != prev_sell else 0
		cost_moved = 1 if new_cost != prev_cost else 0

		if can_customer == 0 and can_vendor == 0:
			result["error"] = NO_COMMERCIAL_EDIT
		elif sell_moved == 1 and can_customer == 0:
			result["error"] = "Your role may not move the customer-side selling position. Presales may revise buying cost only."
		elif cost_moved == 1 and can_vendor == 0:
			result["error"] = "Your role may not move the vendor-side buying cost. Sales User may revise the customer-side selling position only."
		elif new_sell <= 0:
			result["error"] = "Proposed selling value must be greater than zero."
		else:
			only_init = 1 if (new_cost == prev_cost and new_sell == prev_sell and init_done == 1) else 0

			new_margin = pct((new_sell - new_cost), new_sell)
			new_con = pct((baseline - new_sell), baseline)
			req = requirement(new_con)
			mg = gate_for(new_margin)
			appr_text = why_approval(new_con)
			gate_text = why_gate(new_margin)

			if only_init == 1:
				next_no = 1
				rev_name = str(dcs_name) + "-R1"
				st = "Not Started"
				appr_text = "Living position initialised. No negotiation applied yet."
			else:
				next_no = rev_no + 1
				st = state_for(req)
				rev_name = write_revision(
					dcs_name, next_no, source, reason, prev_cost, prev_sell, prev_margin, prev_con,
					new_cost, new_sell, new_margin, new_con, tech_impact, req, rev_state_for(req), mg,
				)
			if str(rev_name)[0:11] == "COLLISION::":
				result["ok"] = 0
				result["error"] = "Another user recorded a revision on this deal a moment ago, so this movement was not saved. Reload the workspace to see the current position and apply the movement again. Nothing was lost and no revision was overwritten."
			else:
				before = snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
				frappe.db.set_value(
					"Deal Cost Sheet", dcs_name,
					{
						"custom_dcs_revision_no": next_no, "custom_revision_reference": rev_name,
						"custom_working_total_cost": new_cost, "custom_working_total_selling": new_sell,
						"custom_working_margin_percent": new_margin, "custom_concession_percent_from_baseline": new_con,
						"custom_baseline_selling": baseline, "custom_approval_state": st,
						"custom_approval_required": req, "custom_approval_reason": appr_text,
						"custom_margin_gate": mg, "custom_margin_gate_reason": gate_text,
					},
					update_modified=True,
				)
				after = snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
				moved = diff_changes(D2A_FIELDS, before, after, "Deal Cost Sheet", dcs_name)
				result["governance_event"] = audit_event(
					dcs_name, "DCS_REVISION_APPLIED", "Apply a negotiated revision to the living commercial position",
					"dcs_apply_revision", reason, next_no, rev_name, rev_name, moved,
				)
				result["ok"] = 1
				result["initialised"] = init_done
				result["revision"] = rev_name
				result["state"] = {
					"revision_no": next_no, "working_total_cost": new_cost, "working_total_selling": new_sell,
					"working_margin_percent": new_margin, "concession_percent_from_baseline": new_con,
					"baseline_selling": baseline, "approval_state": st, "approval_required": req,
					"approval_reason": appr_text, "margin_gate": mg, "margin_gate_reason": gate_text,
					"gp_movement": (new_sell - new_cost) - (prev_sell - prev_cost),
					"docstatus_unchanged": sheet.docstatus,
				}

	if result.get("ok"):
		st_ = result.get("state") or {}
		req_ = st_.get("approval_required")
		if req_ and req_ != "None":
			emit_timeline(dcs_name, "Approval required: " + str(req_) + " - revision " + str(st_.get("revision_no")) + " - state " + str(st_.get("approval_state")))
	return result


# ---------------------------------------------------------------------------
# dcs_screen3 - READ ONLY
# ---------------------------------------------------------------------------
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
	return {
		"key": key, "label": label, "total_cost": r2(cost), "total_selling": r2(sell), "gp": r2(sell - cost),
		"margin_percent": m, "concession_percent": c, "approval_required": req, "margin_gate": g,
		"advisory_win_probability": advisory_win(c, m, req), "blocker": blocker, "rationale": rationale,
		"submittable": 0 if req == "Blocked" else 1,
	}


@governed_endpoint("dcs_screen3", ptype="read", idempotent=False)
def dcs_screen3(args):
	result = {"ok": 0, "error": "", "user": frappe.session.user, "capability": {}}

	dcs_name = args.get("dcs")
	roles = get_user_roles()
	can_cust = has_any(roles, CUSTOMER_SIDE)
	can_vend = has_any(roles, VENDOR_SIDE)
	is_tech = has_any(roles, TECHNICAL_ROLES)

	cap = {
		"can_customer_side": can_cust, "can_vendor_side": can_vend, "can_negotiate": 0,
		"roles_matched": matched(roles, ["Sales User", "Presales", "Sales Manager", "Commercial Controller", "Managing Director"]),
		"denial_reason": "",
	}
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

		revisions = frappe.get_all(
			"DCS Revision", filters={"dcs": dcs_name},
			fields=["name", "revision_no", "source", "reason", "changed_by", "changed_on", "prev_total_cost",
					"prev_total_selling", "prev_margin_percent", "prev_concession_percent", "new_total_cost",
					"new_total_selling", "new_margin_percent", "new_concession_percent", "gp_movement",
					"margin_movement", "technical_impact", "approval_requirement", "approval_state", "margin_gate"],
			order_by="revision_no asc",
		)

		decision = "Decide the next negotiation movement on the living commercial position."
		if s.custom_approval_required == "Blocked":
			decision = "Recover this position. It is above the concession ceiling and cannot be authorised by anyone."
		elif s.custom_approval_required == "Managing Director":
			decision = "Decide whether to hold, counter, or send the current position to the Managing Director."
		if_nothing = "The customer receives no response and the position stays where it is. No revision is recorded."
		if s.custom_margin_gate == "Blocked":
			if_nothing = "The margin gate stays blocked. The deal cannot proceed to award on this position."
		result["header"] = {
			"decision": decision,
			"money": {"total_cost": r2(wc), "total_selling": r2(ws), "gp": r2(ws - wc), "margin_percent": wm, "currency": s.currency},
			"if_nothing": if_nothing, "resolvable_here": 1,
		}

		result["dcs"] = {
			"name": s.name, "customer": s.customer, "subject": s.subject, "deal_owner": s.deal_owner,
			"opportunity": s.opportunity, "docstatus": s.docstatus, "currency": s.currency, "initialised": initialised,
			"revision_no": s.custom_dcs_revision_no or 0, "revision_reference": s.custom_revision_reference,
			"baseline_selling": r2(baseline), "working_total_cost": r2(wc), "working_total_selling": r2(ws),
			"working_gp": r2(ws - wc), "working_margin_percent": wm,
			"concession_percent_from_baseline": s.custom_concession_percent_from_baseline or 0,
			"approval_required": s.custom_approval_required, "approval_state": s.custom_approval_state,
			"approval_reason": s.custom_approval_reason, "margin_gate": s.custom_margin_gate,
			"margin_gate_reason": s.custom_margin_gate_reason, "cancel_amend_required": 0,
			"cancel_amend_note": "This workspace never cancels and never amends. Every movement is an immutable DCS Revision against the same submitted document.",
		}

		result["policy"] = {
			"md_threshold_percent": MD_THRESHOLD, "concession_ceiling_percent": CEILING, "margin_floor_percent": MARGIN_FLOOR,
			"basis": "Approval routing is driven by concession from baseline only. The 20% margin floor is an independent commercial gate and is never cleared by an approval decision.",
		}

		result["revisions"] = revisions
		result["lines"] = frappe.get_all(
			"Deal Cost Item", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"},
			fields=["idx", "item_code", "item_name", "customer_item_name", "brand", "item_category", "qty", "cost_rate",
					"cost_amount", "selling_rate", "selling_amount", "gp_value", "gp_percent"], order_by="idx asc",
		)
		result["resources"] = frappe.get_all(
			"Deal Cost Resource", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"},
			fields=["idx", "resource_type", "role", "no_of_persons", "no_of_days", "hours", "cost_rate", "cost_amount",
					"linked_project", "remarks"], order_by="idx asc",
		)

		conv = []
		for rv in revisions:
			conv.append({
				"revision_no": rv.get("revision_no"), "party": rv.get("source"), "who": rv.get("changed_by"),
				"when": rv.get("changed_on"), "message": rv.get("reason"), "technical_impact": rv.get("technical_impact"),
				"selling_from": rv.get("prev_total_selling"), "selling_to": rv.get("new_total_selling"),
				"cost_from": rv.get("prev_total_cost"), "cost_to": rv.get("new_total_cost"),
				"approval_requirement": rv.get("approval_requirement"), "margin_gate": rv.get("margin_gate"),
			})
		result["conversation"] = conv

		target_raw = args.get("customer_target")
		target = None
		if target_raw and target_raw != "":
			target = float(target_raw)
		scn = [scenario("hold", "Hold", wc, ws, baseline, "Do not move. Defend the current position on value.")]
		if target is not None:
			if target > 0:
				mid = (ws + target) / 2.0
				scn.append(scenario("counter", "Counter", wc, mid, baseline, "Meet the customer approximately half way between the current position and their target."))
				scn.append(scenario("accept", "Accept customer target", wc, target, baseline, "Concede fully to the stated customer target."))
		else:
			scn.append(scenario("counter", "Counter (indicative 5% move)", wc, ws * 0.95, baseline, "Indicative only. Enter a customer target to model a real counter."))
		result["scenarios"] = scn
		result["scenario_notice"] = "Scenarios are advisory modelling only. They are not decisions, are not recorded, and no revision exists until Apply and Continue is used."

		p_cost = args.get("probe_cost")
		p_sell = args.get("probe_selling")
		if p_sell or p_cost:
			pc = float(p_cost) if p_cost else wc
			ps = float(p_sell) if p_sell else ws
			if ps > 0:
				result["preview"] = scenario("preview", "Proposed position", pc, ps, baseline, "Live impact of the values currently entered.")

		ci = {"customer": s.customer, "available": 0}
		if s.customer:
			prior = frappe.get_all(
				"Deal Cost Sheet", filters={"customer": s.customer},
				fields=["name", "custom_deal_status", "total_selling", "total_cost", "margin_percent"], order_by="creation desc",
			)
			won = lost = tot = mcount = 0
			msum = 0.0
			for p in prior:
				tot += 1
				st = p.get("custom_deal_status")
				if st == "Won":
					won += 1
				elif st in ("Lost", "Dropped / No Bid"):
					lost += 1
				mv = p.get("margin_percent")
				if mv:
					msum += float(mv)
					mcount += 1
			avg = 0.0
			if mcount > 0:
				avg = int(((msum / mcount) * 1000.0) + 0.5) / 1000.0
			ci = {
				"customer": s.customer, "available": 1, "total_deal_cost_sheets": tot, "won": won, "lost_or_dropped": lost,
				"decided": won + lost, "average_margin_percent": avg,
				"basis": "Counted from real Deal Cost Sheet records for this customer. Win rate is only meaningful once decided deals exist.",
			}
		result["customer_intelligence"] = ci

		result["unavailable"] = [
			{"key": "vendor_intelligence", "label": "Vendor intelligence (response time, historical discount, reliability, alternatives)", "reason": "No supplier or vendor field exists on Deal Cost Item or Deal Cost Resource, and no vendor quotation evidence is captured. There is no real source for vendor behaviour."},
			{"key": "payment_behaviour", "label": "Customer payment behaviour", "reason": "Not sourced from Accounts Receivable in this step. Not fabricated."},
			{"key": "technical_signoff", "label": "Technical sign-off state", "reason": "No technical approval field exists on the Deal Cost Sheet. Technical impact is recorded as free text on each revision only."},
		]
		result["ok"] = 1

	return result
