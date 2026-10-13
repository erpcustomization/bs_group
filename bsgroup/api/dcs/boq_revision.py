"""Governed changes to submitted item/resource rows, with immutable line history.

Ordinary document saves remain locked. Totals-only legacy movements are never
silently added to or removed from a replacement BOQ.
"""
import json
import math

import frappe
from frappe.utils import flt, now_datetime

from bsgroup.api.dcs._common import (
    CUSTOMER_SIDE, VENDOR_SIDE, MD, get_user_roles, has_any, governed_endpoint,
    audit_event, diff_changes, snapshot, truthy_flag,
)
from bsgroup.api.dcs.negotiation import (
    D2A_FIELDS, NO_COMMERCIAL_EDIT, pct, requirement, gate_for, state_for,
    rev_state_for, why_approval, why_gate, write_revision,
)

ITEM_FIELDS = ["item_code", "description", "qty", "cost_rate", "selling_rate"]
RESOURCE_FIELDS = ["resource_type", "role", "no_of_persons", "no_of_days", "hours", "cost_rate", "remarks"]
_SAVE_TOKEN = object()


def authorised_save(doc):
    return doc.flags.get("bsg_boq_revision") is _SAVE_TOKEN


def boq_managed(name, locking=False):
    """Once line revisions start, totals-only writes cannot split totals from rows.

    Amendments inherit this rule. Read-only panels do not take write locks;
    mutating callers use current locking reads after locking the sheet.
    """
    seen = set()
    while name and name not in seen:
        seen.add(name)
        sql = """SELECT l.name FROM `tabDCS Revision Line` l
            INNER JOIN `tabDCS Revision` r ON r.name=l.parent
            WHERE r.dcs=%s AND l.operation IN ('Add','Update','Remove') LIMIT 1"""
        if locking:
            sql += " FOR UPDATE"
        if frappe.db.sql(sql, (name,)):
            return True
        name = frappe.db.get_value("Deal Cost Sheet", name, "amended_from", for_update=locking)
    return False


def row_values(row, kind):
    fields = ITEM_FIELDS if kind == "Item" else RESOURCE_FIELDS
    return {**{field: row.get(field) for field in fields}, "position": row.idx}


def line_history(before, after, baseline=False):
    rows = []
    for table, kind in [("items", "Item"), ("resources", "Resource")]:
        old = {r.name: r for r in before.get(table) or []}
        new = {r.name: r for r in after.get(table) or []}
        for key in dict.fromkeys(list(old) + list(new)):
            a, b = old.get(key), new.get(key)
            av, bv = row_values(a, kind) if a else {}, row_values(b, kind) if b else {}
            if av == bv and not baseline:
                continue
            pc, nc = flt(a.cost_amount) if a else 0, flt(b.cost_amount) if b else 0
            ps = flt(a.selling_amount) if a and kind == "Item" else 0
            ns = flt(b.selling_amount) if b and kind == "Item" else 0
            rows.append({"line_type": kind, "row_key": key,
                "operation": "Baseline" if baseline else ("Remove" if not b else "Add" if not a else "Update"),
                "label": (b or a).get("description" if kind == "Item" else "role"),
                "before_values": json.dumps(av, sort_keys=True, default=str),
                "after_values": json.dumps(bv, sort_keys=True, default=str),
                "previous_cost": pc, "new_cost": nc, "cost_delta": flt(nc-pc, 2),
                "previous_selling": ps, "new_selling": ns, "selling_delta": flt(ns-ps, 2)})
    return rows


def _number(value, label, positive=False):
    if isinstance(value, bool):
        frappe.throw(f"{label} must be a number, not a checkbox value.")
    try:
        number = float(value or 0)
    except (ValueError, TypeError):
        frappe.throw(f"{label} must be a number.")
    if not math.isfinite(number) or number < 0 or (positive and number <= 0):
        frappe.throw(f"{label} must be finite and {'positive' if positive else 'non-negative'}.")
    return number


def _rows(raw, table):
    try:
        raw = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        frappe.throw(f"{table} must be a JSON row list.")
    if not isinstance(raw, list) or len(raw) > 500 or any(not isinstance(r, dict) for r in raw):
        frappe.throw(f"{table} must contain at most 500 row objects.")
    return raw


