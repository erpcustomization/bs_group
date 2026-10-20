"""Regression for reported cash-journal and closed-PO gaps; all postings roll back."""
import json
import uuid
import frappe
from frappe.utils import nowdate, add_days, flt
from frappe.model.workflow import apply_workflow
from test_standard_documents import (
    check, blocked, RESULTS, new_order, payload, po_action, action, BUYER, MANAGER, COMPANY,
)
from qc_fixtures import cleanup_files
from bsgroup.tests.dcs_fixtures import make_user
from bsgroup import procurement as p
from erpnext.buying.doctype.purchase_order.purchase_order import (
    update_status, make_purchase_receipt, make_purchase_invoice,
)
from erpnext.stock.doctype.material_request.material_request import make_purchase_order

ACCOUNTS = "zztest-cash-gap-accounts@example.com"
BANK = "RAK BANK - AE"


def account(label, root, kind):
    parent = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 1, "root_type": root})
    return frappe.get_doc(dict(doctype="Account", company=COMPANY, parent_account=parent,
        account_name="ZZTEST GAP " + label + " " + uuid.uuid4().hex[:8],
        account_type=kind, is_group=0)).insert().name


def journal(debit, credit=BANK, amount=10, **kw):
    return frappe.get_doc(dict(doctype="Journal Entry", company=COMPANY,
        voucher_type="Bank Entry" if credit == BANK else "Journal Entry", posting_date=nowdate(),
        cheque_no="ZZTEST-ROLLED-BACK", cheque_date=nowdate(),
        user_remark="QC ONLY - all entries rolled back", accounts=[
            dict(account=debit, debit_in_account_currency=amount, exchange_rate=1,
                 cost_center=frappe.get_cached_value("Company", COMPANY, "cost_center")),
            dict(account=credit, credit_in_account_currency=amount, exchange_rate=1),
        ], **kw))


def cash_checks():
    expense = frappe.db.get_value("Account", {
        "company": COMPANY, "account_name": "Cooling Energy Bill", "is_group": 0})
    liability = account("liability", "Liability", "Current Liability")
    cash = account("cash", "Asset", "Cash")
    fixed = account("asset", "Asset", "Fixed Asset")
    tax = account("tax", "Liability", "Tax")
    employee_account = account("employee advances", "Asset", "Receivable")
    employee = frappe.db.get_value("Employee", {"company": COMPANY, "status": "Active"})
    assert employee, "An active test-company Employee is required for the employee-settlement regression"
    for user in (ACCOUNTS, MANAGER, "Administrator"):
        frappe.set_user(user)
        blocked("Direct Cooling Energy Bill payment blocked / " + user,
                lambda: journal(expense).insert(), "Direct expense")
    frappe.set_user(ACCOUNTS)
    for label, debit, credit in (("cash", expense, cash), ("asset", fixed, BANK),
                                  ("clearing", liability, BANK)):
        blocked("Unapproved " + label + " disbursement blocked",
                lambda: journal(debit, credit).insert(), "Direct expense")
    blocked("Changing voucher type does not bypass expense control",
            lambda: journal(expense).update({"voucher_type": "Journal Entry"}).insert(), "Direct expense")
    blocked("Financing label cannot exempt a utility expense",
            lambda: journal(expense, custom_bsp_cash_category="Financing or capital settlement",
                custom_bsp_cash_reason="Claimed exception").insert(), "Direct expense")
    noncash = journal(expense, liability)
    noncash.insert(); noncash.submit()
    check("Non-cash expense accrual still posts balanced GL",
          frappe.db.count("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": noncash.name,
                                      "is_cancelled": 0}) == 2)
    noncash.cancel()
    check("Non-cash accrual reversal remains available", noncash.docstatus == 2)
    transfer = journal(cash)
    transfer.insert(); transfer.submit()
    check("Genuine bank-to-cash transfer still submits", transfer.docstatus == 1)
    transfer.cancel()
    draft = journal(expense, liability).insert()
    def change_to_cash():
        doc = frappe.get_doc("Journal Entry", draft.name)
        doc.accounts[1].account = BANK
        doc.save()
    blocked("Saved non-cash draft cannot switch to direct bank payment", change_to_cash, "Direct expense")
    # Model an expense-payment draft saved before this release; only the test
    # fixture uses SQL. Submitting it must execute the normal document hooks.
    frappe.db.set_value("Journal Entry Account", draft.accounts[1].name, "account", BANK)
    blocked("Pre-existing direct-expense draft cannot submit",
            lambda: frappe.get_doc("Journal Entry", draft.name).submit(), "Direct expense")
    def forge():
        doc = journal(liability, custom_bsp_cash_category="Financing or capital settlement",
                      custom_bsp_cash_reason="QC repayment")
        doc.custom_bsp_cash_approved_by = MANAGER
        doc.insert()
    blocked("Cash approval identity cannot be forged", forge, "approval evidence")
    blocked("Non-procurement settlement needs explanatory notes",
            lambda: journal(liability, custom_bsp_cash_category="Financing or capital settlement").insert(),
            "Explain")
    exception = journal(liability, custom_bsp_cash_category="Financing or capital settlement",
                        custom_bsp_cash_reason="QC financing repayment; not a vendor or utility payment").insert()
    check("Accounts can prepare a legitimate financing journal for review", exception.docstatus == 0)
    for user in (ACCOUNTS, "Administrator"):
        frappe.set_user(user)
        blocked("Only Mohan may submit a classified cash exception / " + user,
                lambda: frappe.get_doc("Journal Entry", exception.name).submit(), "Only Mohan")
    frappe.set_user(MANAGER)
    exception.reload().submit()
    check("Mohan's cash exception approval is recorded",
          exception.docstatus == 1 and exception.custom_bsp_cash_approved_by == MANAGER
          and exception.custom_bsp_cash_approved_on)
    exception.reload().save()
    check("Unchanged approved cash journal can be saved", exception.docstatus == 1)
    def change_approved():
        doc = frappe.get_doc("Journal Entry", exception.name)
        doc.accounts[0].account = expense
        doc.flags.ignore_validate_update_after_submit = True
        doc.save()
    blocked("Approved cash exception cannot become a utility payment",
            change_approved, "Cancel and replace")
    exception.reload().cancel()
    check("Approved non-procurement journal can be reversed", exception.docstatus == 2)
    for category, debit, party_type, party in (
        ("Statutory tax settlement", tax, None, None),
        ("Customer refund", frappe.get_cached_value("Company", COMPANY, "default_receivable_account"),
         "Customer", frappe.db.get_value("Customer", {"disabled": 0})),
        ("Employee settlement", employee_account, "Employee", employee),
    ):
        frappe.set_user(ACCOUNTS)
        doc = journal(debit, custom_bsp_cash_category=category,
                      custom_bsp_cash_reason="QC actual non-procurement settlement; rolled back")
        doc.accounts[0].party_type, doc.accounts[0].party = party_type, party
        doc.insert()
        blocked(category + ": Accounts cannot self-approve",
                lambda: frappe.get_doc("Journal Entry", doc.name).submit(), "Only Mohan")
        frappe.set_user(MANAGER)
        doc.reload().submit()
        check(category + ": valid journal submits with Mohan's evidence",
              doc.custom_bsp_cash_approved_by == MANAGER and doc.custom_bsp_cash_approved_on)
        doc.cancel()


