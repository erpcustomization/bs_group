# dcs_approval_decision
# Records an approval decision against the LIVING Deal Cost Sheet.
# Never cancels, never amends, never deletes. Authority is enforced server side.
# Commercial Controller: Endorse, Return for Rework.  Managing Director: Approve, Return for Rework, Reject.

MD = "Managing Director"
CC = "Commercial Controller"

def get_user_roles(u):
	rows = frappe.get_all("Has Role", filters={"parent": u, "parenttype": "User"}, fields=["role"])
	out = []
	for r in rows:
		out.append(r.get("role"))
	return out

# --- D2a CANONICAL GOVERNED AUDIT HELPER (shared, byte identical across instrumented endpoints) ---
# Builds and inserts one append-only DCS Governance Event plus one child row per genuinely
# changed field. Trusted, server-derived inputs only: no caller supplied actor, role or
# authority is accepted here or anywhere downstream. Actor, timestamp, outcome and
# correlation id are derived by the DCS Governance Event Insert Guard, which also drops
# unchanged rows and resolves field labels and value types from live metadata.
# This helper never commits. It participates in the caller transaction so that a business
# mutation and its audit event either both survive or both roll back.
def dcs_audit_event(a_dcs, a_code, a_label, a_endpoint, a_reason, a_rev_no, a_rev_ref, a_evid, a_changes):
	kept = []
	for ch in a_changes:
		ov = ch.get("old")
		nv = ch.get("new")
		if ov is None:
			ov = ""
		if nv is None:
			nv = ""
		if str(ov) == str(nv):
			continue
		kept.append({"fieldname": ch.get("field"), "target_doctype": ch.get("dt") or "Deal Cost Sheet", "target_name": ch.get("dn") or a_dcs, "old_value": str(ov), "new_value": str(nv)})
	if len(kept) < 1:
		return ""
	ev = frappe.new_doc("DCS Governance Event")
	ev.dcs = a_dcs
	ev.event_code = a_code
	ev.action_label = a_label
	ev.source_endpoint = a_endpoint
	ev.reason = a_reason
	ev.revision_no = a_rev_no
	ev.revision_reference = a_rev_ref
	ev.evidence_reference = a_evid
	ev.changes = json.dumps(kept)
	ev.change_count = len(kept)
	ev.flags.dcs_audit_write = 1
	ev.insert(ignore_permissions=True)
	return ev.name
# --- END D2a CANONICAL GOVERNED AUDIT HELPER ---

result = {"ok": 0, "error": "", "action": "", "state": {}}

dcs_name = frappe.form_dict.get("dcs")
action = frappe.form_dict.get("action")
reason = frappe.form_dict.get("reason")
valid = ["Endorse", "Approve", "Return for Rework", "Reject"]
needs_reason = ["Return for Rework", "Reject"]

roles = get_user_roles(frappe.session.user)
is_md = 0
is_cc = 0
if MD in roles:
	is_md = 1
if CC in roles:
	is_cc = 1

if not dcs_name:
	result["error"] = "dcs is required."
