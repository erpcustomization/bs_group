"""Initialise a submitted sheet without inventing a negotiated movement.

Runs in the caller's transaction. The sheet row is locked before deciding,
so submit, award and negotiation cannot create competing R1 baselines.
"""
import math

import frappe
from frappe.utils import flt, now_datetime

from bsgroup.dcs.governance import diff_changes, make_request_key, record_governance_event, snapshot

FIELDS = [
    "custom_dcs_revision_no", "custom_revision_reference", "custom_working_total_cost",
    "custom_working_total_selling", "custom_working_margin_percent", "custom_baseline_selling",
    "custom_concession_percent_from_baseline", "custom_approval_state", "custom_approval_required",
    "custom_approval_reason", "custom_margin_gate", "custom_margin_gate_reason",
]


def ensure_baseline(dcs_name, source_endpoint):
    """Internal lifecycle service; callers enforce submission/commercial authority."""
    from bsgroup.api.dcs.negotiation import gate_for, pct, why_gate, requirement, why_approval, state_for, rev_state_for

    sheet = frappe.get_doc("Deal Cost Sheet", dcs_name, for_update=True)
    if sheet.docstatus != 1:
        frappe.throw("Commercial baseline initialisation requires a submitted Deal Cost Sheet.")
    if (sheet.custom_dcs_revision_no or 0) >= 1:
        if not frappe.db.get_value("DCS Revision", {"name": sheet.custom_revision_reference, "dcs": dcs_name,
                                                     "revision_no": sheet.custom_dcs_revision_no}, "name", for_update=True):
            frappe.throw("The commercial revision reference is inconsistent. No baseline was overwritten.")
        return {"initialised": 0, "revision": sheet.custom_revision_reference}
    if frappe.db.exists("DCS Revision", {"dcs": dcs_name}):
        frappe.throw("Revision history already exists on this revision-zero sheet. Reconcile it before initialising.")
    if sheet.custom_baseline_frozen or sheet.custom_award_state == "Awarded" or sheet.custom_approved_revision_no:
        frappe.throw("Award or approval history exists on this revision-zero sheet. No baseline was overwritten.")
    if sheet.custom_approval_required not in (None, "", "None") or sheet.custom_approval_state not in (
        None, "", "Not Started", "In Negotiation"
    ):
        frappe.throw("An existing commercial approval state must be reconciled before baseline initialisation.")

    cost, selling = flt(sheet.total_cost), flt(sheet.total_selling)
    if not math.isfinite(cost) or not math.isfinite(selling) or cost < 0 or selling <= 0:
        frappe.throw("Valid submitted cost and a positive selling total are required to initialise the commercial baseline.")
    for field, expected in (("custom_working_total_cost", cost), ("custom_working_total_selling", selling),
                            ("custom_baseline_selling", selling)):
        value = flt(sheet.get(field))
        if value and abs(value - expected) > 0.005:
            frappe.throw("Unrecorded commercial figures differ from the submitted baseline. Reconcile them before initialising.")
    if flt(sheet.custom_concession_percent_from_baseline):
        frappe.throw("An unrecorded concession exists. No baseline was overwritten.")

    margin = pct(selling - cost, selling)
    before = snapshot("Deal Cost Sheet", dcs_name, FIELDS)
    req = requirement(0, margin)
    rev = frappe.get_doc({
        "doctype": "DCS Revision", "dcs": dcs_name, "revision_no": 1,
        "changed_by": frappe.session.user, "changed_on": now_datetime(), "source": "Internal",
        "reason": "Commercial baseline initialised from submitted totals; no negotiated change.",
        "prev_total_cost": cost, "prev_total_selling": selling, "prev_margin_percent": margin,
        "prev_concession_percent": 0, "new_total_cost": cost, "new_total_selling": selling,
        "new_margin_percent": margin, "new_concession_percent": 0,
        "gp_movement": 0, "margin_movement": 0, "approval_requirement": req,
        "approval_state": rev_state_for(req), "margin_gate": gate_for(margin),
    })
    rev.flags.dcs_api_write = 1
    from bsgroup.api.dcs.boq_revision import line_history
    for row in line_history(sheet, sheet, baseline=True):
        rev.append("boq_lines", row)
    rev.insert(ignore_permissions=True)
    values = {
        "custom_dcs_revision_no": 1, "custom_revision_reference": rev.name,
        "custom_working_total_cost": cost, "custom_working_total_selling": selling,
        "custom_working_margin_percent": margin, "custom_baseline_selling": selling,
        "custom_concession_percent_from_baseline": 0, "custom_approval_state": state_for(req) if req != "None" else "Not Started",
        "custom_approval_required": req,
        "custom_approval_reason": why_approval(0, margin),
        "custom_margin_gate": gate_for(margin), "custom_margin_gate_reason": why_gate(margin),
    }
    frappe.db.set_value("Deal Cost Sheet", dcs_name, values, update_modified=True)
    event = record_governance_event(
        dcs_name, "DCS_BASELINE_INITIALISED", action_label="Initialise the submitted commercial baseline",
        source_endpoint=source_endpoint, reason=rev.reason, revision_no=1, revision_reference=rev.name,
        changes=diff_changes(FIELDS, before, snapshot("Deal Cost Sheet", dcs_name, FIELDS), "Deal Cost Sheet", dcs_name),
        request_key=make_request_key("dcs_baseline_initialisation", {"dcs": dcs_name}),
    )
    return {"initialised": 1, "revision": rev.name, "governance_event": event}
