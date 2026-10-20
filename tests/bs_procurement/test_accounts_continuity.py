"""Test-site continuity checks. Real ERP postings, all rolled back."""
import json
import uuid
import frappe
from frappe.utils import nowdate, add_days, flt
from frappe.model.workflow import apply_workflow
from test_standard_documents import check, blocked, RESULTS, payload, po_action, action as base_action

COMPANY = "Bits Secure IT Infrastructure LLC - AE"
SOURCE_QUOTATION = "SAL-QTN-2026-01213"
SOURCE_MR = "MAT-MR-2026-00007"
OBSERVATIONS = {}
ACCOUNTS_USER = "zztest-continuity-accounts@example.com"
ACCOUNTS_MANAGER = "zztest-continuity-finance-manager@example.com"
ROLE_CHECKED = False
from bsgroup.procurement_controls import PROCUREMENT_APPROVER
PURCHASE_MANAGER = PROCUREMENT_APPROVER


def action(p,r,a,reason=""):
    user=frappe.session.user
    if a=="Approve":
        frappe.set_user(PURCHASE_MANAGER)
    try:
        return base_action(p,r,a,reason)
    finally:
        frappe.set_user(user)


def close(a, b):
    return abs(flt(a) - flt(b)) < 0.005


def posted_invoice(doc):
    user=frappe.session.user
    try:
        return _posted_invoice(doc)
    finally:
        frappe.set_user(user)


def _posted_invoice(doc):
    global ROLE_CHECKED
    role_test = doc.doctype == "Purchase Invoice" and not ROLE_CHECKED
    doc.posting_date = nowdate()
    doc.due_date = nowdate()
    if doc.doctype == "Purchase Invoice":
        doc.bill_no = "ZZTEST-CONTINUITY-" + uuid.uuid4().hex[:10]
        doc.bill_date = nowdate()
    if doc.doctype == "Purchase Invoice":
        frappe.set_user(ACCOUNTS_USER)
    doc.insert()
    if doc.doctype == "Purchase Invoice":
        if role_test:
            from bsgroup import procurement_accounts as accounts
            check("Invoice-based Payment Order shows draft with no payable balance",
                  accounts.get_payment_order(doc.name)["outstanding"] is None)
            accounts.invoice_action(doc.name, str(doc.modified), "Send for Approval")
            doc.reload()
            blocked("Accounts User cannot approve a supplier invoice",
                    lambda: accounts.invoice_action(doc.name, str(doc.modified), "Approve"))
            frappe.set_user(ACCOUNTS_MANAGER)
            accounts.invoice_action(doc.name, str(doc.modified), "Approve")
            doc.reload()
        else:
            doc = apply_workflow(doc, "Send for Approval")
            frappe.set_user(ACCOUNTS_MANAGER)
            doc = apply_workflow(doc, "Approve")
    else:
        doc = apply_workflow(doc, "Approve")
    if role_test:
        check("Accounts Manager approves through the existing invoice workflow", doc.docstatus == 1)
        ROLE_CHECKED = True
    frappe.set_user("Administrator")
    return doc.reload()


def ledger(doc, label):
    rows = frappe.get_all("GL Entry", filters={"voucher_type": doc.doctype,
        "voucher_no": doc.name, "is_cancelled": 0},
        fields=["account", "debit", "credit", "project", "cost_center"])
    check(label + ": balanced posted ledger", bool(rows) and close(
        sum(r.debit for r in rows), sum(r.credit for r in rows)))
    return rows


def pay(doc, amount=None):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    pe = get_payment_entry(doc.doctype, doc.name, bank_account="RAK BANK - AE")
    if amount is not None:
        pe.paid_amount = amount
        pe.received_amount = amount
        pe.references[0].allocated_amount = amount
    pe.custom_bsp_settlement_sources = '{"orders":["FAKE-PO"],"invoices":["FAKE-INVOICE"]}'
    pe.reference_no = "ZZTEST-CONTINUITY"
    pe.reference_date = nowdate()
    pe.posting_date = nowdate()
    pe.insert()
    pe.submit()
    if doc.doctype == "Purchase Invoice":
        check("Payment audit history ignores fabricated client source links",
              "FAKE-" not in (pe.custom_bsp_settlement_sources or ""))
    ledger(pe, "Supplier payment" if doc.doctype == "Purchase Invoice" else "Customer receipt")
    return pe


