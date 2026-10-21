"""Closed PO receipt -> invoice -> payment, with replacement; rollback-only."""
import json
import uuid
import frappe
from frappe.utils import add_days, nowdate, flt
from frappe.model.workflow import apply_workflow
from test_standard_documents import (
    check, blocked, RESULTS, new_order, payload, po_action, action, BUYER, MANAGER, COMPANY,
)
from qc_fixtures import cleanup_files
from bsgroup.tests.dcs_fixtures import make_user, make_dcs
from bsgroup import procurement as p, procurement_accounts as settlement
from bsgroup.utils.project_cost_baseline import get_project_cost_summary
from erpnext.buying.doctype.purchase_order.purchase_order import update_status, make_purchase_receipt
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import (
    make_purchase_invoice, make_purchase_return,
)
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

ACCOUNTS = "zztest-closed-invoice-accounts@example.com"
OBSERVATIONS = {}


def unique(kind):
    return "ZZTEST-CLOSED-BILL-" + kind + "-" + uuid.uuid4().hex[:12]


def equal(a, b):
    return abs(flt(a) - flt(b)) < 0.00001


def approve_order(order, rate=90):
    frappe.set_user(BUYER)
    order = p.order_data(frappe.get_doc("Purchase Order", order["id"]))
    order = p.save_order(order["id"], order["modified"], payload(order, rate))
    order = po_action(p, order, "Send for Approval")
    frappe.set_user(MANAGER)
    return po_action(p, order, "Approve")


def request(item, project=None, uom=None):
    frappe.set_user(BUYER)
    req = p.create_request(dict(key=str(uuid.uuid4()), company=COMPANY,
        title=unique("PR"), project=project, warehouse="Stores - AE",
        supporting=dict(exception=True, explanation="Rollback QC single-source comparison exception."),
        schedule_date=add_days(nowdate(), 7),
        items=[dict(item_code=item, qty=10,
                    rate=100 * p.uom_factor(item, uom) if uom else 100,
                    **({"uom": uom} if uom else {}))]))
    req = action(p, req, "Send for Approval")
    frappe.set_user(MANAGER)
    return action(p, req, "Approve")


def receive(order, qty):
    frappe.set_user(MANAGER)
    doc = make_purchase_receipt(order["id"])
    doc.posting_date = nowdate()
    doc.items[0].qty = doc.items[0].received_qty = qty
    doc.insert(set_name=unique("REC"))
    doc.submit()
    return doc


def insert_invoice(doc):
    frappe.set_user(ACCOUNTS)
    doc.posting_date = doc.due_date = doc.bill_date = nowdate()
    doc.bill_no = unique("BILL")
    doc.insert(set_name=unique("INV"))
    return doc


def approve_invoice(doc):
    frappe.set_user(ACCOUNTS)
    doc = apply_workflow(doc.reload(), "Send for Approval")
    frappe.set_user(MANAGER)
    doc = apply_workflow(doc, "Approve")
    check("Invoice submitted with Mohan's recorded approval",
          doc.docstatus == 1 and doc.custom_bsp_approved_by == MANAGER
          and doc.custom_bsp_approved_on)
    ledger(doc)
    return doc.reload()


def ledger(doc):
    entries = frappe.get_all("GL Entry", filters=dict(voucher_type=doc.doctype,
        voucher_no=doc.name, is_cancelled=0), fields=["debit", "credit"])
    check(doc.doctype + ": balanced accounting entries",
          bool(entries) and equal(sum(r.debit for r in entries), sum(r.credit for r in entries)))


def pay(inv, amount=None):
    frappe.set_user(ACCOUNTS)
    doc = get_payment_entry("Purchase Invoice", inv.name, bank_account="RAK BANK - AE")
    if amount is not None:
        doc.paid_amount = doc.received_amount = doc.references[0].allocated_amount = amount
    doc.posting_date = doc.reference_date = nowdate()
    doc.reference_no = unique("PAYMENT")
    doc.insert(set_name=unique("PE"))
    doc.submit()
    ledger(doc)
    return doc


