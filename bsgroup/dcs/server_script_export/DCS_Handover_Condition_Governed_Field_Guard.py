# DCS Handover Condition - Governed Field Guard.
# Conditions are raised, cleared and accepted only through the Award and Handover Workspace,
# which sets doc.flags.dcs_api_write on the document it saves. Any other edit path is refused.

GOVERNED = ["state", "category", "original_category", "domain", "condition_title", "detail", "last_action_note", "assigned_to", "hold_state", "cleared_by", "cleared_on", "clearance_note", "accepted_by", "accepted_on", "acceptance_reason", "acknowledged", "exposure_amount", "exposure_note", "follow_up_date", "auto_generated", "source_key", "raised_by", "raised_on", "dcs", "condition_no"]

prev = doc.get_doc_before_save()

if prev is None:
    # A condition is governed history. It may only be created by a DCS service, each of
    # which validates authority and Deal Cost Sheet permission before raising anything.
    if doc.flags.get("dcs_api_write") != 1:
        frappe.throw("A handover condition may only be raised by a governed Deal Cost Sheet service, which validates authority and Deal Cost Sheet permission first. Direct creation of a handover condition is not permitted.")
    if str(doc.get("state") or "") != "Open":
        frappe.throw("A handover condition must be raised in the Open state. A condition cannot be created already cleared or already accepted as risk.")
    if doc.get("cleared_by") or doc.get("cleared_on") or doc.get("accepted_by") or doc.get("accepted_on"):
        frappe.throw("A handover condition cannot be created with a clearance or acceptance already recorded.")
else:
    if doc.flags.get("dcs_api_write") != 1:
        changed = []
        for f in GOVERNED:
            if str(prev.get(f) or "") != str(doc.get(f) or ""):
                changed.append(f)
        if len(changed) > 0:
            frappe.throw("These handover condition fields are governed by the Award and Handover Workspace and cannot be edited directly: " + "; ".join(changed) + ". Clearing a blocker, accepting a risk or reassigning a domain must go through the workspace so that authority is checked and the action is attributed.")
