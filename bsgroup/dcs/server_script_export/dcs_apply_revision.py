# dcs_apply_revision
# Applies a negotiation movement to the LIVING Deal Cost Sheet.
# Creates an immutable DCS Revision entry. Never cancels, never amends.
# Approval routing is driven by concession from baseline ONLY.
# The 20% margin floor is an INDEPENDENT commercial gate, never an approver-routing rule.

def pct(numer, denom):
    if not denom:
        return 0.0
    return int((((numer * 1.0) / denom) * 100000.0) + 0.5) / 1000.0

def num(v, fallback):
    if v is None:
        return fallback
    if v == "":
        return fallback
    return float(v)

def requirement(concession):
    if concession > 26:
        return "Blocked"
    if concession >= 16:
        return "Managing Director"
    return "None"

def why_approval(concession):
    if concession > 26:
        return "Concession " + str(concession) + "% from baseline is above the 26% ceiling. No approver may authorise this position."
    if concession >= 16:
        return "Concession " + str(concession) + "% from baseline is at or above 16%, which requires Managing Director approval."
    return "Concession " + str(concession) + "% from baseline is below 16%. No discount sign-off is required."

def gate_for(margin):
    if margin < 20:
        return "Blocked"
    return "Clear"

def why_gate(margin):
    if margin < 20:
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
    rev.changed_on = frappe.utils.now_datetime()
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
        rev.insert(ignore_permissions=True)
    except Exception as e:
        return "COLLISION::" + str(e)
    return rev.name

# ---- authority model (server-side, never client-side only) ----
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
# --- D2a PHASE 2 SNAPSHOT COMPANIONS (shared, byte identical across Phase 2 endpoints) ---
# Pure read helpers used to prove the actual committed movement. A snapshot is taken server
# side immediately before the governed mutation and a second one immediately after it has
# succeeded, so every recorded before -> after pair is a real committed change rather than an
# intention. Fields that did not move are dropped, so a true no-op produces no event at all.
def dcs_audit_snapshot(a_dt, a_dn, a_fields):
	snap = {}
	if not a_dn:
		return snap
	row = frappe.db.get_value(a_dt, a_dn, a_fields, as_dict=True)
	if row is None:
		return snap
	for f in a_fields:
		v = row.get(f)
		if v is None:
			v = ""
		snap[f] = str(v)
	return snap
def dcs_audit_changes(a_fields, a_before, a_after, a_dt, a_dn):
	moved = []
	for f in a_fields:
		ov = a_before.get(f)
		nv = a_after.get(f)
		if ov is None:
			ov = ""
		if nv is None:
			nv = ""
		if str(ov) == str(nv):
			continue
		moved.append({"field": f, "old": ov, "new": nv, "dt": a_dt, "dn": a_dn})
	return moved
# --- END D2a PHASE 2 SNAPSHOT COMPANIONS ---
CUSTOMER_SIDE = ["Sales User", "Sales Manager", "Commercial Controller", "Managing Director"]
VENDOR_SIDE = ["Presales", "Sales Manager", "Commercial Controller", "Managing Director"]

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

result = {"ok": 0, "error": "", "revision": "", "initialised": 0, "state": {}}

dcs_name = frappe.form_dict.get("dcs")
source = frappe.form_dict.get("source")
reason = frappe.form_dict.get("reason")
tech_impact = frappe.form_dict.get("technical_impact")
valid_sources = ["Customer", "Vendor", "Technical", "Internal"]

if not dcs_name:
    result["error"] = "dcs is required."
elif not reason:
    result["error"] = "A reason is required for every revision. Revisions are never recorded silently."
elif source not in valid_sources:
    result["error"] = "source must be one of Customer, Vendor, Technical, Internal."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
    result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif frappe.db.get_value("Deal Cost Sheet", dcs_name, "docstatus") == 2:
    result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