def budget(project, baseline, committed, actual, label):
    summary = get_project_cost_summary(project.name)
    check(label + ": committed cost", equal(summary["committed_cost"], committed))
    check(label + ": actual cost", equal(summary["actual_cost"], actual))
    check(label + ": remaining budget refreshed",
          equal(baseline.reload().remaining_amount, 935 - committed - actual))
    return summary


def allocated(req, expected, available, label):
    frappe.set_user(MANAGER)
    doc = frappe.get_doc("Material Request", req["id"])
    view = p.get_request(req["id"])
    check(label + ": standard PR allocated quantity", equal(doc.items[0].ordered_qty, expected))
    check(label + ": BS PR available quantity", equal(view["items"][0]["available"], available))


def malformed(receipt, mode, other=None):
    doc = make_purchase_invoice(receipt.name)
    if mode == "excess":
        doc.items[0].qty += 1
    elif mode == "no_receipt":
        doc.items[0].purchase_receipt = doc.items[0].pr_detail = None
    elif mode == "stock":
        doc.update_stock = 1
    elif mode == "wrong_row":
        doc.items[0].purchase_receipt = other.name
        doc.items[0].pr_detail = other.items[0].name
    return insert_invoice(doc)


def project_budget(stock):
    frappe.set_user("Administrator")
    customer = frappe.db.get_value("Quotation", "SAL-QTN-2026-01213", "party_name")
    project = frappe.get_doc(dict(doctype="Project", project_name=unique("PROJECT"),
        company=COMPANY, customer=customer, custom_project_description="Rollback closed PO billing test",
        expected_start_date=nowdate(), expected_end_date=add_days(nowdate(), 30),
        project_type="Quick-Turn Project", custom_project_manager="1028")).insert()
    dcs = make_dcs(submit=True, company=COMPANY, currency="AED", project=project.name,
        suffix=unique("BUDGET"), items=[dict(item_code=stock.name, qty=1, cost_rate=935, selling_rate=1200)])
    baseline = frappe.get_doc(dict(doctype="Project Cost Baseline", project=project.name,
        deal_cost_sheet=dcs.name)).insert()
    baseline.submit()
    return project, baseline


