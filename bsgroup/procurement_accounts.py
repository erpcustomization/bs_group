"""Supplier invoice based Payment Orders and matching for BS Procurement."""
import json
import frappe
from frappe.utils import cint, flt, getdate
from bsgroup.procurement import access, load, fail
from bsgroup.procurement_controls import approval_allowed, approver_details, track_preparers


def visible_documents(doctype, names, company):
    """Candidate links are internal; only readable documents leave this function."""
    if not frappe.has_permission(doctype, "read"):
        return [], True
    names = sorted(set(names))
    if not names:
        return [], False
    date_field = "transaction_date" if doctype == "Purchase Order" else "posting_date"
    visible = frappe.get_list(doctype, filters={"name": ["in", names], "company": company},
                              pluck="name", limit_page_length=0, order_by=f"{date_field} desc, creation desc")
    docs = []
    for name in visible:
        try:
            docs.append(access(frappe.get_doc(doctype, name)))
        except frappe.PermissionError:
            pass
    return docs, len(docs) != len(names)


def linked_documents(doctype, order):
    names = frappe.db.sql(
        f"select distinct parent from `tab{doctype} Item` where purchase_order=%s",
        (order.name,), pluck=True)
    return visible_documents(doctype, names, order.company)


def document_state(doc):
    if doc.docstatus == 2:
        return "Cancelled"
    return doc.get("status") or ("Submitted" if doc.docstatus == 1 else "Draft")


def payment_sources(payment, previous=None, extra_invoices=()):
    saved = json.loads(previous.get("custom_bsp_settlement_sources") or "{}") if previous else {}
    orders, invoices = set(saved.get("orders", [])), set(saved.get("invoices", []))
    refs = list(payment.references) + (list(previous.references) if previous else [])
    candidates = set(extra_invoices)
    for row in refs:
        if row.reference_doctype == "Purchase Invoice":
            candidates.add(row.reference_name)
        elif row.reference_doctype == "Purchase Order" and frappe.db.get_value(
                "Purchase Order", row.reference_name, "custom_bsp_managed"):
            orders.add(row.reference_name)
    for name in candidates:
        found = frappe.db.sql("""
            select distinct po.name from `tabPurchase Invoice Item` i
            join `tabPurchase Order` po on po.name=i.purchase_order
            where i.parent=%s and po.custom_bsp_managed=1
        """, (name,), pluck=True)
        if found:
            orders.update(found)
            invoices.add(name)
    return json.dumps(dict(orders=sorted(orders), invoices=sorted(invoices))) if orders else None


def remember_payment_sources(doc, method=None):
    # Rebuild from real references and the saved audit value; ignore client-supplied
    # history. It survives ERPNext's direct removal of invoice allocations.
    previous = doc.get_doc_before_save()
    doc.custom_bsp_settlement_sources = payment_sources(doc, previous)


def remember_invoice_payments(doc, method=None):
    # Also capture payments reconciled by ERP's accounting routines without a
    # Payment Entry save, immediately before invoice cancellation removes links.
    names = frappe.db.sql("""select distinct parent from `tabPayment Entry Reference`
        where reference_doctype='Purchase Invoice' and reference_name=%s""", (doc.name,), pluck=True)
    for name in names:
        payment = frappe.get_doc("Payment Entry", name)
        sources = payment_sources(payment, payment, extra_invoices=(doc.name,))
        if sources:
            frappe.db.set_value("Payment Entry", name, "custom_bsp_settlement_sources", sources,
                                update_modified=False)
            payment.custom_bsp_settlement_sources = sources
            sync_payment_index(payment)


def sync_payment_index(doc, method=None):
    data = json.loads(doc.get("custom_bsp_settlement_sources") or "{}")
    for name in data.get("invoices", []):
        if not frappe.db.exists("BS Payment Source", dict(payment_entry=doc.name, purchase_invoice=name)):
            frappe.get_doc(dict(doctype="BS Payment Source", payment_entry=doc.name,
                purchase_invoice=name, company=doc.company)).insert(ignore_permissions=True)