def _proposal(sheet, args, roles):
    proposed = frappe.get_doc(sheet.as_dict())
    for table, kind, fields in [("items", "Item", ITEM_FIELDS), ("resources", "Resource", RESOURCE_FIELDS)]:
        existing = {r.name: r for r in sheet.get(table) or []}
        seen = set()
        rows = _rows(args.get(table), table)
        if table == "items" and not rows:
            frappe.throw("A BOQ revision must retain at least one item.")
        proposed.set(table, [])
        for raw in rows:
            if set(raw) - set(fields + ["row_name"]):
                frappe.throw(f"Unsupported fields in {table}; derived/control fields cannot be supplied.")
            key = raw.get("row_name")
            if key and not isinstance(key, str):
                frappe.throw("Row names must be strings.")
            if key and (key not in existing or key in seen):
                frappe.throw("A row belongs to another sheet, is stale, or is repeated.")
            if key:
                seen.add(key)
            values = existing[key].as_dict() if key else {}
            for field in fields:
                if field in raw:
                    values[field] = raw[field]
            for field in (["item_code", "description"] if kind == "Item" else ["resource_type", "role", "remarks"]):
                if values.get(field) is not None and not isinstance(values[field], str):
                    frappe.throw(f"{field} must be text.")
            if kind == "Item":
                item = frappe.db.get_value("Item", values.get("item_code"), ["name", "disabled", "item_name", "brand"], as_dict=True)
                if not item or item.disabled:
                    frappe.throw("Every item must exist and be enabled.")
                if not key or values.get("item_code") != existing[key].item_code:
                    values["item_name"], values["brand"] = item.item_name, item.brand
                values["qty"] = _number(values.get("qty"), "Item quantity", positive=True)
                for field in ["cost_rate", "selling_rate"]:
                    values[field] = _number(values.get(field), field)
            else:
                if values.get("resource_type") not in ["Internal", "Outsourced"] or not values.get("role"):
                    frappe.throw("Every labour row requires an Internal/Outsourced type and role.")
                for field in ["no_of_persons", "no_of_days", "hours", "cost_rate"]:
                    values[field] = _number(values.get(field), field)
                days_based = values["no_of_persons"] > 0 and values["no_of_days"] > 0
                hours_based = values["hours"] > 0
                if days_based == hours_based or (not days_based and (values["no_of_persons"] or values["no_of_days"])):
                    frappe.throw("Use either persons × days or hours for labour, not both.")
            row = proposed.append(table, values)
            row.idx = len(proposed.get(table))
            if not key:
                row.name = frappe.generate_hash(length=10)
                row.currency = sheet.currency
            numeric = ["qty", "cost_rate", "selling_rate"] if kind == "Item" else ["no_of_persons", "no_of_days", "hours", "cost_rate"]
            for field in numeric:
                row.set(field, flt(row.get(field), row.precision(field)))
            if kind == "Item" and row.qty <= 0:
                frappe.throw("Item quantity must remain positive at the field's stored precision.")
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import calculate_deal_financials
    calculate_deal_financials(proposed)
    history = line_history(sheet, proposed)
    if not history:
        return proposed, history
    can_sell, can_cost = has_any(roles, CUSTOMER_SIDE), has_any(roles, VENDOR_SIDE)
    for h in history:
        a, b = json.loads(h["before_values"]), json.loads(h["after_values"])
        structure = h["line_type"] == "Item" and (h["operation"] != "Update" or any(a.get(f) != b.get(f) for f in ["item_code", "qty", "description", "position"]))
        cost_change = h["line_type"] == "Resource" or structure or a.get("cost_rate") != b.get("cost_rate")
        sell_change = structure or (h["line_type"] == "Item" and a.get("selling_rate") != b.get("selling_rate"))
        if (cost_change and not can_cost) or (sell_change and not can_sell):
            frappe.throw("Your role may not change these BOQ fields. Buying and selling authority are checked per line, even when total changes cancel out.", frappe.PermissionError)
    if not math.isfinite(proposed.total_cost) or not math.isfinite(proposed.total_selling):
        frappe.throw("Calculated BOQ totals must be finite.")
    if proposed.total_selling <= 0:
        frappe.throw("Revised selling total must be positive.")
    return proposed, history


