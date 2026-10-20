"""Real test-site policy scenarios; all records and ledger postings roll back."""
import json
import uuid
import frappe
from frappe.utils import nowdate, add_days
from frappe.model.workflow import apply_workflow
from test_standard_documents import (
    check, blocked, RESULTS, new_request, new_order, payload, action, po_action, BUYER, MANAGER, COMPANY,
)
from qc_fixtures import cleanup_files
from bsgroup.procurement_controls import APPROVER_ROLE
from bsgroup.procurement_payments import SUPPLIER_EXCEPTIONS, validate_payment, approved_invoice

ACCOUNTS = "zztest-policy-accounts@example.com"
OTHER = "zztest-policy-manager@example.com"


def draft_invoice(po, user=ACCOUNTS):
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice
    frappe.set_user(MANAGER)
    doc = make_purchase_invoice(po["id"])
    frappe.set_user(user)
    doc.items[0].qty = 1
    doc.bill_no = "ZZTEST-POLICY-" + uuid.uuid4().hex
    doc.bill_date = doc.posting_date = doc.due_date = nowdate()
    return doc


def payment(invoice, amount=10):
    from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
    doc = get_payment_entry("Purchase Invoice", invoice.name, bank_account="RAK BANK - AE")
    doc.paid_amount = doc.received_amount = doc.references[0].allocated_amount = amount
    doc.reference_no = "ZZTEST-POLICY"
    doc.reference_date = doc.posting_date = nowdate()
    return doc


def journal(invoice, amount=10, reference=True):
    return frappe.get_doc(dict(doctype="Journal Entry", company=COMPANY,
        voucher_type="Bank Entry", posting_date=nowdate(), cheque_no="ZZTEST-POLICY",
        cheque_date=nowdate(), accounts=[
            dict(account=invoice.credit_to, party_type="Supplier", party=invoice.supplier,
                 debit_in_account_currency=amount, exchange_rate=1,
                 reference_type="Purchase Invoice" if reference else None,
                 reference_name=invoice.name if reference else None),
            dict(account="RAK BANK - AE", credit_in_account_currency=amount, exchange_rate=1),
        ]))