def validate_invoice_approval(doc, method=None):
    old = doc.get_doc_before_save()
    managed = bool(bs_order_names(doc) or (old and old.get("custom_bsp_managed")))
    if not managed:
        doc.custom_bsp_managed = 0
        from bsgroup.procurement_payments import protect_approval
        protect_approval(doc, old)
        return
    doc.custom_bsp_managed = 1
    track_preparers(doc, old, doc.workflow_state or "Draft",
                    old.workflow_state if old else None)
    if (doc.workflow_state == "Pending Approval" and
            (not old or old.workflow_state != "Pending Approval")):
        validate_payment_order_ready(doc)
    from bsgroup.procurement_payments import protect_approval
    protect_approval(doc, old)


def quantity_used(doctype, field, value, exclude):
    rows = frappe.db.sql(f"""select i.qty, i.conversion_factor
        from `tab{doctype} Item` i join `tab{doctype}` p on p.name=i.parent
        where i.{field}=%s and p.docstatus=1 and p.name!=%s for update""",
        (value, exclude or ""), as_dict=True)
    return sum(flt(r.qty) * flt(r.conversion_factor or 1) for r in rows)


def receipt_unbilled_stock_qty(row, exclude_invoice=None):
    """Accepted stock units left after submitted returns and supplier invoices."""
    billed = quantity_used("Purchase Invoice", "pr_detail", row.name, exclude_invoice)
    returned = -sum(min(0, flt(r.qty) * flt(r.conversion_factor or 1)) for r in
        frappe.db.sql("""select i.qty, i.conversion_factor from `tabPurchase Receipt Item` i
        join `tabPurchase Receipt` p on p.name=i.parent
        where p.docstatus=1 and p.is_return=1 and i.purchase_receipt_item=%s for update""",
        (row.name,), as_dict=True))
    return flt(row.stock_qty) - returned - billed


def enforce_line_limits(doc):
    """BS limits remain effective even if global/item/supplier allowances change."""
    old = doc.get_doc_before_save()
    managed = bs_order_names(doc) or (old and old.get("custom_bsp_managed"))
    if not managed or doc.docstatus == 2 or doc.get("is_return"):
        return
    is_receipt = doc.doctype == "Purchase Receipt"
    po_field = "purchase_order_item" if is_receipt else "po_detail"
    grouped, received = {}, {}
    for row in doc.items:
        if not row.purchase_order or not row.get(po_field):
            fail("Every line on a BS receipt or supplier invoice must reference an approved PO row.")
        frappe.db.sql("select name from `tabPurchase Order` where name=%s for update", row.purchase_order)
        po = frappe.get_doc("Purchase Order", row.purchase_order)
        source = next((r for r in po.items if r.name == row.get(po_field)), None)
        if po.docstatus != 1 or not source:
            fail("Select a submitted Purchase Order and its matching row.")
        if po.status == "Closed" and (
                is_receipt or not row.purchase_receipt or not row.pr_detail or doc.get("update_stock")):
            # Closing releases the undelivered balance, not the liability for
            # goods/services already accepted. Native ERPNext also permits
            # closed-PO invoices with a receipt, without reopening the PO.
            fail("A closed Purchase Order can only be invoiced against its existing accepted "
                 "Purchase Receipt. New receipts and stock-updating invoices are not allowed.")
        if po.get("custom_bsp_managed") and po.custom_bsp_approval_state != "Approved":
            fail("The BS Purchase Order must be approved.")
        if doc.supplier != po.supplier or doc.company != po.company or row.item_code != source.item_code:
            fail("Supplier, company and item must match the approved PO.")
        if doc.currency != po.currency:
            fail("Use the approved PO currency on its receipt or supplier invoice.")
        factor, source_factor = flt(row.conversion_factor or 1), flt(source.conversion_factor or 1)
        if factor <= 0 or flt(row.qty) <= 0:
            fail("A purchase quantity and its UOM conversion must be positive.")
        from bsgroup.procurement import uom_factor
        if abs(factor-uom_factor(row.item_code,row.uom)) > 0.000000001:
            fail("The receipt/invoice UOM conversion must match the configured Item UOM.")
        if flt(row.rate)/factor > flt(source.rate)/source_factor + 0.000001:
            fail("The receipt/invoice unit rate cannot exceed the approved PO rate.")
        key = source.name
        grouped[key] = grouped.get(key, 0) + flt(row.qty)*factor
        used = quantity_used(doc.doctype, po_field, key, doc.name)
        if used + grouped[key] > flt(source.stock_qty) + 0.000001:
            fail("Receipt or invoiced quantity exceeds the approved PO quantity.")
        if not is_receipt:
            item = frappe.get_cached_doc("Item", row.item_code)
            if (item.is_stock_item or item.is_fixed_asset) and not row.purchase_receipt:
                fail("A submitted Purchase Receipt is required for stock and fixed-asset invoices.")
            if row.purchase_receipt:
                receipt = frappe.get_doc("Purchase Receipt", row.purchase_receipt)
                source_receipt = next((r for r in receipt.items if r.name == row.pr_detail), None)
                if (receipt.docstatus != 1 or receipt.is_return
                        or receipt.company != doc.company or receipt.supplier != doc.supplier
                        or not source_receipt or source_receipt.purchase_order != po.name
                        or source_receipt.purchase_order_item != key):
                    fail("The invoice receipt row must come from the same approved PO row.")
                received[row.pr_detail] = received.get(row.pr_detail, 0) + flt(row.qty)*factor
                if received[row.pr_detail] > receipt_unbilled_stock_qty(source_receipt, doc.name) + 0.000001:
                    fail("Invoiced quantity exceeds the accepted, unreturned receipt quantity.")


