"""Only a decision on the current revision authorises a commercial exception."""
from bsgroup.dcs.currency import money_tolerance
import frappe
from frappe.utils import flt

def authorised_position(sheet):
    from bsgroup.dcs.input_validation import position_is_valid
    if not position_is_valid(sheet):
        return False
    from bsgroup.api.dcs.negotiation import requirement
    selling, cost = flt(sheet.custom_working_total_selling), flt(sheet.custom_working_total_cost)
    if selling <= 0:
        return False
    baseline = flt(sheet.custom_baseline_selling)
    concession = (baseline-selling)/baseline*100 if baseline else 0
    required = requirement(concession, (selling-cost)/selling*100)
    if required == "Blocked" or sheet.custom_approval_required == "Blocked":
        return False
    if sheet.custom_approval_state in ("Rejected", "Returned for Rework"):
        return False
    if required == "None" and sheet.custom_approval_required in (None, "", "None"):
        return True
    if sheet.custom_approval_state != "Approved" or sheet.custom_approved_revision_no != sheet.custom_dcs_revision_no:
        return False
    revision = frappe.db.get_value("DCS Revision", sheet.custom_revision_reference,
        ["dcs", "approval_state", "decided_by"], as_dict=True)
    from bsgroup.dcs.manager_approval import route_for, FIXED_POLICY, FIXED_APPROVER
    route = route_for(sheet)
    if route.get("approval_policy") == "Immediate Manager" and (not route.get("approval_manager") or route.approval_manager != sheet.custom_approved_by or route.changed_by == sheet.custom_approved_by):
        return False
    if route.get("approval_policy") == FIXED_POLICY and (route.get("approval_manager") != FIXED_APPROVER or sheet.custom_approved_by != FIXED_APPROVER):
        return False
    return bool(revision and revision.dcs == sheet.name and revision.approval_state == "Approved"
                and revision.decided_by == sheet.custom_approved_by
                and revision.decided_by
                and abs(flt(sheet.custom_approved_total_cost)-cost) <= money_tolerance(sheet.currency)
                and abs(flt(sheet.custom_approved_total_selling)-selling) <= money_tolerance(sheet.currency))
