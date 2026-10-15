# DCS Revision - Immutability Guard.
# A recorded revision is immutable. The approval decision fields may only be written by dcs_approval_decision,
# which writes them with frappe.db.set_value so that no document hook and no direct edit can forge a decision.

prev = doc.get_doc_before_save()

if prev is not None:
    locked = ["dcs", "revision_no", "changed_by", "changed_on", "source", "reason", "prev_total_cost", "prev_total_selling", "prev_margin_percent", "prev_concession_percent", "new_total_cost", "new_total_selling", "new_margin_percent", "new_concession_percent", "gp_movement", "margin_movement", "technical_impact", "approval_requirement", "margin_gate"]
    for f in locked:
        before = prev.get(f)
        after = doc.get(f)
        if str(before) != str(after):
            frappe.throw("DCS Revision " + str(doc.name) + " is immutable. The field '" + str(f) + "' cannot be changed after the revision is recorded.")
    decision_fields = ["approval_state", "decided_by", "decided_on", "decision_reason"]
    for f in decision_fields:
        if str(prev.get(f) or "") != str(doc.get(f) or ""):
            frappe.throw("The approval decision on DCS Revision " + str(doc.name) + " cannot be written directly. The field '" + str(f) + "' is recorded only by the Approval Workspace, which enforces approval authority. Direct edits are refused so that no approval can be spoofed.")
    final_states = ["Approved", "Rejected"]
    if prev.get("approval_state") in final_states:
        frappe.throw("DCS Revision " + str(doc.name) + " already carries a final decision (" + str(prev.get("approval_state")) + "). A recorded approval decision cannot be altered.")

else:
    # This is an insert. A revision is governed negotiation history and may only be
    # created by dcs_apply_revision, which validates commercial authority and Deal Cost
    # Sheet permission before anything is recorded.
    if not doc.flags.dcs_api_write:
        frappe.throw("A DCS Revision may only be created by the revision service, which validates commercial authority and Deal Cost Sheet permission before recording anything. Direct creation of a revision is not permitted, because it would be forged negotiation history.")