def validate_matches(doc, method=None):
    """Preserve the approved BS source chain through native receipt/invoice forms."""
    if doc.docstatus == 2 or doc.get("is_return"):
        return
    po_field = "purchase_order_item" if doc.doctype == "Purchase Receipt" else "po_detail"
    projects = set()
    managed = False
    for row in doc.items:
        if not row.purchase_order:
            if row.material_request and frappe.db.get_value(
                    "Material Request", row.material_request, "custom_bsp_managed"):
                fail("A BS receipt or invoice must reference its approved Purchase Order.")
            continue
        po = frappe.get_doc("Purchase Order", row.purchase_order)
        if not po.get("custom_bsp_managed"):
            continue
        managed = True
        if po.docstatus != 1 or po.custom_bsp_approval_state != "Approved":
            fail("Receive or invoice only an approved, submitted BS Purchase Order.")
        source = next((r for r in po.items if r.name == row.get(po_field)), None)
        if not source:
            fail("The source PO row must belong to the selected Purchase Order.")
        for field in ("material_request", "material_request_item", "project"):
            if row.get(field) and row.get(field) != source.get(field):
                fail("The receipt/invoice source requisition and project must match the approved PO row.")
            row.set(field, source.get(field))
        if source.project:
            projects.add(source.project)
        if doc.doctype == "Purchase Invoice" and row.purchase_receipt:
            receipt = frappe.get_doc("Purchase Receipt", row.purchase_receipt)
            received = next((r for r in receipt.items if r.name == row.pr_detail), None)
            if receipt.docstatus != 1 or not received or received.purchase_order != po.name \
                    or received.purchase_order_item != source.name:
                fail("The invoice receipt row must come from the same approved PO row.")
    if managed and len(projects) == 1:
        project = next(iter(projects))
        if doc.project and doc.project != project:
            fail("The receipt/invoice project must match the approved PO.")
        doc.project = project


def bs_order_names(invoice):
    return sorted({r.purchase_order for r in invoice.items if r.purchase_order and
                   frappe.db.get_value("Purchase Order", r.purchase_order, "custom_bsp_managed")})


def invoice_header(doc):
    return dict(id=doc.name, modified=str(doc.modified), supplier=doc.supplier,
        company=doc.company, bill=doc.bill_no or "", date=str(doc.posting_date),
        billDate=str(doc.bill_date or ""), invoiceFile=doc.get("custom_bsp_supplier_invoice_file") or "",
        due=str(doc.due_date or ""), approval=doc.get("workflow_state") or "",
        status=document_state(doc), docstatus=doc.docstatus, currency=doc.currency,
        total=doc.rounded_total or doc.grand_total, net=doc.net_total,
        taxes=doc.total_taxes_and_charges,
        outstanding=doc.outstanding_amount if doc.docstatus == 1 else None,
        outstandingCurrency=doc.party_account_currency or doc.currency,
        orders=sorted({r.purchase_order for r in doc.get("items") if r.purchase_order}),
        requests=sorted({r.material_request for r in doc.get("items") if r.material_request}))


