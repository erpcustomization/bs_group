"""Mohan's approval inbox; existing commercial and purchasing decisions stay authoritative."""
from html import escape

import frappe
from frappe.utils import get_datetime, flt
from bsgroup.dcs.manager_approval import FIXED_APPROVER, FINAL_STATES, is_assigned_manager, route_for

PAGE = "bs-approval-request"


def require_mohan():
    if frappe.session.user != FIXED_APPROVER or not frappe.get_cached_value("User", FIXED_APPROVER, "enabled"):
        frappe.throw("Approval Request is available only to Mohan.", frappe.PermissionError)


def visible_rows(doctype, filters, fields):
    if not frappe.has_permission(doctype, "read"):
        return []
    rows = frappe.get_list(doctype, filters=filters, fields=fields, limit_page_length=0, order_by="modified asc")
    from bsgroup.procurement_lists import visible_company_names
    allowed = set(visible_company_names(doctype, [r.name for r in rows]))
    return [r for r in rows if r.name in allowed]


def sales_pending(doc):
    return (doc.docstatus == 1 and doc.get("custom_approval_required") not in (None, "", "None")
            and doc.get("custom_approval_state") not in FINAL_STATES
            and not doc.get("custom_superseded_by") and is_assigned_manager(doc))


@frappe.whitelist()
def pending():
    require_mohan()
    result = []
    sales = visible_rows("Deal Cost Sheet", {"docstatus": 1,
        "custom_approval_required": ["in", ["Manager", "Blocked", "Managing Director"]],
        "custom_approval_state": ["not in", list(FINAL_STATES)]},
        ["name", "modified", "owner", "company", "customer", "subject", "deal_owner", "currency",
         "custom_working_total_selling", "custom_approval_state", "custom_quotation"])
    for row in sales:
        doc = frappe.get_doc("Deal Cost Sheet", row.name)
        if not sales_pending(doc):
            continue
        result.append(dict(kind="sales", name=row.name, modified=str(row.modified),
            subject=row.subject, customer=row.customer, company=row.company,
            requested_by=route_for(doc).get("changed_by") or row.deal_owner or row.owner,
            amount=row.custom_working_total_selling, currency=row.currency,
            state=row.custom_approval_state, quotation=row.custom_quotation or ""))
    requests = visible_rows("Material Request", {"custom_bsp_managed": 1,
        "material_request_type": "Purchase", "workflow_state": "Pending Approval", "docstatus": 0},
        ["name", "modified", "owner", "company", "title", "custom_bsp_customer", "custom_bsp_quotation"])
    from bsgroup.procurement_controls import approval_allowed
    for row in requests:
        doc = frappe.get_doc("Material Request", row.name)
        if not approval_allowed(doc):
            continue
        result.append(dict(kind="purchase", name=row.name, modified=str(row.modified),
            subject=row.title, customer=row.custom_bsp_customer, company=row.company,
            requested_by=row.owner, amount=sum(flt(i.qty) * flt(i.rate) for i in doc.items),
            currency=frappe.get_cached_value("Company", row.company, "default_currency"),
            state="Pending Approval", quotation=row.custom_bsp_quotation or ""))
    result.sort(key=lambda row: (row["modified"], row["kind"], row["name"]))
    return dict(requests=result, counts={kind: sum(r["kind"] == kind for r in result)
                                        for kind in ("sales", "purchase")})


def load_sales(name, lock=False):
    from bsgroup.procurement import access
    doc = frappe.get_doc("Deal Cost Sheet", name, for_update=lock)
    access(doc)
    if not sales_pending(doc):
        frappe.throw("This sales request is no longer pending Mohan's approval. Refresh the inbox.")
    return doc