def _sync_quotation(sheet, requested):
    if not requested:
        return "Linked Quotation was not changed; review it against this revision before sending."
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_deal_identity
    if not sheet.custom_quotation:
        frappe.throw("There is no linked Quotation to update.")
    q = frappe.get_doc("Quotation", sheet.custom_quotation, for_update=True)
    q.check_permission("write")
    if q.docstatus != 0 or q.custom_deal_cost_sheet != sheet.name or quotation_deal_identity(sheet, q):
        frappe.throw("Only this sheet's own verified Draft Quotation can be updated. Submitted, cancelled or other-party quotations are never changed.")
    expected_currency = sheet.currency or frappe.db.get_value("Company", sheet.company, "default_currency")
    if q.currency != expected_currency:
        frappe.throw("The linked Quotation currency differs from the BOQ; review it separately.")
    if any(flt(r.get("selling_amount")) for r in sheet.addtional_charges or []):
        frappe.throw("Quotation sync with separate additional charges requires a commercial review. Represent quoted charges as selling item rows first, or leave the Quotation unchanged.")
    # Do not call make_quotation: that legacy endpoint inserts and commits a
    # new document. This action updates only the already locked draft and must
    # remain atomic with the BOQ and audit history.
    items = []
    for row in sheet.items:
        item = frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom", "brand"], as_dict=True)
        description = row.description or (row.item_name if row.exclude_item_name_and_brand else " - ".join(str(x) for x in [row.brand, row.item_code, row.item_name] if x)) or item.item_name
        items.append({"item_code": row.item_code, "item_name": row.item_name or item.item_name,
            "brand": row.brand, "uom": item.stock_uom, "stock_uom": item.stock_uom,
            "conversion_factor": 1, "description": description, "custom_header": row.header,
            "custom_exclude_item_name_and_brand": row.exclude_item_name_and_brand,
            "qty": row.qty, "custom_cost_rate": row.cost_rate,
            "custom_selling_rate": row.selling_rate, "price_list_rate": row.selling_rate,
            "discount_percentage": 0, "rate": row.selling_rate})
    q.set("items", items)
    # The draft was created by make_quotation with ignore_mandatory; quotation
    # mandatory fields (e.g. payment terms) are enforced when it is submitted,
    # not when the governed BOQ sync refreshes its lines.
    q.flags.ignore_mandatory = True
    q.save()
    if abs(flt(q.total)-flt(sheet.total_selling)) > 0.005:
        frappe.throw("Quotation pricing rules or discounts changed the derived selling total. Review them before synchronising; this revision was not saved.")
    return f"Draft Quotation {q.name} updated from the revised BOQ."


@governed_endpoint("dcs_apply_boq_revision", ptype="write", denied_message=NO_COMMERCIAL_EDIT)
def dcs_apply_boq_revision(args):
    savepoint = "boq_" + frappe.generate_hash(length=12)
    frappe.db.savepoint(savepoint)
    try:
        return _apply(args)
    except frappe.QueryDeadlockError:
        frappe.db.rollback()
        return {"ok": 0, "error": "The BOQ changed while this request was waiting. Refresh and retry; nothing from this request was recorded.", "retry_required": 1}
    except Exception:
        # Also atomic for in-process callers which catch an exception and then
        # commit their surrounding transaction (e.g. an administrative console).
        frappe.db.rollback(save_point=savepoint)
        raise