@frappe.whitelist()
def get_payment_orders(start=0, page_length=50):
    if frappe.session.user == "Guest":
        fail("Please sign in.", frappe.PermissionError)
    can_create = frappe.has_permission("Purchase Invoice", "create")
    navigation = dict(user=frappe.session.user,
                      canReadRequests=bool(frappe.has_permission("Material Request", "read")))
    if not frappe.has_permission("Purchase Invoice", "read"):
        return dict(invoices=[], restricted=True, has_more=False, canCreate=can_create, **navigation)
    candidates = frappe.db.sql("""select distinct i.parent from `tabPurchase Invoice Item` i
        join `tabPurchase Order` po on po.name=i.purchase_order where po.custom_bsp_managed=1""", pluck=True)
    size = min(100, max(1, cint(page_length)))
    rows = frappe.get_list("Purchase Invoice", filters={"name": ["in", candidates or [""]]},
        fields=["name","modified","supplier","company","bill_no","bill_date","posting_date","due_date",
                "workflow_state","status","docstatus","currency","rounded_total","grand_total",
                "net_total","total_taxes_and_charges","outstanding_amount","party_account_currency",
                "custom_bsp_supplier_invoice_file"],
        start=max(0, cint(start)), page_length=size+1, order_by="creation asc")
    from bsgroup.procurement_lists import visible_company_names
    names = visible_company_names("Purchase Invoice", [r.name for r in rows[:size]])
    lines = {}
    if names:
        for row in frappe.get_all("Purchase Invoice Item", filters={"parent":["in",names]},
                                  fields=["parent","purchase_order","material_request"]):
            lines.setdefault(row.parent, []).append(row)
    invoices = []
    for row in rows[:size]:
        if row.name in names:
            row["items"] = lines.get(row.name, [])
            invoices.append(invoice_header(row))
    sources = get_payment_order_sources() if can_create else []
    return dict(invoices=invoices, sources=sources, restricted=False, canCreate=can_create,
                has_more=len(rows)>size, **navigation)