elif action not in valid:
	result["error"] = "action must be one of Endorse, Approve, Return for Rework, Reject."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
	result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif frappe.db.get_value("Deal Cost Sheet", dcs_name, "docstatus") == 2:
	result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
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
		now = frappe.utils.now_datetime()
		me = frappe.session.user
		new_state = ""
		patch = {}
		if action == "Endorse":
			new_state = "Endorsed - Pending MD"
			patch = {"custom_approval_state": new_state, "custom_endorsed_by": me, "custom_endorsed_on": now, "custom_last_decision_reason": reason or "Endorsed by the Commercial Controller. The Managing Director remains the final approver."}
		elif action == "Approve":
			new_state = "Approved"
			patch = {"custom_approval_state": new_state, "custom_approved_revision_no": s.custom_dcs_revision_no, "custom_approved_total_cost": s.custom_working_total_cost, "custom_approved_total_selling": s.custom_working_total_selling, "custom_approved_margin_percent": s.custom_working_margin_percent, "custom_approved_by": me, "custom_approved_on": now, "custom_last_decision_reason": reason or "Approved by the Managing Director."}
		elif action == "Return for Rework":
			new_state = "Returned for Rework"
			patch = {"custom_approval_state": new_state, "custom_last_decision_reason": reason}
		else:
			new_state = "Rejected"
			patch = {"custom_approval_state": new_state, "custom_last_decision_reason": reason}

		# D2a: capture the pre-mutation state of both targets, server side, before any write.
		d2a_dcs_keys = ["custom_approval_state", "custom_endorsed_by", "custom_endorsed_on", "custom_approved_revision_no", "custom_approved_total_cost", "custom_approved_total_selling", "custom_approved_margin_percent", "custom_approved_by", "custom_approved_on", "custom_last_decision_reason"]
		d2a_dcs_before = {}
		for pk in d2a_dcs_keys:
			if pk in patch:
				d2a_dcs_before[pk] = s.get(pk)
		d2a_rev_doc = frappe.get_doc("DCS Revision", rev_ref)
		d2a_rev_before = {}
		d2a_rev_before["approval_state"] = d2a_rev_doc.get("approval_state")
		d2a_rev_before["decided_by"] = d2a_rev_doc.get("decided_by")
		d2a_rev_before["decided_on"] = d2a_rev_doc.get("decided_on")
		d2a_rev_before["decision_reason"] = d2a_rev_doc.get("decision_reason")
		d2a_rev_reason = reason or ("Recorded by " + str(action) + ".")

		frappe.db.set_value("DCS Revision", rev_ref, {"approval_state": new_state, "decided_by": me, "decided_on": now, "decision_reason": reason or ("Recorded by " + str(action) + ".")}, update_modified=True)

		frappe.db.set_value("Deal Cost Sheet", dcs_name, patch, update_modified=True)

		# D2a: canonical governed audit event, in the same transaction as the two writes above.
		# Every successful branch is covered, including the Commercial Controller endorsement,
		# which produces no Comment. Existing Comments and Notification Logs are left untouched.
		d2a_codes = {"Endorse": "DCS_APPROVAL_ENDORSED", "Approve": "DCS_APPROVAL_APPROVED", "Return for Rework": "DCS_APPROVAL_RETURNED_FOR_REWORK", "Reject": "DCS_APPROVAL_REJECTED"}
		d2a_labels = {"Endorse": "Endorse - Commercial Controller", "Approve": "Approve - Managing Director", "Return for Rework": "Return for Rework", "Reject": "Reject - Managing Director"}
		d2a_changes = []
		for pk in d2a_dcs_keys:
			if pk in patch:
				d2a_changes.append({"field": pk, "old": d2a_dcs_before.get(pk), "new": patch.get(pk), "dt": "Deal Cost Sheet", "dn": dcs_name})
		d2a_changes.append({"field": "approval_state", "old": d2a_rev_before.get("approval_state"), "new": new_state, "dt": "DCS Revision", "dn": rev_ref})
		d2a_changes.append({"field": "decided_by", "old": d2a_rev_before.get("decided_by"), "new": me, "dt": "DCS Revision", "dn": rev_ref})
		d2a_changes.append({"field": "decided_on", "old": d2a_rev_before.get("decided_on"), "new": now, "dt": "DCS Revision", "dn": rev_ref})
		d2a_changes.append({"field": "decision_reason", "old": d2a_rev_before.get("decision_reason"), "new": d2a_rev_reason, "dt": "DCS Revision", "dn": rev_ref})
		result["governance_event"] = dcs_audit_event(dcs_name, d2a_codes.get(action) or "DCS_APPROVAL_DECISION", d2a_labels.get(action) or str(action), "dcs_approval_decision", reason or "", s.custom_dcs_revision_no, rev_ref, rev_ref, d2a_changes)

		gate_note = ""
		if s.custom_margin_gate == "Blocked":
			gate_note = "The margin gate remains BLOCKED. This decision does not clear it."
		result["ok"] = 1
		result["action"] = action
		result["state"] = {"approval_state": new_state, "revision": rev_ref, "decided_by": me, "approval_required": req, "margin_gate": s.custom_margin_gate, "margin_gate_note": gate_note, "docstatus_unchanged": s.docstatus, "authorised_position": {"total_cost": s.custom_working_total_cost, "total_selling": s.custom_working_total_selling, "margin_percent": s.custom_working_margin_percent}}

frappe.response["message"] = result

# --- Native timeline + notification emit (go-live Day 2) ---
try:
    if result.get("ok"):
        tlname = frappe.form_dict.get("dcs")
        tlstate = result.get("state") or {}
        tltext = ""
        tlas = tlstate.get("approval_state")
        if tlas == "Returned for Rework":
            tltext = "Approval returned for rework - revision " + str(tlstate.get("revision"))
        if tlas == "Approved":
            tltext = "APPROVED - " + str(tlname) + " revision " + str(tlstate.get("revision")) + " - decision " + str(result.get("action")) + " - approver " + str(tlstate.get("decided_by")) + " - at " + str(tlstate.get("decided_on")) + " - resulting state " + str(tlas)
        if tlas == "Rejected":
            tltext = "REJECTED - " + str(tlname) + " revision " + str(tlstate.get("revision")) + " - decision " + str(result.get("action")) + " - approver " + str(tlstate.get("decided_by")) + " - at " + str(tlstate.get("decided_on")) + " - reason " + str(tlstate.get("decision_reason")) + " - resulting state " + str(tlas)
        if tlname:
            if tltext:
                tlc = frappe.new_doc("Comment")
                tlc.comment_type = "Info"
                tlc.reference_doctype = "Deal Cost Sheet"
                tlc.reference_name = tlname
                tlc.content = tltext
                tlc.insert(ignore_permissions=True)
                tlusers = []
                tlo = frappe.db.get_value("Deal Cost Sheet", tlname, "deal_owner")
                tld = frappe.db.get_value("Deal Cost Sheet", tlname, "custom_delivery_owner")
                if tlo:
                    tlusers.append(tlo)
                if tld:
                    if tld not in tlusers:
                        tlusers.append(tld)
                for tlu in tlusers:
                    if tlu != frappe.session.user:
                        tln = frappe.new_doc("Notification Log")
                        tln.for_user = tlu
                        tln.from_user = frappe.session.user
                        tln.type = "Alert"
                        tln.document_type = "Deal Cost Sheet"
                        tln.document_name = tlname
                        tln.subject = tltext
                        tln.insert(ignore_permissions=True)
except Exception as e:
    pass