else:
    sheet = frappe.get_doc("Deal Cost Sheet", dcs_name)
    sheet.check_permission("write")

    my_roles = get_user_roles(frappe.session.user)
    can_customer = has_any(my_roles, CUSTOMER_SIDE)
    can_vendor = has_any(my_roles, VENDOR_SIDE)

    rev_no = sheet.custom_dcs_revision_no or 0
    baseline = sheet.custom_baseline_selling or 0
    init_done = 0

    # The baseline initialisation below writes a governed DCS Revision under service
    # authority. It must therefore never run before the commercial authority gate.
    # A caller holding neither customer-side nor vendor-side authority falls through
    # to the else branch and is refused below without any record being created.
    if rev_no < 1 and (can_customer == 1 or can_vendor == 1):
        base_cost = sheet.total_cost or 0
        base_sell = sheet.total_selling or 0
        baseline = base_sell
        base_margin = pct((base_sell - base_cost), base_sell)
        write_revision(dcs_name, 1, "Internal", "Commercial baseline established from the existing submitted Deal Cost Sheet totals. No commercial change was made by this entry.", base_cost, base_sell, base_margin, 0.0, base_cost, base_sell, base_margin, 0.0, "", "None", "Not Required", gate_for(base_margin))
        rev_no = 1
        init_done = 1
        prev_cost = base_cost
        prev_sell = base_sell
        prev_margin = base_margin
        prev_con = 0.0
    else:
        prev_cost = sheet.custom_working_total_cost or 0
        prev_sell = sheet.custom_working_total_selling or 0
        prev_margin = sheet.custom_working_margin_percent or 0
        prev_con = sheet.custom_concession_percent_from_baseline or 0

    new_cost = num(frappe.form_dict.get("new_total_cost"), prev_cost)
    new_sell = num(frappe.form_dict.get("new_total_selling"), prev_sell)

    sell_moved = 0
    cost_moved = 0
    if new_sell != prev_sell:
        sell_moved = 1
    if new_cost != prev_cost:
        cost_moved = 1

    if can_customer == 0 and can_vendor == 0:
        result["error"] = "You do not hold a commercial-edit role. Technical roles and System Manager administration cannot revise a commercial position."
    elif sell_moved == 1 and can_customer == 0:
        result["error"] = "Your role may not move the customer-side selling position. Presales may revise buying cost only."
    elif cost_moved == 1 and can_vendor == 0:
        result["error"] = "Your role may not move the vendor-side buying cost. Sales User may revise the customer-side selling position only."
    elif new_sell <= 0:
        result["error"] = "Proposed selling value must be greater than zero."
    else:
        only_init = 0
        if new_cost == prev_cost and new_sell == prev_sell and init_done == 1:
            only_init = 1

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
            rev_name = write_revision(dcs_name, next_no, source, reason, prev_cost, prev_sell, prev_margin, prev_con, new_cost, new_sell, new_margin, new_con, tech_impact, req, rev_state_for(req), mg)
        if str(rev_name)[0:11] == "COLLISION::":
            result["ok"] = 0
            result["error"] = "Another user recorded a revision on this deal a moment ago, so this movement was not saved. Reload the workspace to see the current position and apply the movement again. Nothing was lost and no revision was overwritten."
        else:

            # D2a Phase 2: snapshot the governed fields server side immediately before the write.
            D2A_FIELDS = ["custom_dcs_revision_no", "custom_revision_reference", "custom_working_total_cost", "custom_working_total_selling", "custom_working_margin_percent", "custom_concession_percent_from_baseline", "custom_baseline_selling", "custom_approval_state", "custom_approval_required", "custom_approval_reason", "custom_margin_gate", "custom_margin_gate_reason"]
            d2a_before = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
            frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_dcs_revision_no": next_no, "custom_revision_reference": rev_name, "custom_working_total_cost": new_cost, "custom_working_total_selling": new_sell, "custom_working_margin_percent": new_margin, "custom_concession_percent_from_baseline": new_con, "custom_baseline_selling": baseline, "custom_approval_state": st, "custom_approval_required": req, "custom_approval_reason": appr_text, "custom_margin_gate": mg, "custom_margin_gate_reason": gate_text}, update_modified=True)

            # D2a Phase 2: the governed write above has succeeded, so record the committed movement.
            d2a_after = dcs_audit_snapshot("Deal Cost Sheet", dcs_name, D2A_FIELDS)
            d2a_moved = dcs_audit_changes(D2A_FIELDS, d2a_before, d2a_after, "Deal Cost Sheet", dcs_name)
            result["governance_event"] = dcs_audit_event(dcs_name, "DCS_REVISION_APPLIED", "Apply a negotiated revision to the living commercial position", "dcs_apply_revision", reason, next_no, rev_name, rev_name, d2a_moved)
            result["ok"] = 1
            result["initialised"] = init_done
            result["revision"] = rev_name
            result["state"] = {"revision_no": next_no, "working_total_cost": new_cost, "working_total_selling": new_sell, "working_margin_percent": new_margin, "concession_percent_from_baseline": new_con, "baseline_selling": baseline, "approval_state": st, "approval_required": req, "approval_reason": appr_text, "margin_gate": mg, "margin_gate_reason": gate_text, "gp_movement": (new_sell - new_cost) - (prev_sell - prev_cost), "docstatus_unchanged": sheet.docstatus}

frappe.response["message"] = result

# --- Native timeline + notification emit (go-live Day 2) ---
try:
    if result.get("ok"):
        tlname = frappe.form_dict.get("dcs")
        tlstate = result.get("state") or {}
        tltext = ""
        tlreq = tlstate.get("approval_required")
        if tlreq:
            if tlreq != "None":
                tltext = "Approval required: " + str(tlreq) + " - revision " + str(tlstate.get("revision_no")) + " - state " + str(tlstate.get("approval_state"))
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