@frappe.whitelist()
def get_payment_order(name):
    """One Payment Order in the BS screen is one standard supplier invoice."""
    invoice = load("Purchase Invoice", name)
    if not bs_order_names(invoice):
        fail("Select a supplier invoice linked to BS Procurement.")
    result = invoice_header(invoice)
    result["editableDetails"] = bool(invoice.docstatus == 0 and
        (invoice.workflow_state or "Draft") in ("Draft", "Rejected") and
        frappe.has_permission("Purchase Invoice", "write", doc=invoice))
    receipt_names = {r.purchase_receipt for r in invoice.items if r.purchase_receipt}
    receipts, restricted = visible_documents("Purchase Receipt", receipt_names, invoice.company)
    result["receipts"] = dict(restricted=restricted, records=[
        dict(id=d.name, date=str(d.posting_date), status=document_state(d), docstatus=d.docstatus,
             deliveryNote=d.get("custom_bsp_delivery_note_file") or "",
             invoiceNo=d.get("custom_bsp_supplier_invoice_no") or "",
             invoiceFile=d.get("custom_bsp_supplier_invoice_file") or "",
             lines=[dict(item=r.item_code, qty=r.qty, uom=r.uom, rejected=r.rejected_qty)
                    for r in d.items if any(i.pr_detail == r.name for i in invoice.items)])
        for d in receipts])
    payment_names = set(frappe.db.sql("""select distinct parent from `tabPayment Entry Reference`
        where reference_doctype='Purchase Invoice' and reference_name=%s""", (invoice.name,), pluck=True))
    payment_names.update(frappe.db.sql("""select distinct voucher_no from `tabPayment Ledger Entry`
        where voucher_type='Payment Entry' and company=%s
          and against_voucher_type='Purchase Invoice' and against_voucher_no=%s""",
        (invoice.company, invoice.name), pluck=True))
    payment_names.update(frappe.db.sql("""select payment_entry from `tabBS Payment Source`
        where company=%s and purchase_invoice=%s""",
        (invoice.company, invoice.name), pluck=True))
    advances = {}
    for row in invoice.advances:
        if row.reference_type == "Payment Entry":
            payment_names.add(row.reference_name)
            advances[row.reference_name] = advances.get(row.reference_name, 0) + flt(row.allocated_amount)
    payments, restricted = visible_documents("Payment Entry", payment_names, invoice.company)
    records = []
    for payment in payments:
        refs = [r for r in payment.references if
                r.reference_doctype == "Purchase Invoice" and r.reference_name == invoice.name]
        amount = sum(flt(r.allocated_amount) for r in refs)
        if not refs and invoice.docstatus == 1:
            amount = advances.get(payment.name, 0)
        records.append(dict(id=payment.name, date=str(payment.posting_date),
            status=document_state(payment), docstatus=payment.docstatus, type=payment.payment_type,
            currency=invoice.party_account_currency or invoice.currency, allocated=amount,
            historical=not refs and not amount,
            shared=any(r.reference_doctype != "Purchase Invoice" or r.reference_name != invoice.name
                       for r in payment.references)))
    result["payments"] = dict(records=records, restricted=restricted)
    result["items"] = [dict(item=r.item_code, description=r.item_name, qty=r.qty,
        uom=r.uom, rate=r.rate, amount=r.amount, order=r.purchase_order or "",
        receipt=r.purchase_receipt or "", project=r.project or "") for r in invoice.items]
    from frappe.model.workflow import get_transitions, has_approval_access
    result["actions"] = [t.action for t in get_transitions(invoice)
                         if has_approval_access(frappe.session.user, invoice, t)
                         and (t.action not in ("Approve", "Reject") or approval_allowed(invoice))]
    from bsgroup.procurement_payments import is_approved
    result["approver"] = approver_details()
    result["approvedBy"] = invoice.get("custom_bsp_approved_by")
    result["approvedOn"] = str(invoice.get("custom_bsp_approved_on") or "")
    result["canPay"] = bool(is_approved(invoice) and flt(invoice.outstanding_amount)>0
                            and frappe.has_permission("Payment Entry", "create"))
    from bsgroup.procurement_gl import accounting_data
    result["accounting"] = accounting_data(invoice)
    return result


@frappe.whitelist(methods=["POST"])
def invoice_action(name, modified, action):
    from frappe.model.workflow import apply_workflow
    invoice = load("Purchase Invoice", name, "write", modified)
    if not bs_order_names(invoice):
        fail("Select a BS Procurement supplier invoice.")
    if action in ("Approve", "Reject"):
        approval_allowed(invoice, throw=True)
    if action == "Send for Approval":
        validate_payment_order_ready(invoice)
    invoice = apply_workflow(invoice, action)
    return get_payment_order(invoice.name)


def validate_payment_order_ready(invoice):
    missing = []
    if not (invoice.bill_no or "").strip():
        missing.append("supplier invoice number")
    if not invoice.bill_date:
        missing.append("supplier invoice date")
    invoice_file = invoice.get("custom_bsp_supplier_invoice_file")
    source_receipt = invoice.get("custom_bsp_source_receipt")
    attached = frappe.db.get_value("File", {"file_url": invoice_file},
        ["is_private", "attached_to_doctype", "attached_to_name"], as_dict=True) if invoice_file else None
    valid_attachment = bool(attached and attached.is_private and (
        (attached.attached_to_doctype == "Purchase Invoice" and attached.attached_to_name == invoice.name) or
        (source_receipt and attached.attached_to_doctype == "Purchase Receipt" and
         attached.attached_to_name == source_receipt)))
    if not valid_attachment:
        missing.append("supplier invoice attachment")
    if not invoice.get("custom_bsp_journal_code"):
        missing.append("journal code")
    if not invoice.get("custom_bsp_accounting_confirmed"):
        missing.append("confirmed GL accounts")
    if missing:
        fail("Complete the Payment Order before approval: " + ", ".join(missing) + ".")