def _apply(args):
    roles = get_user_roles()
    if not has_any(roles, CUSTOMER_SIDE + VENDOR_SIDE):
        return {"ok": 0, "error": NO_COMMERCIAL_EDIT, "permission_denied": 1}
    if not isinstance(args.get("dcs"), str) or not args["dcs"] or not isinstance(args.get("reason"), str) or not args["reason"].strip():
        return {"ok": 0, "error": "A Deal Cost Sheet and revision reason are required."}
    sheet = frappe.get_doc("Deal Cost Sheet", args["dcs"], for_update=True)
    sheet.check_permission("write")
    if sheet.docstatus != 1:
        frappe.throw("BOQ Revision requires a submitted sheet; edit draft rows normally.")
    if str(args.get("expected_modified") or "") != str(sheet.modified):
        frappe.throw("The sheet has changed since the revision dialog opened. Refresh and try again.")
    if sheet.custom_award_state == "Awarded" or sheet.custom_delivery_release_state in ("Released", "Released with MD Override"):
        frappe.throw("Reverse the award before changing its BOQ. An awarded or released scope is locked.")
    if args.get("source") not in ["Customer", "Vendor", "Technical", "Internal"]:
        frappe.throw("A valid revision source is required.")
    proposed, history = _proposal(sheet, args, roles)
    if not history:
        return {"ok": 1, "no_change": 1, "error": "", "revision": sheet.custom_revision_reference}
    quote_changed = any(h["line_type"] == "Item" and any(
        json.loads(h["before_values"]).get(f) != json.loads(h["after_values"]).get(f)
        for f in ["item_code", "description", "qty", "selling_rate", "position"]
    ) for h in history)
    if quote_changed and sheet.custom_quotation and not truthy_flag(args.get("update_quotation")) and not truthy_flag(args.get("acknowledge_quote_review")):
        frappe.throw("This changes the quoted scope or selling rates. Update the verified Draft Quotation, or explicitly acknowledge that the existing quotation needs separate review.")
    from bsgroup.dcs.baseline import ensure_baseline
    unpriced = not sheet.custom_dcs_revision_no and not flt(sheet.total_selling)
    if unpriced:
        if (frappe.db.exists("DCS Revision", {"dcs": sheet.name}) or sheet.custom_baseline_frozen
            or sheet.custom_approved_revision_no or flt(sheet.custom_baseline_selling)
            or flt(sheet.custom_working_total_selling) or flt(sheet.custom_concession_percent_from_baseline)
            or sheet.custom_approval_required not in (None, "", "None")
            or sheet.custom_approval_state not in (None, "", "Not Started", "In Negotiation")):
            frappe.throw("The unpriced sheet carries commercial history. Reconcile it before establishing its first priced BOQ.")
        pc, ps = flt(sheet.total_cost), 0
        if not math.isfinite(pc) or pc < 0 or flt(sheet.custom_working_total_cost) not in (0, pc):
            frappe.throw("The unpriced sheet's existing cost must be reconciled first.")
    else:
        ensure_baseline(sheet.name, "dcs_apply_boq_revision")
        sheet.reload()
        pc, ps = flt(sheet.custom_working_total_cost), flt(sheet.custom_working_total_selling)
    gap = abs(pc-flt(sheet.total_cost)) > 0.005 or abs(ps-flt(sheet.total_selling)) > 0.005
    if gap and not (MD in roles and truthy_flag(args.get("reconcile_header_adjustments"))):
        frappe.throw("Totals-only adjustments do not match the current BOQ. The Managing Director must explicitly reconcile them to this replacement BOQ; no hidden amount is carried forward.")
    before = snapshot("Deal Cost Sheet", sheet.name, D2A_FIELDS)
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import GOVERNED_TEXT, GOVERNED_NUM
    for field in GOVERNED_TEXT + GOVERNED_NUM:
        proposed.set(field, sheet.get(field))
    proposed.modified = sheet.modified
    # The only update-after-submit bypass is this internal object token. No
    # client flag can grant it; payloads cannot change fields outside the BOQ.
    proposed.flags.bsg_boq_revision = _SAVE_TOKEN
    proposed.flags.ignore_validate_update_after_submit = True
    # Authority was decided above (governed endpoint write check, per-line buying/selling
    # authority, MD-only reconciliation). DocType 'submit' permission is not the control here:
    # Commercial Controller and Managing Director hold no submit right, which made every
    # CC/MD BOQ revision - including the MD-only header reconciliation - fail with 403.
    proposed.flags.ignore_permissions = True
    proposed.save()
    proposed.reload()
    history = line_history(sheet, proposed)
    nc, ns = flt(proposed.total_cost), flt(proposed.total_selling)
    baseline = ns if unpriced else flt(sheet.custom_baseline_selling)
    nm, ncon = pct(ns-nc, ns), pct(baseline-ns, baseline)
    req, gate = requirement(ncon, nm), gate_for(nm)
    no = (sheet.custom_dcs_revision_no or 0) + 1
    rev = write_revision(sheet.name, no, args["source"], args["reason"], pc, ps,
        pct(ps-pc, ps), flt(sheet.custom_concession_percent_from_baseline), nc, ns,
        nm, ncon, args.get("technical_impact"), req, rev_state_for(req), gate, boq_lines=history)
    if rev.startswith("COLLISION::"):
        frappe.throw("Another revision was recorded. Refresh and retry; this transaction was not saved.")
    frappe.db.set_value("Deal Cost Sheet", sheet.name, {
        "custom_dcs_revision_no": no, "custom_revision_reference": rev,
        "custom_working_total_cost": nc, "custom_working_total_selling": ns,
        "custom_working_margin_percent": nm, "custom_concession_percent_from_baseline": ncon,
        "custom_baseline_selling": baseline,
        "custom_approval_state": state_for(req), "custom_approval_required": req,
        "custom_approval_reason": why_approval(ncon, nm), "custom_margin_gate": gate,
        "custom_margin_gate_reason": why_gate(nm)}, update_modified=True)
    proposed.reload()
    from bsgroup.dcs.quotation_control import supersede_submitted
    supersession_changes = supersede_submitted(proposed)
    quotation_note = _sync_quotation(proposed, truthy_flag(args.get("update_quotation")))
    changes = diff_changes(D2A_FIELDS, before, snapshot("Deal Cost Sheet", sheet.name, D2A_FIELDS), "Deal Cost Sheet", sheet.name)
    changes += supersession_changes
    if quote_changed and sheet.custom_quotation and not truthy_flag(args.get("update_quotation")):
        if sheet.custom_deal_status == "Quoted":
            frappe.db.set_value("Deal Cost Sheet", sheet.name, "custom_deal_status", "Submitted to Sales", update_modified=True)
            changes.append({"dt": "Deal Cost Sheet", "dn": sheet.name, "field": "custom_deal_status", "old": "Quoted", "new": "Submitted to Sales"})
        proposed.add_comment("Info", f"Quotation {sheet.custom_quotation} was deliberately left unchanged after BOQ revision {rev}. Review its scope and selling rates before using it for this revision.")
    for h in history:
        changes.append({"dt": "Deal Cost Sheet", "dn": sheet.name,
            "field": h["line_type"] + ":" + h["row_key"], "old": h["before_values"], "new": h["after_values"]})
    event = audit_event(sheet.name, "DCS_REVISION_APPLIED", "Apply a governed item and labour BOQ revision",
        "dcs_apply_boq_revision", args["reason"], no, rev, rev, changes)
    return {"ok": 1, "error": "", "revision": rev, "governance_event": event,
        "state": {"revision_no": no, "working_total_cost": nc, "working_total_selling": ns,
            "working_margin_percent": nm, "approval_required": req, "margin_gate": gate,
            "docstatus_unchanged": 1}, "quotation_note": quotation_note}


def settle_predecessor(amendment):
    if not amendment.amended_from:
        return
    rows = frappe.get_all("DCS Revision", filters={"dcs": amendment.amended_from, "settled_by": ["is", "not set"]}, fields=["name"])
    changes = []
    for row in rows:
        frappe.db.set_value("DCS Revision", row.name, {"settled_by": amendment.name, "settled_on": now_datetime()}, update_modified=False)
        changes.append({"dt": "DCS Revision", "dn": row.name, "field": "settled_by", "old": "", "new": amendment.name})
    if changes:
        from bsgroup.dcs.governance import record_governance_event, make_request_key
        record_governance_event(amendment.name, "DCS_BOQ_LINEAGE_SETTLED",
            action_label="Supersede predecessor BOQ history with the amendment's own baseline",
            source_endpoint="deal_cost_sheet.on_submit", reason=f"Amended from {amendment.amended_from}; prior movements are not applied again.",
            changes=changes, request_key=make_request_key("dcs_boq_settlement", {"amendment": amendment.name}))