@frappe.whitelist()
def review(kind, name):
    require_mohan()
    if kind == "sales":
        doc = load_sales(name)
        from bsgroup.api.dcs.approval import dcs_screen4
        data = dcs_screen4(dcs=doc.name)
        if not data.get("ok"):
            frappe.throw(data.get("error") or "This sales request cannot be reviewed.")
        data.update(kind=kind, name=doc.name, modified=str(doc.modified), revision=doc.custom_revision_reference,
            quotation=doc.get("custom_quotation"), items=[dict(item=r.get("item_name") or r.item_code,
                description=frappe.utils.strip_html(r.description or ""), qty=r.qty,
                uom=r.get("uom") or "", cost=r.cost_rate, selling=r.selling_rate) for r in doc.items])
        data["actions"] = [a["key"] for a in data["actions"] if a["key"] in ("Approve", "Reject", "Return for Rework")]
        return data
    if kind == "purchase":
        from bsgroup.procurement import get_request
        data = get_request(name)
        if data["approval"] != "Pending Approval":
            frappe.throw("This requisition is no longer pending approval. Refresh the inbox.")
        data.update(kind=kind, name=name)
        data["actions"] = [a for a in data["actions"] if a in ("Approve", "Reject")]
        return data
    frappe.throw("Unknown approval request type.")


@frappe.whitelist(methods=["POST"])
def decide(kind, name, modified, action, reason="", revision=None):
    require_mohan()
    if action not in ("Approve", "Reject", "Return for Rework"):
        frappe.throw("Choose a valid approval decision.")
    reason = str(reason or "").strip()
    if action in ("Reject", "Return for Rework") and not reason:
        frappe.throw("Enter a reason for this decision.")
    if not modified:
        frappe.throw("Refresh and review the request before deciding.")
    if kind == "sales":
        doc = load_sales(name, lock=True)
        if (not revision or revision != doc.custom_revision_reference
                or get_datetime(modified) != get_datetime(doc.modified)):
            frappe.throw("This sales request changed after you opened it. Refresh and review it again.", frappe.TimestampMismatchError)
        from bsgroup.api.dcs.approval import dcs_approval_decision
        result = dcs_approval_decision(dcs=name, action=action, reason=reason)
        if not result.get("ok"):
            frappe.throw(result.get("error") or "The approval decision could not be recorded.")
        return dict(saved=True, state=result.get("state", {}).get("approval_state") or action)
    if kind == "purchase":
        if action not in ("Approve", "Reject"):
            frappe.throw("Purchase Requisitions support Approve or Reject.")
        from bsgroup.procurement import load, request_action
        doc = load("Material Request", name, "write", modified)
        if not doc.custom_bsp_managed or doc.workflow_state != "Pending Approval" or doc.docstatus:
            frappe.throw("This requisition is no longer pending approval. Refresh the inbox.")
        result = request_action(name, modified, action, reason)
        return dict(saved=True, state=result["approval"])
    frappe.throw("Unknown approval request type.")


@frappe.whitelist(methods=["POST"])
def install():
    frappe.only_for("System Manager")
    frappe.reload_doc("bs_group", "page", "bs_approval_request", force=True)
    frappe.clear_cache()
    return setup_page()


@frappe.whitelist()
def setup_page():
    """Deployment setup only; no business decisions, roles or document shares are changed."""
    frappe.only_for("System Manager")
    from frappe.sessions import get_csrf_token
    installed = bool(frappe.db.exists("Page", PAGE))
    body = f'''<h2>Approval Request</h2><p>Status: {"Installed" if installed else "Ready to install"}</p>
    <p>A private inbox for Mohan's pending sales commercial approvals and BS Purchase Requisition approvals.
    Existing approval rules and record access remain enforced.</p>
    <form method="post" action="/api/method/bsgroup.approval_requests.install">
    <input type="hidden" name="csrf_token" value="{escape(get_csrf_token(), quote=True)}">
    <button class="btn btn-primary" type="submit">Install Approval Request screen</button></form>
    <p><a href="/desk/bs-group/{PAGE}">Open Approval Request as Mohan</a></p>'''
    frappe.respond_as_web_page("Approval Request setup", body, indicator_color="green" if installed else "orange")