def order(p, r, source, qty, supplier, rate, tax=True):
    r = p.get_request(r["id"])
    po = p.create_order(r["id"], r["modified"], supplier, {source: qty}, str(uuid.uuid4()))
    po = p.save_order(po["id"], po["modified"], payload(po, rate))
    if tax:
        doc = frappe.get_doc("Purchase Order", po["id"])
        doc.taxes_and_charges = "UAE VAT 5% Input - AE - AE"
        template = frappe.get_doc("Purchase Taxes and Charges Template", doc.taxes_and_charges)
        doc.set("taxes", [])
        for row in template.taxes:
            doc.append("taxes", {k: row.get(k) for k in (
                "charge_type", "account_head", "description", "rate",
                "category", "add_deduct_tax", "cost_center")})
        doc.save()
    po = po_action(p, po, "Send for Approval")
    user=frappe.session.user
    frappe.set_user(PURCHASE_MANAGER)
    try:
        po = po_action(p, po, "Approve")
    finally:
        frappe.set_user(user)
    return frappe.get_doc("Purchase Order", po["id"])


def run():
    from bsgroup import procurement as p
    from bsgroup import procurement_accounts as settlement
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt, make_purchase_invoice
    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice as receipt_invoice
    from bsgroup.tests.dcs_fixtures import make_user
    make_user(ACCOUNTS_USER, ["Accounts User"])
    make_user(ACCOUNTS_MANAGER, ["Accounts User", "Accounts Manager"])
    make_user(PURCHASE_MANAGER, ["Purchase User", "Purchase Manager"])
    make_user("zztest-settlement-buyer@example.com", ["Purchase User"])
    make_user("zztest-settlement-noaccess@example.com", ["Sales User"])
    # Exercise the intended settings before deployment. The caller's persisted
    # configuration is restored with the complete test transaction.
    frappe.db.set_single_value("Buying Settings", "po_required", "Yes")
    frappe.db.set_single_value("Buying Settings", "pr_required", "Yes")
    frappe.db.set_single_value("Buying Settings", "maintain_same_rate", 1)
    frappe.db.set_single_value("Buying Settings", "maintain_same_rate_action", "Stop")
    frappe.db.set_single_value("BS Group Settings", "cost_overrun_policy", "Block")

    # Existing clearly labelled review handover; modifications roll back.
    q = frappe.get_doc("Quotation", SOURCE_QUOTATION)
    mr = frappe.get_doc("Material Request", SOURCE_MR)
    check("Source quotation links to the actual standard MR",
          q.custom_bsp_material_request == mr.name and mr.custom_bsp_quotation == q.name)
    r = p.get_request(mr.name)
    r = action(p, r, "Send for Approval")
    r = action(p, r, "Approve")
    po = order(p, r, mr.items[0].name, 1, "A plus typing", 900)
    prepared = settlement.prepare_payment_order("Purchase Order", po.name)
    check("New Payment Order prepares an unsaved standard vendor invoice from its service PO",
          prepared.doctype == "Purchase Invoice" and prepared.is_new()
          and prepared.items[0].purchase_order == po.name)
    inv = posted_invoice(prepared)
    check("Non-stock service invoice works with PO matching and without a stock receipt", inv.docstatus == 1)
    def missing_po_invoice():
        bad = frappe.copy_doc(inv)
        bad.workflow_state = "Draft"
        for row in bad.items:
            row.purchase_order = row.po_detail = row.material_request = row.material_request_item = None
        posted_invoice(bad)
    blocked("Supplier invoice without a PO is blocked", missing_po_invoice)
    check("Payment Order list uses vendor invoice IDs and exact purchase references",
          any(d["id"] == inv.name and d["orders"] == [po.name]
              for d in settlement.get_payment_orders()["invoices"]))
    mapped_payment = settlement.prepare_payment(inv.name)
    check("Record payment prepares an unsaved entry against this vendor invoice",
          mapped_payment.is_new() and mapped_payment.references[0].reference_name == inv.name)
    check("Award-to-invoice chain retains MR row and PO row identities",
          inv.items[0].material_request == mr.name and
          inv.items[0].material_request_item == mr.items[0].name and
          inv.items[0].po_detail == po.items[0].name)
    check("Purchase invoice uses negotiated cost, not quotation selling price",
          close(inv.net_total, 900) and close(inv.total_taxes_and_charges, 45)
          and close(inv.grand_total, 945))
    ledger(inv, "Supplier invoice")
    payment1 = pay(inv, 400)
    check("Partial supplier payment leaves exact outstanding balance",
          close(inv.reload().outstanding_amount, 545))
    register = settlement.get_payment_order(inv.name)
    check("Payment register shows exact partial payment allocation and outstanding",
          close(register["payments"]["records"][0]["allocated"], 400)
          and close(register["outstanding"], 545))
    payment2 = pay(inv.reload())
    check("Final supplier payment clears invoice", close(inv.reload().outstanding_amount, 0))
    payment2.cancel()
    check("Payment cancellation reopens exact outstanding", close(inv.reload().outstanding_amount, 545))
    check("Cancelled payments remain visibly cancelled in the register",
          any(d["id"] == payment2.name and d["docstatus"] == 2
              for d in settlement.get_payment_order(inv.name)["payments"]["records"]))
    apply_workflow(inv.reload(), "Cancel")
    payment1.reload()
    OBSERVATIONS["invoice_cancellation_payment"] = dict(docstatus=payment1.docstatus,
        unallocated=payment1.unallocated_amount,
        references=[(r.reference_name, r.allocated_amount) for r in payment1.references])
    check("Cancelled invoice releases its existing payment for reallocation",
          payment1.docstatus == 1 and close(payment1.unallocated_amount, 400)
          and not any(r.reference_name == inv.name and r.allocated_amount for r in payment1.references))
    register = settlement.get_payment_order(inv.name)
    check("Cancelled invoice shows no payable balance",
          register["outstanding"] is None and not register["canPay"])
    blocked("Cancelled invoice cannot prepare another payment", lambda: settlement.prepare_payment(inv.name))
    check("Released payment remains in history without a false live allocation",
          any(d["id"] == payment1.name and d["historical"] and close(d["allocated"], 0)
              for d in register["payments"]["records"]))
    payment1.cancel()
    check("Invoice cancellation restores PO unbilled balance",
          close(po.reload().per_billed, 0))

    # Customer revenue is a separate accounting branch of the same quotation.
    from bsgroup.dcs.quotation_control import make_sales_order
    from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice
    so = make_sales_order(q.name)
    so.delivery_date = add_days(nowdate(), 7)
    for row in so.items:
        row.delivery_date = so.delivery_date
    so.insert()
    so.submit()
    si = posted_invoice(make_sales_invoice(so.name))
    check("Customer invoice retains Sales Order and original quotation lineage",
          si.items[0].sales_order == so.name and so.items[0].prevdoc_docname == q.name)
    check("Customer invoice retains selling value and output VAT",
          close(si.net_total, 1500) and close(si.total_taxes_and_charges, 75)
          and close(si.grand_total, 1575))
    ledger(si, "Customer invoice")
    customer_payment = pay(si)
    check("Customer receipt clears receivable and identifies customer",
          close(si.reload().outstanding_amount, 0) and customer_payment.party == q.party_name)

    # Multiple suppliers, partial stock deliveries, receipt-to-invoice and project costing.
    project = frappe.get_doc(dict(doctype="Project", project_name="ZZTEST-Continuity-" + uuid.uuid4().hex[:6],
        company=COMPANY, customer=q.party_name, custom_project_description="Rollback continuity test",
        expected_start_date=nowdate(), expected_end_date=add_days(nowdate(), 30),
        project_type="Quick-Turn Project", custom_project_manager="1028")).insert()
    item = frappe.get_doc(dict(doctype="Item", item_code="ZZTEST-CONT-STOCK-" + uuid.uuid4().hex[:6],
        item_name="QC stock item", item_group=frappe.db.get_value("Item", mr.items[0].item_code, "item_group"),
        stock_uom="Nos", is_stock_item=1, is_purchase_item=1, is_sales_item=1,
        valuation_rate=100)).insert()
    from bsgroup.tests.dcs_fixtures import make_dcs
    budget_dcs = make_dcs(suffix="Continuity-Budget-" + uuid.uuid4().hex[:6], submit=True,
        company=COMPANY, currency="AED", project=project.name,
        items=[dict(item_code=item.name, qty=1, cost_rate=370, selling_rate=500)])
    baseline = frappe.get_doc(dict(doctype="Project Cost Baseline", project=project.name,
        deal_cost_sheet=budget_dcs.name)).insert()
    baseline.submit()
    frappe.db.set_single_value("BS Group Settings", "cost_overrun_policy", "Block")
    r = p.create_request(dict(key=str(uuid.uuid4()), company=COMPANY,
        project=project.name, customer=q.party_name, title="ZZTEST continuity split vendors",
        schedule_date=add_days(nowdate(), 7), warehouse="Stores - AE",
        items=[dict(item_code=item.name, qty=4, rate=100)]))
    r = action(p, r, "Send for Approval")
    r = action(p, r, "Approve")
    source = r["items"][0]["sourceId"]
    from erpnext.stock.doctype.material_request.material_request import make_purchase_order
    native = make_purchase_order(r["id"], args=dict(supplier="A plus typing",
        filtered_children=[source], requested_qty={source: 1}))
    native.insert()
    check("Native Material Request mapper also receives the project header", native.project == project.name)
    def remove_project():
        doc = frappe.get_doc("Purchase Order", native.name)
        doc.project = None
        doc.save()
    blocked("Native PO edit cannot remove the source project", remove_project, "project")
    p.order_action(native.name, str(native.modified), "Cancel", "QC native mapping completed")
    frappe.db.savepoint("missing_project_baseline")
    frappe.db.set_value("Project Cost Baseline", baseline.name, "status", "Draft")
    blocked("Project-linked PO approval requires an approved cost baseline",
            lambda: order(p, r, source, 1, "A plus typing", 90), "Baseline")
    frappe.db.rollback(save_point="missing_project_baseline")
    po1 = order(p, r, source, 2, "A plus typing", 90)
    po2 = order(p, r, source, 2, "A Rehman tech services", 95)
    OBSERVATIONS["project_mapping"] = dict(expected=project.name, po_header=po1.project,
                                           po_row=po1.items[0].project)
    check("Project carries to standard PO header and row",
          po1.project == project.name and po1.items[0].project == project.name)
    check("Multiple suppliers fully allocate one PR", p.get_request(r["id"])["purchasing"] == "Fully ordered")
    blocked("Stock supplier invoice without a receipt is blocked",
            lambda: posted_invoice(make_purchase_invoice(po1.name)), "Receipt")
    blocked("Payment Order creation for stock requires a receipt",
            lambda: settlement.prepare_payment_order("Purchase Order", po1.name), "Receipt")
    def bad_receipt(mode):
        bad = make_purchase_receipt(po1.name)
        if mode == "missing_po":
            for row in bad.items:
                row.purchase_order = row.purchase_order_item = row.material_request = row.material_request_item = None
        else:
            bad.items[0].rate = 91
        bad.insert()
    blocked("Purchase Receipt without a PO is blocked", lambda: bad_receipt("missing_po"))
    blocked("Receipt price cannot exceed approved PO rate", lambda: bad_receipt("rate"))
    pre = make_purchase_receipt(po1.name)
    pre.items[0].qty = 1
    pre.items[0].received_qty = 1
    pre.posting_date = nowdate()
    pre.insert()
    pre.submit()
    check("Partial receipt updates only its source PO", close(po1.reload().per_received, 50)
          and close(po2.reload().per_received, 0))
    check("Receipt keeps original MR and project", pre.items[0].material_request == r["id"]
          and pre.items[0].project == project.name)
    check("Stock receipt posts stock ledger", bool(frappe.db.exists("Stock Ledger Entry",
          {"voucher_no": pre.name, "item_code": item.name, "actual_qty": 1, "is_cancelled": 0})))
    inv1 = posted_invoice(settlement.prepare_payment_order("Purchase Receipt", pre.name))
    def wrong_receipt_source():
        bad = frappe.copy_doc(inv1)
        bad.workflow_state = "Draft"
        bad.items[0].purchase_order = po2.name
        bad.items[0].po_detail = po2.items[0].name
        posted_invoice(bad)
    blocked("Invoice cannot combine a receipt with another PO row", wrong_receipt_source, "same approved PO row")
    register = settlement.get_payment_order(inv1.name)
    check("Payment Order receipt section preserves matched quantities",
          len(register["receipts"]["records"]) == 1
          and close(register["receipts"]["records"][0]["lines"][0]["qty"], 1))
    check("Uninvoiced PO is not listed as a Payment Order",
          not any(po2.name in d["orders"] for d in settlement.get_payment_orders()["invoices"]))
    frappe.set_user("zztest-settlement-buyer@example.com")
    restricted = settlement.get_payment_orders()
    if frappe.has_permission("Purchase Invoice", "read"):
        buyer_view = settlement.get_payment_order(inv1.name)
        check("Buyer invoice access follows existing ERP permissions; payments stay restricted",
              not restricted["restricted"] and buyer_view["payments"]["restricted"]
              and not buyer_view["payments"]["records"])
    else:
        check("Buyer without invoice permission receives no invoice data",
              restricted["restricted"] and not restricted["invoices"])
        blocked("Buyer without invoice permission cannot open details", lambda: settlement.get_payment_order(inv1.name))
    frappe.set_user("zztest-settlement-noaccess@example.com")
    check("User without invoice access receives an empty restricted list",
          settlement.get_payment_orders()["restricted"] and not settlement.get_payment_orders()["invoices"])
    blocked("Sales User cannot open Payment Order details", lambda: settlement.get_payment_order(inv1.name))
    blocked("Sales User cannot prepare supplier payment", lambda: settlement.prepare_payment(inv1.name))
    frappe.set_user("Administrator")
    check("Receipt invoice preserves all source links",
          inv1.items[0].purchase_receipt == pre.name and inv1.items[0].purchase_order == po1.name
          and inv1.items[0].material_request == r["id"])
    check("Partial billing has correct quantity, tax and source percentage",
          close(inv1.grand_total, 94.5) and close(po1.reload().per_billed, 50))
    rows = ledger(inv1, "Stock supplier invoice")
    check("Project survives invoice and expense ledger", inv1.project == project.name
          and inv1.items[0].project == project.name and any(r.project == project.name for r in rows))
    from bsgroup.utils.project_cost_baseline import get_purchase_committed_cost, get_actual_purchase_cost
    check("Partial billing releases only the invoiced commitment",
          close(get_purchase_committed_cost(project.name), 280)
          and close(get_actual_purchase_cost(project.name), 90))
    blocked("Receipt cancellation blocked after invoicing", lambda: pre.reload().cancel())
    pre2 = make_purchase_receipt(po1.name)
    pre2.posting_date = nowdate()
    pre2.insert()
    pre2.submit()
    inv2 = posted_invoice(receipt_invoice(pre2.name))
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    shared = get_payment_entry("Purchase Invoice", inv1.name, bank_account="RAK BANK - AE")
    other = get_payment_entry("Purchase Invoice", inv2.name, bank_account="RAK BANK - AE")
    shared.append("references", {k: v for k, v in other.references[0].as_dict().items()
                                if k not in ("name", "parent", "parenttype", "parentfield", "idx")})
    shared.paid_amount = shared.received_amount = inv1.outstanding_amount + inv2.outstanding_amount
    shared.reference_no = "ZZTEST-SHARED-PAYMENT"
    shared.reference_date = nowdate()
    shared.insert()
    shared.submit()
    for target in (inv1, inv2):
        shown = settlement.get_payment_order(target.name)
        allocation = next(d for d in shown["payments"]["records"] if d["id"] == shared.name)
        check("Shared payment shows only this invoice allocation: " + target.name,
              allocation["shared"] and close(allocation["allocated"], 94.5)
              and close(shown["outstanding"], 0) and not shown["canPay"])
    shared.cancel()
    check("Remaining receipt and invoice complete PO without duplicate quantities",
          close(pre2.items[0].qty, 1) and close(po1.reload().per_received, 100)
          and close(po1.per_billed, 100) and po1.status == "Completed")
    def over_receive():
        d = frappe.copy_doc(pre2)
        d.set("items", [frappe.copy_doc(pre2.items[0])])
        d.insert()
        d.submit()
    blocked("Over-receipt beyond PO quantity blocked", over_receive)
    def over_bill():
        d = frappe.copy_doc(inv2)
        d.workflow_state = "Draft"
        posted_invoice(d)
    blocked("Duplicate billing beyond PO quantity blocked", over_bill)
    check("Second supplier remains independently unreceived and unbilled",
          close(po2.reload().per_received, 0) and close(po2.per_billed, 0))
    OBSERVATIONS["project_costs_after_billing"] = dict(
        committed=get_purchase_committed_cost(project.name),
        actual=get_actual_purchase_cost(project.name),
        expected_committed=190, expected_actual=180)
    check("Project cost transfers billed PO value from committed to actual without double counting",
          close(get_purchase_committed_cost(project.name), 190)
          and close(get_actual_purchase_cost(project.name), 180))
    check("Invoice approval at the exact baseline avoids a false overrun",
          close(baseline.reload().remaining_amount, 0))
    def overspend():
        extra = p.create_request(dict(key=str(uuid.uuid4()), company=COMPANY,
            project=project.name, customer=q.party_name, title="ZZTEST excess budget",
            schedule_date=add_days(nowdate(), 7), warehouse="Stores - AE",
            items=[dict(item_code=item.name, qty=1, rate=1)]))
        extra = action(p, extra, "Send for Approval")
        extra = action(p, extra, "Approve")
        order(p, extra, extra["items"][0]["sourceId"], 1, "A plus typing", 1)
    blocked("Actual new commitment above the project baseline is still blocked", overspend, "Baseline")
    frappe.db.set_single_value("BS Group Settings","cost_overrun_policy","None")
    blocked("G07 BS project overrun remains blocked if global policy is disabled",overspend,"Baseline")
    frappe.db.set_single_value("BS Group Settings","cost_overrun_policy","Block")
    apply_workflow(inv2.reload(), "Cancel")
    check("Invoice reversal restores commitment and reduces actual cost exactly once",
          close(get_purchase_committed_cost(project.name), 280)
          and close(get_actual_purchase_cost(project.name), 90)
          and close(baseline.reload().remaining_amount, 0))
    OBSERVATIONS["settings"] = dict(
        invoice_requires_po=frappe.db.get_single_value("Buying Settings", "po_required"),
        invoice_requires_receipt=frappe.db.get_single_value("Buying Settings", "pr_required"),
        perpetual_inventory=frappe.get_cached_value("Company", COMPANY, "enable_perpetual_inventory"))
    print(json.dumps(dict(passed=len(RESULTS), tests=RESULTS, observations=OBSERVATIONS), indent=2), flush=True)


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    try:
        run()
    finally:
        print("OBSERVATIONS", json.dumps(OBSERVATIONS), flush=True)
        frappe.db.rollback()
        frappe.destroy()
        print("All test business transactions rolled back.", flush=True)
