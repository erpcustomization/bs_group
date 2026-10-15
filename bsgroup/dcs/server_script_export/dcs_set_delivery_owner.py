# dcs_set_delivery_owner
# A named delivery owner is mandatory for every release, including a Managing Director override.

COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]
TECHNICAL_ROLES = ["Technical Engineer", "Project Engineer", "Project Manager", "Operations Manager"]
MD = "Managing Director"
CC = "Commercial Controller"

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

def absf(v):
	if v < 0:
		return 0 - v
	return v

def next_condition_no(sheet_name):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name}, fields=["condition_no"], order_by="condition_no desc", limit_page_length=1)
	n = 0
	for r in rows:
		n = r.get("condition_no") or 0
	return n + 1

def find_condition(sheet_name, key):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "source_key": key}, fields=["name", "state", "category"], limit_page_length=1)
	for r in rows:
		return r
	return None

def raise_condition(sheet_name, key, title, category, domain, detail):
	existing = find_condition(sheet_name, key)
	if existing is not None:
		if existing.get("state") == "Open":
			return existing.get("name")
		if existing.get("state") == "Accepted Risk":
			return existing.get("name")
		return existing.get("name")
	c = frappe.new_doc("DCS Handover Condition")
	c.dcs = sheet_name
	c.condition_no = next_condition_no(sheet_name)
	c.condition_title = title
	c.category = category
	c.original_category = category
	c.domain = domain
	c.state = "Open"
	c.detail = detail
	c.raised_by = frappe.session.user
	c.raised_on = frappe.utils.now_datetime()
	c.auto_generated = 1
	c.source_key = key
	c.insert()
	return c.name

def open_blockers(sheet_name):
	rows = frappe.get_all("DCS Handover Condition", filters={"dcs": sheet_name, "category": "Blocker", "state": "Open"}, fields=["name", "condition_title", "domain"])
	return rows

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

result = {"ok": 0, "error": "", "state": {}}
dcs_name = frappe.form_dict.get("dcs")
owner_user = frappe.form_dict.get("delivery_owner")
roles = get_user_roles(frappe.session.user)

if not dcs_name:
	result["error"] = "dcs is required."
elif not frappe.db.exists("Deal Cost Sheet", dcs_name):
	result["error"] = "Deal Cost Sheet " + str(dcs_name) + " does not exist."
elif frappe.db.get_value("Deal Cost Sheet", dcs_name, "docstatus") == 2:
	result["error"] = "This Deal Cost Sheet is cancelled and cannot be modified."
elif has_any(roles, COMMERCIAL_ROLES) == 0 and has_any(roles, TECHNICAL_ROLES) == 0:
	result["error"] = "You hold neither a commercial nor a technical role."
elif not owner_user:
	result["error"] = "delivery_owner is required. Delivery can never be released without a named owner."
elif not frappe.db.exists("User", owner_user):
	result["error"] = "User " + str(owner_user) + " does not exist. The delivery owner must be a real named user."
else:
	s = frappe.get_doc("Deal Cost Sheet", dcs_name)
	s.check_permission("write")
	if not s.custom_baseline_frozen:
		result["error"] = "No award has been recorded. There is nothing to hand over yet."
	else:
		# D2a: capture the pre-mutation state server side, immediately before the write.
		d2a_prev_owner = s.custom_delivery_owner
		d2a_hc_ref = ""
		d2a_rel_old = ""
		d2a_rel_new = ""
		frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_delivery_owner": owner_user}, update_modified=True)
		c = find_condition(dcs_name, "delivery_owner")
		if c is not None:
			if c.get("state") == "Open":
				d = frappe.get_doc("DCS Handover Condition", c.get("name"))
				d.state = "Cleared"
				d.cleared_by = frappe.session.user
				d.cleared_on = frappe.utils.now_datetime()
				d.clearance_note = "Named delivery owner recorded as " + str(owner_user) + "."
				d.assigned_to = owner_user
				d.flags.dcs_api_write = 1
				d.save()
				d2a_hc_ref = c.get("name")
		blk = open_blockers(dcs_name)
		cur = s.custom_delivery_release_state
		if cur not in ["Released", "Released with MD Override"]:
			rel = "Pending"
			if len(blk) > 0:
				rel = "Blocked"
			d2a_rel_old = cur
			d2a_rel_new = rel
			frappe.db.set_value("Deal Cost Sheet", dcs_name, {"custom_delivery_release_state": rel}, update_modified=True)
			result["state"] = {"delivery_owner": owner_user, "delivery_release_state": rel, "open_blockers": len(blk)}
		else:
			result["state"] = {"delivery_owner": owner_user, "delivery_release_state": cur}
		# D2a: canonical governed audit event. Same transaction as the business mutation.
		# A no-op (owner unchanged) produces no event and no misleading field-change row.
		d2a_changes = [{"field": "custom_delivery_owner", "old": d2a_prev_owner, "new": owner_user}]
		if d2a_rel_new:
			d2a_changes.append({"field": "custom_delivery_release_state", "old": d2a_rel_old, "new": d2a_rel_new})
		result["governance_event"] = dcs_audit_event(dcs_name, "DCS_DELIVERY_OWNER_ASSIGNED", "Assign the delivery owner", "dcs_set_delivery_owner", "", s.custom_dcs_revision_no, s.custom_revision_reference, d2a_hc_ref, d2a_changes)
		result["ok"] = 1

frappe.response["message"] = result