def approve_order(order):
    frappe.set_user(BUYER)
    order = p.save_order(order["id"], order["modified"], payload(order, 90))
    order = po_action(p, order, "Send for Approval")
    frappe.set_user(MANAGER)
    return po_action(p, order, "Approve")


def close_checks():
    frappe.set_user("Administrator")
    stock = frappe.copy_doc(frappe.get_doc("Item", "ZZTEST-CLAUDE-DCS-ITEM-A"))
    stock.item_code = stock.item_name = "ZZTEST-CLOSED-GAP-" + uuid.uuid4().hex[:8]
    stock.is_stock_item = 1
    stock.valuation_rate = 90
    if not any(r.uom == "Box" for r in stock.uoms):
        stock.append("uoms", dict(uom="Box", conversion_factor=2))
    else:
        next(r for r in stock.uoms if r.uom == "Box").conversion_factor = 2
    stock.insert()
    for label, ordered, received, invoiced, factor in (
        ("fully allocated, unreceived", 10, 0, 0, 1),
        ("fully allocated, partly received", 10, 3, 0, 1),
        ("partly allocated, partly received", 6, 3, 0, 1),
        ("service partly invoiced", 10, 0, 3, 1),
        ("two-unit boxes partly received", 10, 3, 0, 2),
        ("fully received", 10, 10, 0, 1),
    ):
        frappe.set_user(BUYER)
        req = p.create_request(dict(key=str(uuid.uuid4()), company=COMPANY,
            title="ZZTEST closed PO final approval / " + label,
            supporting=dict(exception=True, explanation="QC single-source test; rolled back"),
            schedule_date=add_days(nowdate(), 7), warehouse="Stores - AE",
            items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A" if invoiced else stock.name,
                        qty=10, rate=100, **({"uom": "Box"} if factor == 2 else {}))]))
        req = action(p, req, "Send for Approval")
        frappe.set_user(MANAGER)
        req = action(p, req, "Approve")
        frappe.set_user(BUYER)
        original = approve_order(new_order(p, req, qty=ordered))
        fulfilment = None
        if received:
            fulfilment = make_purchase_receipt(original["id"])
            fulfilment.posting_date = nowdate()
            fulfilment.items[0].qty = fulfilment.items[0].received_qty = received
            fulfilment.insert(); fulfilment.submit()
        if invoiced:
            fulfilment = make_purchase_invoice(original["id"])
            fulfilment.posting_date = fulfilment.due_date = fulfilment.bill_date = nowdate()
            fulfilment.bill_no = "ZZTEST-GAP-" + uuid.uuid4().hex
            fulfilment.items[0].qty = invoiced
            fulfilment.insert()
            fulfilment = apply_workflow(fulfilment, "Send for Approval")
            fulfilment = apply_workflow(fulfilment, "Approve")
        kept, remaining = max(received, invoiced), 10 - max(received, invoiced)
        update_status("Closed", original["id"])
        mr = frappe.get_doc("Material Request", req["id"])
        view = p.get_request(req["id"])
        check(label + ": native MR retains only fulfilled quantity", flt(mr.items[0].ordered_qty) == kept * factor)
        check(label + ": BS screen offers exact replacement quantity", view["items"][0]["available"] == remaining)
        native = make_purchase_order(req["id"], args=dict(supplier="A Rehman tech services",
            filtered_children=[mr.items[0].name]))
        if not remaining:
            check(label + ": native mapper offers no replacement", not native.items)
            frappe.set_user(BUYER)
            blocked(label + ": no fulfilled quantity can be re-ordered",
                    lambda: new_order(p, req, qty=1), "unallocated")
            continue
        check(label + ": native mapper includes released balance",
              len(native.items) == 1 and flt(native.items[0].qty) == remaining)
        frappe.set_user(BUYER)
        replacement = new_order(p, view, qty=remaining, supplier="A Rehman tech services")
        replacement = p.save_order(replacement["id"], replacement["modified"], payload(replacement, 90))
        replacement = po_action(p, replacement, "Send for Approval")
        blocked(label + ": replacement still needs Mohan",
                lambda: po_action(p, replacement, "Approve"), "Only Mohan")
        frappe.set_user(MANAGER)
        replacement = po_action(p, replacement, "Approve")
        check(label + ": different supplier replacement approved and submitted",
              replacement["docstatus"] == 1 and replacement["supplier"] == "A Rehman tech services")
        check(label + ": native MR and BS allocation agree after approval",
              flt(frappe.get_doc("Material Request", req["id"]).items[0].ordered_qty) == 10 * factor
              and p.get_request(req["id"])["items"][0]["available"] == 0)
        blocked(label + ": original cannot reopen over replacement",
                lambda: update_status("Submitted", original["id"]), "unallocated")
        frappe.set_user(BUYER)
        blocked(label + ": additional PO cannot over-order", lambda: new_order(p, req, qty=1), "unallocated")
        frappe.set_user(MANAGER)
        replacement = po_action(p, replacement, "Cancel", "QC replacement cancellation")
        check(label + ": replacement cancellation releases balance",
              flt(frappe.get_doc("Material Request", req["id"]).items[0].ordered_qty) == kept * factor
              and p.get_request(req["id"])["items"][0]["available"] == remaining)
        update_status("Submitted", original["id"])
        check(label + ": safe reopening restores native commitment",
              flt(frappe.get_doc("Material Request", req["id"]).items[0].ordered_qty) == ordered * factor)
        update_status("Closed", original["id"])
        if fulfilment:
            # ERPNext requires reopening a closed PO before receipt cancellation.
            # Preserve that standard control, then reclose with current totals.
            update_status("Submitted", original["id"])
            if invoiced:
                apply_workflow(fulfilment.reload(), "Cancel")
            else:
                fulfilment.reload().cancel()
            update_status("Closed", original["id"])
            check(label + ": reversing fulfilment resyncs closed balance",
                  flt(frappe.get_doc("Material Request", req["id"]).items[0].ordered_qty) == 0
                  and p.get_request(req["id"])["items"][0]["available"] == 10)
    check("Over-order allowance was not relaxed",
          flt(frappe.db.get_single_value("Buying Settings", "over_order_allowance")) == 0)


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    try:
        make_user(BUYER, ["Purchase User"])
        make_user(ACCOUNTS, ["Accounts User", "Accounts Manager"])
        cash_checks()
        close_checks()
        print(json.dumps(dict(passed=len(RESULTS), tests=RESULTS), indent=2), flush=True)
    finally:
        frappe.db.rollback()
        cleanup_files()
        frappe.clear_cache(user=ACCOUNTS)
        frappe.destroy()
        print("All gap-test records, stock and ledger entries rolled back.", flush=True)