@frappe.whitelist(methods=["POST"])
def save_payment_order_details(name, modified, bill_no, bill_date, due_date, invoice_file=""):
    invoice = load("Purchase Invoice", name, "write", modified)
    if not bs_order_names(invoice) or invoice.docstatus != 0 or \
            (invoice.workflow_state or "Draft") not in ("Draft", "Rejected"):
        fail("Supplier invoice details can only be edited on a draft or rejected Payment Order.")
    bill_no = (bill_no or "").strip()
    if not bill_no or not bill_date or not due_date:
        fail("Enter the supplier invoice number, invoice date and due date.")
    file_url = (invoice_file or "").strip()
    if file_url and file_url != invoice.get("custom_bsp_supplier_invoice_file"):
        file = frappe.db.get_value("File", {"file_url": file_url,
            "attached_to_doctype": "Purchase Invoice", "attached_to_name": invoice.name},
            ["name", "is_private"], as_dict=True)
        if not file or not file.is_private:
            fail("Upload the supplier invoice privately against this Payment Order.")
    invoice.bill_no = bill_no
    invoice.bill_date = getdate(bill_date)
    invoice.due_date = getdate(due_date)
    invoice.custom_bsp_supplier_invoice_file = file_url or None
    invoice.save()
    return get_payment_order(invoice.name)


@frappe.whitelist()
def get_payment_order_sources():
    """Return selectable BS sources without exposing ERPNext's create-new links."""
    frappe.has_permission("Purchase Invoice", "create", throw=True)
    sources = []

    receipt_names = frappe.db.sql("""select distinct pr.name
        from `tabPurchase Receipt` pr
        join `tabPurchase Receipt Item` pri on pri.parent=pr.name
        join `tabPurchase Order` po on po.name=pri.purchase_order
        where pr.docstatus=1 and pr.is_return=0 and po.custom_bsp_managed=1
          and not exists (select 1 from `tabPurchase Invoice Item` pii
              join `tabPurchase Invoice` pi on pi.name=pii.parent
              where pii.purchase_receipt=pr.name and pi.docstatus<2)""", pluck=True)
    if receipt_names and frappe.has_permission("Purchase Receipt", "read"):
        for receipt in frappe.get_list("Purchase Receipt",
                filters={"name": ["in", receipt_names]},
                fields=["name", "posting_date", "supplier", "custom_bsp_delivery_note_file",
                        "custom_bsp_supplier_invoice_no", "custom_bsp_supplier_invoice_date",
                        "custom_bsp_supplier_invoice_file"],
                limit_page_length=100, order_by="posting_date desc, creation desc"):
            ready = bool(receipt.custom_bsp_delivery_note_file and
                receipt.custom_bsp_supplier_invoice_file and receipt.custom_bsp_supplier_invoice_no and
                receipt.custom_bsp_supplier_invoice_date)
            sources.append(dict(doctype="Purchase Receipt", name=receipt.name, ready=ready,
                label=f"Receipt {receipt.name} · {receipt.supplier} · {receipt.posting_date}",
                bill=receipt.custom_bsp_supplier_invoice_no or "",
                billDate=str(receipt.custom_bsp_supplier_invoice_date or ""),
                invoiceFile=receipt.custom_bsp_supplier_invoice_file or ""))

    if frappe.has_permission("Purchase Order", "read"):
        orders = frappe.get_list("Purchase Order",
            filters={"docstatus": 1, "custom_bsp_managed": 1,
                     "custom_bsp_approval_state": "Approved"},
            fields=["name", "transaction_date", "supplier"],
            limit_page_length=100, order_by="transaction_date desc, creation desc")
        for order in orders:
            doc = access(frappe.get_doc("Purchase Order", order.name))
            if any(not any(frappe.get_cached_value(
                    "Item", row.item_code, ["is_stock_item", "is_fixed_asset"]))
                    for row in doc.items):
                sources.append(dict(doctype="Purchase Order", name=doc.name, ready=True,
                    label=f"Service PO {doc.name} · {doc.supplier} · {doc.transaction_date}",
                    bill="", billDate="", invoiceFile=""))

    return sources