def run():
    from bsgroup import procurement as p, procurement_accounts as a
    from bsgroup.tests.dcs_fixtures import make_user
    from erpnext.accounts.doctype.unreconcile_payment.unreconcile_payment import create_unreconcile_doc_for_selection
    make_user(BUYER, ["Purchase User"])
    make_user(ACCOUNTS, ["Accounts User"])
    make_user(OTHER, ["Accounts User", "Accounts Manager", APPROVER_ROLE])
    for field in SUPPLIER_EXCEPTIONS:
        check("All supplier exception flags remain off: " + field,
              not frappe.db.count("Supplier", {field: 1}))
        check("Supplier exception checkbox is read-only: " + field,
              frappe.get_meta("Supplier").get_field(field).read_only)
        def toggle():
            doc = frappe.get_doc("Supplier", "A plus typing")
            doc.set(field, 1)
            doc.save()
        blocked("Even Administrator cannot enable supplier exception: " + field, toggle, "remain off")
    plain = frappe.get_doc(dict(doctype="Purchase Order", company=COMPANY, supplier="A plus typing",
        schedule_date=add_days(nowdate(), 7), items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",
        qty=1, rate=90, schedule_date=add_days(nowdate(), 7))]))
    blocked("Native PO creation without BS PR is rejected", lambda: plain.insert(), "approved BS")
    def edit_legacy_draft():
        name = frappe.db.get_value("Purchase Order",
            {"docstatus": 0, "custom_bsp_managed": 0, "company": COMPANY})
        legacy = frappe.get_doc("Purchase Order", name)
        legacy.save()
    blocked("Existing ordinary PO drafts cannot be saved around the BS route", edit_legacy_draft, "approved BS")
    def expand_legacy_order():
        name = frappe.db.get_value("Purchase Order",
            {"docstatus": 1, "custom_bsp_managed": 0, "company": COMPANY})
        legacy = frappe.get_doc("Purchase Order", name)
        legacy.items[0].qty += 1
        legacy.flags.ignore_validate_update_after_submit = True
        legacy.save()
    blocked("Historical ordinary submitted POs cannot add unapproved scope", expand_legacy_order, "Historical")
    def reopen_legacy_order():
        name = frappe.db.get_value("Purchase Order",
            {"docstatus": 1, "status": "Closed", "custom_bsp_managed": 0, "company": COMPANY})
        frappe.get_doc("Purchase Order", name).update_status("Submitted")
    blocked("Historical ordinary closed POs cannot be reopened", reopen_legacy_order, "cannot be reopened")
    frappe.set_user(BUYER)
    r = new_request(p, count=12)
    blocked("PO from an unapproved BS PR is rejected", lambda: new_order(p, r))
    r = action(p, r, "Send for Approval")
    frappe.set_user(MANAGER)
    r = action(p, r, "Approve")
    frappe.set_user(BUYER)
    po = new_order(p, r, qty=12)
    po = p.save_order(po["id"], po["modified"], payload(po))
    po = po_action(p, po, "Send for Approval")
    frappe.set_user("Administrator")
    blocked("Administrator cannot approve PO", lambda: po_action(p, po, "Approve"), "Only Mohan")
    frappe.set_user(MANAGER)
    po = po_action(p, po, "Approve")
    check("Every new PO retains approved BS PR and Mohan approval",
          po["history"][-1]["actor"] == MANAGER and po["request"] == r["id"])
    invoices = []
    for initiator in (ACCOUNTS, OTHER, "Administrator", MANAGER):
        doc = draft_invoice(po, initiator)
        doc.insert()
        check("Draft Payment Order is not payable / " + initiator,
              not a.get_payment_order(doc.name)["canPay"])
        blocked("Draft cannot prepare payment / " + initiator, lambda: a.prepare_payment(doc.name))
        doc = apply_workflow(doc, "Send for Approval")
        for denied in (ACCOUNTS, OTHER, "Administrator"):
            frappe.set_user(denied)
            check("Payment Order hides decisions from " + denied + " / " + initiator,
                  "Approve" not in a.get_payment_order(doc.name)["actions"])
            blocked("Payment Order API refuses " + denied + " / " + initiator,
                    lambda: a.invoice_action(doc.name, str(doc.modified), "Approve"), "Only Mohan")
        frappe.set_user(OTHER)
        blocked("Native workflow rejects substituted approval role / " + initiator,
                lambda: apply_workflow(doc.reload(), "Approve"), "Only Mohan")
        def forge():
            forged = doc.reload()
            forged.workflow_state = "Approved"
            forged.submit()
        frappe.set_user("Administrator")
        blocked("Native submit rejects forged approval / " + initiator, forge, "Only Mohan")
        frappe.set_user(MANAGER)
        doc.reload()
        check("Pending Payment Order routes only to Mohan's role / " + initiator,
              all(t.allowed == APPROVER_ROLE for t in __import__(
                  "frappe.model.workflow", fromlist=["get_transitions"]).get_transitions(doc)
                  if t.action in ("Approve", "Reject")))
        doc = apply_workflow(doc, "Reject")
        check("Rejected Payment Order is not payable / " + initiator,
              not a.get_payment_order(doc.name)["canPay"])
        frappe.set_user(initiator)
        doc = apply_workflow(doc, "Send for Approval")
        frappe.set_user(MANAGER)
        doc = apply_workflow(doc, "Approve")
        view = a.get_payment_order(doc.name)
        check("Mohan approval is recorded and enables payment / " + initiator,
              doc.docstatus == 1 and doc.custom_bsp_approved_by == MANAGER
              and doc.custom_bsp_approved_on and view["canPay"]
              and view["approver"]["user"] == MANAGER and view["approvedBy"] == MANAGER)
        invoices.append(doc)
    frappe.set_user("Administrator")
    inv = invoices[0].reload()
    def evidence_tamper():
        doc = frappe.get_doc("Purchase Invoice", inv.name)
        doc.custom_bsp_approved_by = OTHER
        doc.flags.ignore_validate_update_after_submit = True
        doc.save()
    blocked("Submitted approval identity cannot be edited", evidence_tamper, "approval evidence")
    def evidence_insert():
        doc = draft_invoice(po, "Administrator")
        doc.custom_bsp_approved_by = MANAGER
        doc.custom_bsp_approved_on = "2026-10-20 10:00:00"
        doc.insert()
    blocked("New invoice cannot invent Mohan's approval", evidence_insert, "approval evidence")
    def inline():
        doc = draft_invoice(po, "Administrator")
        doc.is_paid = 1
        doc.cash_bank_account = "RAK BANK - AE"
        doc.paid_amount = 90
        doc.insert()
    blocked("Inline invoice payment cannot bypass Payment Order approval", inline, "Inline invoice")
    def unallocated():
        doc = payment(inv)
        doc.set("references", [])
        doc.insert()
    blocked("Unallocated supplier payment is rejected", unallocated, "Allocate the entire")
    def partial_allocation():
        doc = payment(inv, 20)
        doc.references[0].allocated_amount = 10
        doc.insert()
    blocked("Partly unallocated supplier payment is rejected", partial_allocation, "Allocate the entire")
    def po_advance():
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
        doc = get_payment_entry("Purchase Order", po["id"], bank_account="RAK BANK - AE")
        doc.reference_no = "ZZTEST-PO-ADVANCE"
        doc.reference_date = nowdate()
        doc.insert()
    blocked("Supplier advance against PO is rejected", po_advance)
    # The historical workflow label alone is not evidence of Mohan's decision.
    frappe.db.savepoint("no_approval_proof")
    frappe.db.set_value("Purchase Invoice", inv.name, "custom_bsp_approved_by", None)
    blocked("Submitted invoice without Mohan approval proof cannot be paid",
            lambda: payment(inv.reload()).insert(), "approved by Mohan")
    frappe.db.rollback(save_point="no_approval_proof")
    inv.reload()
    blocked("Supplier mismatch is rejected", lambda: approved_invoice(inv.name, "A Rehman tech services", COMPANY),
            "supplier and company")
    blocked("Company mismatch is rejected", lambda: approved_invoice(inv.name, inv.supplier, "Other company"),
            "supplier and company")
    blocked("Supplier account mismatch is rejected", lambda: approved_invoice(inv.name, inv.supplier, COMPANY,
            "RAK BANK - AE"), "supplier account")
    blocked("Journal supplier advance without Payment Order is rejected",
            lambda: journal(inv, reference=False).insert(), "approved Payment Orders")
    j = journal(inv)
    j.insert()
    j.submit()
    check("Journal settlement against approved Payment Order posts correctly",
          j.docstatus == 1 and abs(inv.reload().outstanding_amount - 80) < .001)
    blocked("Payment Order with active journal settlement cannot be cancelled",
            lambda: apply_workflow(inv.reload(), "Cancel"), "linked supplier payments")
    blocked("Native Unreconcile Payment cannot orphan a supplier journal settlement",
            lambda: create_unreconcile_doc_for_selection([dict(voucher_type="Journal Entry",
                voucher_no=j.name, company=COMPANY, against_voucher_type="Purchase Invoice",
                against_voucher_no=inv.name)]), "remain linked")
    j.cancel()
    check("Journal reversal restores Payment Order balance", abs(inv.reload().outstanding_amount - 90) < .001)
    pe = payment(inv)
    pe.insert()
    pe.submit()
    check("Partial supplier payment posts only against approved Payment Order",
          pe.docstatus == 1 and abs(inv.reload().outstanding_amount - 80) < .001)
    pe.reload().save()
    check("Saving an unchanged submitted payment preserves its valid allocation",
          abs(inv.reload().outstanding_amount - 80) < .001)
    blocked("Native Unreconcile Payment cannot orphan a supplier payment",
            lambda: create_unreconcile_doc_for_selection([dict(voucher_type="Payment Entry",
                voucher_no=pe.name,company=COMPANY,against_voucher_type="Purchase Invoice",
                against_voucher_no=inv.name)]), "remain linked")
    def stale_unallocated():
        doc = frappe.get_doc("Payment Entry", pe.name)
        doc.flags.ignore_validate_update_after_submit = True
        doc.references[0].allocated_amount = 1
        doc.unallocated_amount = 0
        doc.save(ignore_permissions=True)
    blocked("Submitted edits cannot hide unallocated money with stale cached totals",
            stale_unallocated, "Allocate the entire")
    def edit_references():
        doc = frappe.get_doc("Payment Entry", pe.name)
        doc.flags.ignore_validate_update_after_submit = True
        doc.flags.ignore_reposting_on_reconciliation = True
        doc.set("references", [])
        doc.set_amounts()
        doc.save(ignore_permissions=True)
    blocked("Reconciliation flags cannot remove approved Payment Order references", edit_references,
            "Allocate the entire")
    # Update-after-submit hooks use a fresh locked balance, not client outstanding.
    def excess_allocation():
        doc = frappe.get_doc("Payment Entry", pe.name)
        doc.flags.ignore_validate_update_after_submit = True
        doc.references[0].allocated_amount = 1000
        doc.unallocated_amount = 0
        doc.save(ignore_permissions=True)
    blocked("Reconciliation cannot overpay an approved Payment Order", excess_allocation, "outstanding")
    pe.cancel()
    check("Payment cancellation restores full approved balance", abs(inv.reload().outstanding_amount - 90) < .001)
    apply_workflow(inv.reload(), "Cancel")
    blocked("Cancelled Payment Order cannot authorize payments",
            lambda: approved_invoice(inv.name, inv.supplier, COMPANY), "approved by Mohan")
    print(json.dumps(dict(passed=len(RESULTS), tests=RESULTS), indent=2), flush=True)


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    try:
        run()
    finally:
        frappe.db.rollback()
        cleanup_files()
        frappe.clear_cache(user=OTHER)
        frappe.destroy()
        print("All policy test records and ledger entries rolled back.", flush=True)