def main_flow(stock):
    project, baseline = project_budget(stock)
    req = request(stock.name, project.name)
    original = approve_order(new_order(p, req, qty=10))
    receipt = receive(original, 3)
    invoice = insert_invoice(settlement.prepare_payment_order("Purchase Receipt", receipt.name))
    frappe.set_user(MANAGER)
    update_status("Closed", original["id"])
    allocated(req, 3, 7, "After closing original PO")
    budget(project, baseline, 270, 0, "Closed PO retains accepted, unbilled cost")
    replacement = new_order(p, req, qty=7, supplier="A Rehman tech services")
    blocked("Replacement cannot consume budget reserved for original accepted goods",
            lambda: approve_order(replacement, 96), "Baseline")
    replacement = approve_order(replacement, 95)
    allocated(req, 10, 0, "After replacement approval")
    budget(project, baseline, 935, 0, "Both suppliers fit exactly within baseline")
    blocked("Original cannot reopen over approved replacement",
            lambda: update_status("Submitted", original["id"]), "unallocated")
    blocked("Closed PO cannot accept another stock receipt",
            lambda: receive(original, 1))
    blocked("Closed PO cannot invoice without accepted receipt",
            lambda: malformed(receipt, "no_receipt"))
    blocked("Closed PO cannot create additional stock through invoice",
            lambda: malformed(receipt, "stock"))
    blocked("Closed PO cannot invoice more than its accepted quantity",
            lambda: malformed(receipt, "excess"), "accepted")
    frappe.set_user(ACCOUNTS)
    blocked("Draft Payment Order cannot be paid", lambda: settlement.prepare_payment(invoice.name))
    invoice = apply_workflow(invoice.reload(), "Send for Approval")
    for user in (ACCOUNTS, "Administrator"):
        frappe.set_user(user)
        blocked("Only Mohan approves original closed-PO invoice / " + user,
                lambda: apply_workflow(invoice.reload(), "Approve"))
    frappe.set_user(MANAGER)
    invoice = apply_workflow(invoice.reload(), "Approve")
    check("Draft prepared before closure approves after closure", invoice.docstatus == 1)
    check("Original PO stays closed after late invoicing",
          frappe.db.get_value("Purchase Order", original["id"], "status") == "Closed")
    ledger(invoice)
    budget(project, baseline, 665, 270, "Late invoice transfers commitment to actual")
    allocated(req, 10, 0, "Invoicing cannot reclaim replacement allocation")
    first = pay(invoice, 100)
    check("Partial original-supplier payment leaves 170", equal(invoice.reload().outstanding_amount, 170))
    second = pay(invoice, 170)
    check("Original supplier fully paid", equal(invoice.reload().outstanding_amount, 0))
    receipt2 = receive(replacement, 7)
    blocked("Invoice cannot substitute the other supplier's receipt",
            lambda: malformed(receipt, "wrong_row", receipt2))
    invoice2 = approve_invoice(insert_invoice(settlement.prepare_payment_order("Purchase Receipt", receipt2.name)))
    payment2 = pay(invoice2)
    check("Replacement supplier fully paid", equal(invoice2.reload().outstanding_amount, 0))
    budget(project, baseline, 0, 935, "Both suppliers invoiced and paid")
    check("Both invoice lines preserve the same original PR line",
          invoice.items[0].material_request == req["id"]
          and invoice2.items[0].material_request == req["id"]
          and invoice.items[0].material_request_item == invoice2.items[0].material_request_item)
    stock_qty = frappe.db.sql("""select sum(actual_qty) from `tabStock Ledger Entry`
        where item_code=%s and is_cancelled=0""", stock.name)[0][0]
    check("Only the ten accepted units enter stock", equal(stock_qty, 10))
    def duplicate():
        doc = frappe.copy_doc(invoice)
        doc.workflow_state = "Draft"
        doc.custom_bsp_approved_by = doc.custom_bsp_approved_on = None
        doc.items[0].qty = 1
        insert_invoice(doc)
    blocked("Already billed receipt cannot be billed again", duplicate, "accepted")
    frappe.set_user(MANAGER)
    blocked("Paid original invoice cannot be cancelled",
            lambda: apply_workflow(invoice.reload(), "Cancel"), "payment")
    first.reload().cancel()
    second.reload().cancel()
    apply_workflow(invoice.reload(), "Cancel")
    check("Invoice reversal does not reopen original PO",
          frappe.db.get_value("Purchase Order", original["id"], "status") == "Closed")
    budget(project, baseline, 270, 665, "Reversal restores received-but-unbilled commitment")
    allocated(req, 10, 0, "Reversal preserves replacement allocation")
    corrected = approve_invoice(insert_invoice(settlement.prepare_payment_order("Purchase Receipt", receipt.name)))
    pay(corrected)
    check("Fresh invoice created after closure is fully paid", equal(corrected.reload().outstanding_amount, 0))
    budget(project, baseline, 0, 935, "Corrected invoice completes full flow")
    OBSERVATIONS["split_supplier_flow"] = dict(
        original_qty=10, accepted_original_qty=3, replacement_qty=7,
        original_amount=270, replacement_amount=665, approved_baseline=935,
        original_po_status=frappe.db.get_value("Purchase Order", original["id"], "status"),
        original_invoice_outstanding=corrected.outstanding_amount,
        replacement_invoice_outstanding=invoice2.reload().outstanding_amount,
        rolled_back=True)


