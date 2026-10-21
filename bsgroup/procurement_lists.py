"""Paged summaries without loading every PO, MR and attachment per list row."""
import frappe
from frappe.utils import cint, flt
from bsgroup.procurement_controls import closed_stock_qty


def visible_company_names(doctype, names):
    if frappe.session.user == "Administrator" or not names:
        return names
    from bsgroup.utils.company_access import global_company_condition
    condition = global_company_condition(frappe.session.user, doctype)
    if not condition:
        return names
    visible = set(frappe.db.sql(f"select name from `tab{doctype}` where name in %s and ({condition})",
                             (tuple(names),), pluck=True))
    return [n for n in names if n in visible]


def order_summary(row):
    return dict(id=row.name, request=row.custom_bsp_material_request, company=row.company,
        supplier=row.supplier, status=("Cancelled" if row.docstatus == 2 else
        row.custom_bsp_approval_state or "Draft"), erpStatus=("Withdrawn" if row.docstatus == 0
        and row.custom_bsp_approval_state == "Cancelled" else row.status),
        currency=row.currency, net=row.net_total, grand=row.grand_total)


ORDER_FIELDS = ["name", "custom_bsp_material_request", "company", "supplier", "docstatus",
                "custom_bsp_approval_state", "status", "currency", "net_total", "grand_total"]


def list_orders(start=0, page_length=50, search=""):
    filters = {"custom_bsp_managed": 1}
    query = str(search or "").strip()[:140]
    conditions = [[f, "like", "%" + query + "%"] for f in
                  ("name", "supplier", "custom_bsp_material_request", "custom_bsp_approval_state", "status")] if query else None
    if query.lower() == "withdrawn":
        filters.update(docstatus=0, custom_bsp_approval_state="Cancelled")
        conditions = None
    size = min(100, max(1, cint(page_length)))
    rows = frappe.get_list("Purchase Order", filters=filters, or_filters=conditions,
        fields=ORDER_FIELDS, start=max(0, cint(start)), page_length=size+1, order_by="modified desc")
    allowed = set(visible_company_names("Purchase Order", [r.name for r in rows]))
    return dict(orders=[order_summary(r) for r in rows[:size] if r.name in allowed],
                has_more=len(rows)>size)


def list_requests(start=0, page_length=50):
    from bsgroup.procurement import purchaser
    size = min(100, max(1, cint(page_length)))
    rows = frappe.get_list("Material Request",
        filters={"custom_bsp_managed": 1, "material_request_type": "Purchase"},
        fields=["name", "modified", "owner", "company", "title", "custom_project", "workflow_state", "status", "docstatus"],
        start=max(0, cint(start)), page_length=size+1, order_by="creation desc")
    names = visible_company_names("Material Request", [r.name for r in rows[:size]])
    if not names:
        return dict(requests=[], has_more=len(rows)>size, user=frappe.session.user,
                    canCreate=purchaser() and frappe.has_permission("Material Request", "create"))
    items = frappe.get_all("Material Request Item", filters={"parent": ["in", names]},
        fields=["parent", "name", "item_code", "item_name", "qty", "stock_qty", "rate", "uom", "conversion_factor"], order_by="idx")
    reservations = frappe.db.sql("""select i.material_request, i.material_request_item, i.stock_qty,
        i.received_qty, i.conversion_factor, i.billed_amt, i.amount, p.status, p.docstatus, p.custom_bsp_approval_state
        from `tabPurchase Order Item` i join `tabPurchase Order` p on p.name=i.parent
        where i.material_request in %s and p.docstatus<2
          and coalesce(p.custom_bsp_approval_state,'')!='Cancelled'""", (tuple(names),), as_dict=True)
    totals, states = {}, {}
    for row in reservations:
        effective = closed_stock_qty(row) if row.status == "Closed" else flt(row.stock_qty)
        value = totals.setdefault(row.material_request_item, [0, 0])
        value[0] += effective
        value[1] += effective if row.docstatus == 1 else 0
        if effective:
            states.setdefault(row.material_request, set()).add(row.custom_bsp_approval_state)
    lines = {}
    for row in items:
        reserved, ordered = totals.get(row.name, [0, 0])
        factor = flt(row.conversion_factor or 1)
        lines.setdefault(row.parent, []).append(dict(sourceId=row.name, item_code=row.item_code,
            description=row.item_name, qty=row.qty, uom=row.uom, cost=row.rate,
            reserved=reserved/factor, ordered=ordered/factor, available=max(0,(flt(row.stock_qty)-reserved)/factor)))
    result = []
    for row in rows[:size]:
        if row.name not in names:
            continue
        details = lines.get(row.name, [])
        approval = "Cancelled" if row.docstatus == 2 else row.workflow_state or "Draft"
        status = "Cancelled" if approval == "Cancelled" else "Not started"
        if approval == "Approved":
            if row.status == "Stopped":
                status = "Stopped"
            elif details and all(r["ordered"] >= r["qty"]-1e-6 for r in details):
                status = "Fully ordered"
            elif any(r["ordered"] for r in details):
                status = "Partially ordered"
            elif "Pending Approval" in states.get(row.name, set()):
                status = "Awaiting PO approval"
            elif states.get(row.name):
                status = "Sourcing / PO preparation"
            else:
                status = "Ready for procurement"
        result.append(dict(id=row.name, modified=str(row.modified), person=row.owner,
            company=row.company, project=row.custom_project or row.title,
            currency=frappe.get_cached_value("Company", row.company, "default_currency"),
            approval=approval, purchasing=status, items=details, orders=[]))
    return dict(requests=result, has_more=len(rows)>size, user=frappe.session.user,
                canCreate=purchaser() and frappe.has_permission("Material Request", "create"))