@frappe.whitelist()
def prepare_payment_order(source_doctype, source_name):
    frappe.has_permission("Purchase Invoice", "create", throw=True)
    if source_doctype not in ("Purchase Order", "Purchase Receipt"):
        fail("Select a Purchase Order or Purchase Receipt.")
    source = load(source_doctype, source_name)
    if source.docstatus != 1:
        fail("Select a submitted source document.")
    if source_doctype == "Purchase Order":
        if not source.get("custom_bsp_managed") or source.custom_bsp_approval_state != "Approved":
            fail("Select an approved BS Purchase Order.")
        # Goods/assets require their receipt. This source option is explicitly
        # labelled for non-stock services, including mixed goods/service POs.
        rows = [r.name for r in source.items if not any(frappe.get_cached_value(
            "Item", r.item_code, ["is_stock_item", "is_fixed_asset"]))]
        if not rows:
            fail("Select a submitted Purchase Receipt for stock or asset invoices.")
        from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
        invoice = make_purchase_invoice(source.name, args={"filtered_children": rows})
    else:
        if source.is_return:
            fail("Select the original accepted Purchase Receipt, not a return.")
        if not any(frappe.db.get_value("Purchase Order", r.purchase_order, "custom_bsp_managed")
                   for r in source.items if r.purchase_order):
            fail("Select a receipt linked to BS Procurement.")
        from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice
        invoice = make_purchase_invoice(source.name)
        # The native mapper can include returned/rejected quantities when the
        # global rejected-quantity billing setting is enabled. BS approval
        # always bills accepted, unreturned scope; show that same cap up front.
        source_rows = {r.name: r for r in source.items}
        for row in list(invoice.items):
            available = receipt_unbilled_stock_qty(source_rows[row.pr_detail])
            row.qty = min(flt(row.qty), max(0, available) / flt(row.conversion_factor or 1))
            row.stock_qty = row.qty * flt(row.conversion_factor or 1)
            if row.qty <= 0:
                invoice.remove(row)
        if invoice.items:
            invoice.calculate_taxes_and_totals()
            invoice.set_payment_schedule()
    if not invoice.items:
        fail("There are no unbilled items for this source.")
    return invoice


@frappe.whitelist(methods=["POST"])
def create_payment_order(source_doctype, source_name, bill_no="", bill_date="", due_date=""):
    """Create the standard Purchase Invoice and return it in the BS Payment Order view."""
    invoice = prepare_payment_order(source_doctype, source_name)
    source = load(source_doctype, source_name)
    invoice_file = ""
    if source_doctype == "Purchase Receipt":
        bill_no = source.get("custom_bsp_supplier_invoice_no") or bill_no
        bill_date = source.get("custom_bsp_supplier_invoice_date") or bill_date
        invoice_file = source.get("custom_bsp_supplier_invoice_file") or ""
        if not source.get("custom_bsp_delivery_note_file") or not invoice_file:
            fail("The submitted receipt must include its delivery note and supplier invoice attachments.")
        invoice.custom_bsp_source_receipt = source.name
    if not (bill_no or "").strip() or not bill_date or not due_date:
        fail("Enter the supplier invoice number, invoice date and due date.")
    invoice.bill_no = bill_no.strip()
    invoice.bill_date = getdate(bill_date)
    invoice.due_date = getdate(due_date)
    invoice.custom_bsp_managed = 1
    invoice.custom_bsp_supplier_invoice_file = invoice_file or None
    invoice.insert()
    return get_payment_order(invoice.name)


@frappe.whitelist()
def prepare_payment(name):
    frappe.has_permission("Payment Entry", "create", throw=True)
    invoice = load("Purchase Invoice", name)
    from bsgroup.procurement_payments import is_approved
    if not bs_order_names(invoice) or not is_approved(invoice) or flt(invoice.outstanding_amount)<=0:
        fail("Select a Payment Order approved by Mohan with an outstanding amount.")
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    return get_payment_entry("Purchase Invoice", invoice.name)