def variants(stock):
    for label, item, uom, rate in (
        ("Service accepted on receipt", "ZZTEST-CLAUDE-DCS-ITEM-A", None, 90),
        ("Two-unit box receipt", stock.name, "Box", 180),
        ("Returned units excluded", stock.name, None, 90),
    ):
        is_return_case = label.startswith("Returned")
        project, baseline = project_budget(stock) if is_return_case else (None, None)
        req = request(item, project=project.name if project else None, uom=uom)
        order = approve_order(new_order(p, req, qty=10), rate)
        receipt = receive(order, 5 if is_return_case else 3)
        update_status("Closed", order["id"])
        if is_return_case:
            budget(project, baseline, 450, 0, "Before returning accepted units on closed PO")
            returned = make_purchase_return(receipt.name)
            returned.posting_date = nowdate()
            returned.items[0].qty = returned.items[0].received_qty = -2
            returned.insert(set_name=unique("RETURN"))
            returned.submit()
            budget(project, baseline, 270, 0, "Return on closed PO refreshes accepted commitment")
        prepared = settlement.prepare_payment_order("Purchase Receipt", receipt.name)
        check(label + ": mapper offers exact remaining accepted quantity", equal(prepared.items[0].qty, 3))
        check(label + ": stock units and invoice total match accepted quantity",
              equal(prepared.items[0].stock_qty, 6 if uom else 3)
              and equal(prepared.grand_total, 3 * rate))
        if is_return_case:
            blocked("Return itself cannot be selected as a new Payment Order source",
                    lambda: settlement.prepare_payment_order("Purchase Receipt", returned.name), "original")
        blocked(label + ": excess invoice is rejected",
                lambda: malformed(receipt, "excess"), "accepted")
        inv = approve_invoice(insert_invoice(prepared))
        pay(inv)
        check(label + ": accepted quantity billed and paid after closure",
              equal(inv.reload().outstanding_amount, 0) and equal(inv.items[0].qty, 3))
        check(label + ": original remains closed",
              frappe.db.get_value("Purchase Order", order["id"], "status") == "Closed")
        allocated(req, 6 if uom else 3, 7, label)
        if is_return_case:
            budget(project, baseline, 0, 270, "Only retained goods consume project budget")


def reopen_budget(stock):
    project, baseline = project_budget(stock)
    req = request(stock.name, project.name)
    original = approve_order(new_order(p, req, qty=10))
    update_status("Closed", original["id"])
    budget(project, baseline, 0, 0, "Closing an unreceived PO releases all commitment")
    second_req = request(stock.name, project.name)
    approve_order(new_order(p, second_req, qty=1), 100)
    blocked("Reopening checks project budget even when original PR has free quantity",
            lambda: update_status("Submitted", original["id"]), "Baseline")
    check("Blocked budget reopening preserves closed status",
          frappe.db.get_value("Purchase Order", original["id"], "status") == "Closed")
    budget(project, baseline, 100, 0, "Blocked reopening preserves remaining budget")


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    try:
        make_user(BUYER, ["Purchase User"])
        make_user(ACCOUNTS, ["Accounts User", "Accounts Manager"])
        stock = frappe.copy_doc(frappe.get_doc("Item", "ZZTEST-CLAUDE-DCS-ITEM-A"))
        stock.item_code = stock.item_name = unique("ITEM")
        stock.is_stock_item = 1
        stock.valuation_rate = 90
        if not any(r.uom == "Box" for r in stock.uoms):
            stock.append("uoms", dict(uom="Box", conversion_factor=2))
        else:
            next(r for r in stock.uoms if r.uom == "Box").conversion_factor = 2
        stock.insert()
        main_flow(stock)
        variants(stock)
        reopen_budget(stock)
        check("Supplier PO and receipt exceptions remain disabled",
              not frappe.db.count("Supplier", {"allow_purchase_invoice_creation_without_purchase_order": 1})
              and not frappe.db.count("Supplier", {"allow_purchase_invoice_creation_without_purchase_receipt": 1}))
        check("Over-order allowance remains zero",
              not flt(frappe.db.get_single_value("Buying Settings", "over_order_allowance")))
        print(json.dumps(dict(passed=len(RESULTS), tests=RESULTS, observations=OBSERVATIONS), indent=2), flush=True)
    finally:
        frappe.db.rollback()
        cleanup_files()
        frappe.clear_cache(user=ACCOUNTS)
        frappe.destroy()
        print("All closed-PO invoicing test records, stock and ledger entries rolled back.", flush=True)
