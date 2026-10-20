"""Keep native Material Request quantities consistent with closed BS orders."""
import frappe


def effective_source_field(source_field):
    # Called only for ERPNext's PO -> MR ordered_qty updater. SQL identifiers
    # are fixed server constants, never request parameters. Ordinary POs retain
    # the native calculation, including the subcontracting source field.
    if source_field not in ("stock_qty", "fg_item_qty"):
        return source_field
    return f"""case when exists (
        select 1 from `tabPurchase Order` bsp_po
        where bsp_po.name=`tabPurchase Order Item`.parent
          and bsp_po.custom_bsp_managed=1 and bsp_po.status='Closed')
        then least({source_field}, greatest(
            coalesce(received_qty,0)*coalesce(nullif(conversion_factor,0),1),
            case when coalesce(amount,0)!=0
                 then stock_qty*least(1,greatest(0,coalesce(billed_amt,0)/amount))
                 else 0 end)*coalesce({source_field}/nullif(stock_qty,0),0))
        else {source_field} end"""


def related_orders(doc):
    return sorted({row.purchase_order for row in doc.get("items", []) if row.get("purchase_order")})


def lock_fulfilment_requests(doc, method=None):
    names = related_orders(doc)
    if not names:
        return
    requests = frappe.get_all("Purchase Order", filters={
        "name": ["in", names], "custom_bsp_managed": 1},
        pluck="custom_bsp_material_request")
    for name in sorted(set(requests) - {None, ""}):
        frappe.db.sql("select name from `tabMaterial Request` where name=%s for update", (name,))


def sync_closed_orders(doc, method=None):
    # Receipt returns/cancellations and invoice cancellations can change the
    # fulfilled quantity after closure. Run after native PO totals update.
    for name in related_orders(doc):
        order = frappe.get_doc("Purchase Order", name)
        if order.docstatus == 1 and order.get("custom_bsp_managed") and order.status == "Closed":
            order.update_prevdoc_status()
            order.update_requested_qty()


def repair_closed_requests():
    for name in frappe.get_all("Purchase Order", filters={
            "custom_bsp_managed": 1, "docstatus": 1, "status": "Closed"}, pluck="name"):
        order = frappe.get_doc("Purchase Order", name)
        frappe.db.sql("select name from `tabMaterial Request` where name=%s for update",
                      (order.custom_bsp_material_request,))
        order.update_prevdoc_status()
        order.update_requested_qty()
