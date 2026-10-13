"""Living Deal Cost Sheet (``/living-dcs``) read service - port of the retired ``dcs_screen2`` Server Script.

The published Web Page "Living Deal Cost Sheet" still calls ``/api/method/dcs_screen2``. The Server Script
was disabled in the 7 Sep 2026 teardown, so the page failed with "Failed to get method". ``hooks.py`` maps
that bare command to this app endpoint (``override_whitelisted_methods``). Business content is unchanged;
the frozen award baseline and last approved position are added so management sees them on the same page.
"""

import frappe
from bsgroup.dcs.manager_approval import is_assigned_manager, route_for
from bsgroup.dcs.commercial_authority import authorised_position

from bsgroup.api.dcs._common import TECHNICAL_ROLES, get_user_roles, governed_endpoint, has_any

SCREEN2_COMMERCIAL = ["Managing Director", "Commercial Controller", "Sales Manager", "Presales"]
SCREEN2_REDUCED = ["Sales User"]


def _gate(key, label, state, basis):
	return {"key": key, "label": label, "state": state, "basis": basis}


@governed_endpoint("dcs_screen2", ptype="read", idempotent=False)
def dcs_screen2(args):
	result = {"ok": 0, "error": "", "projection": "denied", "user": frappe.session.user}
	dcs_name = args.get("dcs")
	roles = get_user_roles()
	is_comm = has_any(roles, SCREEN2_COMMERCIAL) or bool(dcs_name and frappe.db.exists("Deal Cost Sheet",dcs_name) and is_assigned_manager(dcs_name))
	is_tech = has_any(roles, TECHNICAL_ROLES)

	if not dcs_name:
		result["error"] = "dcs is required."
		return result
	if not frappe.db.exists("Deal Cost Sheet", dcs_name):
		result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
		return result
	if is_comm == 0 and has_any(roles, SCREEN2_REDUCED) == 1:
		result["projection"] = "reduced"
		result["error"] = "Sales User receives the reduced customer-commercial projection. Screen 2 full cost sheet is not available to this role."
		return result
	if is_comm == 0:
		if is_tech == 1:
			result["projection"] = "technical"
			result["error"] = "Screen 2 is the commercial Living Deal Cost Sheet. Technical roles receive the technical projection instead."
		else:
			result["error"] = "You do not hold a commercial role. System Manager administration does not imply commercial authority."
		return result

	result["projection"] = "commercial"
	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("read")
	result["docstatus"] = s.docstatus
	wc, ws, wm = s.custom_working_total_cost or 0, s.custom_working_total_selling or 0, s.custom_working_margin_percent or 0
	initialised = 1
	if (s.custom_dcs_revision_no or 0) < 1:
		initialised = 0
		wc, ws, wm = s.total_cost or 0, s.total_selling or 0, s.margin_percent or 0

	lines = frappe.get_all("Deal Cost Item", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"},
		fields=["idx", "item_code", "item_name", "customer_item_name", "brand", "item_category", "qty", "cost_rate",
				"cost_amount", "selling_rate", "selling_amount", "gp_value", "gp_percent"], order_by="idx asc")
	resources = frappe.get_all("Deal Cost Resource", filters={"parent": dcs_name, "parenttype": "Deal Cost Sheet"},
		fields=["idx", "resource_type", "role", "no_of_persons", "no_of_days", "hours", "cost_rate", "cost_amount",
				"linked_project", "remarks"], order_by="idx asc")
	revisions = frappe.get_all("DCS Revision", filters={"dcs": dcs_name},
		fields=["name", "revision_no", "source", "reason", "changed_by", "changed_on", "prev_total_cost", "new_total_cost",
				"prev_total_selling", "new_total_selling", "prev_margin_percent", "new_margin_percent", "new_concession_percent",
				"gp_movement", "margin_movement", "technical_impact", "approval_requirement", "approval_state", "margin_gate",
				"decided_by", "decided_on", "decision_reason"], order_by="revision_no asc")

	decision = "Review and progress the current negotiated commercial position."
	if s.custom_approval_required == "Blocked":
		decision = "This position cannot be authorised by anyone. Recover it or stop."
	elif s.custom_approval_required == "Manager":
		decision = "Decide whether to send this position to the submitter\'s immediate manager."
	doing_nothing = "The position stays where it is and no approval is sought."
	if s.custom_margin_gate == "Blocked":
		doing_nothing = "The margin remains below the floor. A recorded manager approval is required before award; delivery conditions remain separate."
	result["header"] = {"decision": decision, "money": {"working_total_selling": ws, "working_total_cost": wc,
		"working_gp": ws - wc, "working_margin_percent": wm, "currency": s.currency}, "if_nothing": doing_nothing, "resolvable_here": 1}

	g = []
	g.append(_gate("scope", "Scope defined", "Pass" if (s.subject or s.scope_overview) else "Fail",
		"Subject and/or Scope Overview present on the Deal Cost Sheet." if (s.subject or s.scope_overview) else "No Subject and no Scope Overview recorded."))
	costed = len(lines) > 0 and (s.total_cost or 0) > 0
	g.append(_gate("costed", "Lines costed", "Pass" if costed else "Fail",
		(str(len(lines)) + " cost lines present with a non-zero total cost.") if costed else "No cost lines, or total cost is zero."))
	g.append(_gate("priced", "Position priced", "Pass" if ws > 0 else "Fail",
		"A working selling value is present." if ws > 0 else "No selling value on the working position."))
	if s.custom_margin_gate == "Blocked":
		g.append(_gate("margin_floor", "Margin floor", "Fail", s.custom_margin_gate_reason))
	elif s.custom_margin_gate == "Clear":
		g.append(_gate("margin_floor", "Margin floor", "Pass", s.custom_margin_gate_reason))
	else:
		g.append(_gate("margin_floor", "Margin floor", "Unavailable", "Living position not yet initialised. Apply a revision to evaluate the gate."))
	g.append(_gate("owner", "Deal owner named", "Pass" if s.deal_owner else "Fail",
		("Deal Owner is " + str(s.deal_owner) + ".") if s.deal_owner else "No Deal Owner set on the Deal Cost Sheet."))
	linked = s.customer and s.opportunity
	g.append(_gate("customer", "Customer and opportunity linked", "Pass" if linked else "Fail",
		("Customer " + str(s.customer) + " linked to " + str(s.opportunity) + ".") if linked else "Customer or Opportunity is not linked."))
	result["gates"] = g

	result["unavailable"] = [
		{"key": "cost_age", "label": "Cost age / vendor quote freshness", "reason": "No vendor quotation evidence field exists on Deal Cost Item. There is no real source for the age of a buying price."},
		{"key": "technical_signoff", "label": "Technical sign-off", "reason": "No technical approval field exists on the Deal Cost Sheet. Not fabricated."},
	]
	result["negotiation_guard"] = {"initialised": initialised, "revision_no": s.custom_dcs_revision_no, "revision_reference": s.custom_revision_reference,
		"baseline_selling": s.custom_baseline_selling, "concession_percent_from_baseline": s.custom_concession_percent_from_baseline,
		"approval_required": s.custom_approval_required, "approval_state": s.custom_approval_state, "approval_reason": s.custom_approval_reason,
		"margin_gate": s.custom_margin_gate, "margin_gate_reason": s.custom_margin_gate_reason, "cancel_amend_required": 0,
        "authorised_position": int(authorised_position(s)),
		"boq_matches_living": int(abs((s.total_selling or 0) - ws) <= 0.005 and abs((s.total_cost or 0) - wc) <= 0.005)}
	result["manager_route"] = dict(route_for(s))
	result["approved_position"] = {"revision_no": s.custom_approved_revision_no or 0, "total_cost": s.custom_approved_total_cost,
		"total_selling": s.custom_approved_total_selling, "margin_percent": s.custom_approved_margin_percent,
		"approved_by": s.custom_approved_by, "approved_on": s.custom_approved_on}
	result["award"] = {"state": s.custom_award_state or "Not Awarded", "reference": s.custom_award_reference, "frozen": s.custom_baseline_frozen or 0,
		"frozen_revision_no": s.custom_frozen_revision_no or 0, "frozen_total_cost": s.custom_frozen_total_cost,
		"frozen_total_selling": s.custom_frozen_total_selling, "frozen_margin_percent": s.custom_frozen_margin_percent,
		"delivery_release_state": s.custom_delivery_release_state, "quotation": s.custom_quotation, "deal_status": s.custom_deal_status}
	result["lines"] = lines
	result["resources"] = resources
	result["timeline"] = revisions
	from bsgroup.dcs.margin_bridge import margin_bridge
	result["margin_bridge"] = margin_bridge(s, revisions)

	ctx = {"customer": s.customer, "available": 0}
	if s.customer:
		prior = frappe.get_all("Deal Cost Sheet", filters={"customer": s.customer}, fields=["custom_deal_status"])
		won = sum(1 for p in prior if p.get("custom_deal_status") == "Won")
		lost = sum(1 for p in prior if p.get("custom_deal_status") in ("Lost", "Dropped / No Bid"))
		ctx = {"customer": s.customer, "available": 1, "total_deal_cost_sheets": len(prior), "won": won, "lost_or_dropped": lost,
			"decided": won + lost, "basis": "Counted from real Deal Cost Sheet records for this customer using custom_deal_status."}
	result["customer_context"] = ctx
	result["ok"] = 1
	return result
