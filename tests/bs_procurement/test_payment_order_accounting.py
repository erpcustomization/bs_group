"""Rollback-only invoice/GL integration checks for BS Payment Order coding."""
import json
import sys
import uuid
from pathlib import Path

import frappe
from frappe.utils import nowdate
from frappe.model.workflow import apply_workflow

sys.path.insert(0, str(Path(__file__).parent))
from test_standard_documents import check, blocked, RESULTS, new_request, action, payload, po_action, BUYER, MANAGER, COMPANY
from qc_fixtures import cleanup_files, FILES, pdf_content

ACCOUNTS = "zztest-bsp-gl-accounts@example.com"


def evidence(doc, label):
    file = frappe.get_doc(dict(doctype="File", file_name="ZZTEST-PAYMENT-" +
        uuid.uuid4().hex + ".pdf", content=pdf_content(label), is_private=1,
        attached_to_doctype=doc.doctype, attached_to_name=doc.name)).insert()
    FILES.append(file.get_full_path())
    return file.file_url


def run():
    from bsgroup import procurement as p, procurement_accounts as a, procurement_gl as gl
    from bsgroup.tests.dcs_fixtures import make_user
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt
    make_user(BUYER, ["Purchase User"])
    make_user(ACCOUNTS, ["Accounts User"])
    make_user(MANAGER, ["Purchase User", "Purchase Manager", "Accounts Manager", "BS Procurement Approver"])
    tag = uuid.uuid4().hex[:8]
    parent = frappe.db.get_value("Account", {"company": COMPANY, "root_type": "Expense", "is_group": 1})
    accounts = []
    for i in range(2):
        account = frappe.get_doc(dict(doctype="Account", account_name="ZZTEST GL " + tag + str(i),
            account_number="QC" + tag + str(i), company=COMPANY, parent_account=parent,
            root_type="Expense", report_type="Profit and Loss", is_group=0)).insert()
        accounts.append(account.name)
    stock = "ZZTEST GL STOCK " + tag
    frappe.get_doc(dict(doctype="Item", item_code=stock, item_name=stock,
        item_group="All Item Groups", stock_uom="Nos", is_stock_item=1,
        is_purchase_item=1, is_sales_item=0)).insert()
    frappe.set_user(BUYER)
    r = action(p, new_request(p), "Send for Approval")
    frappe.set_user(MANAGER)
    r = action(p, r, "Approve")
    frappe.set_user(BUYER)
    po = p.create_order(r["id"], r["modified"], "A plus typing",
        {row["sourceId"]: 1 for row in r["items"]}, str(uuid.uuid4()),
        [dict(item_code=stock, qty=1, rate=25, warehouse="Stores - AE")])
    data = payload(po)
    data["comparison"]["line_reasons"] = {row["sourceId"]:
        "Additional stock required for the accounting integration scenario."
        for row in po["items"] if row["additional"]}
    po = p.save_order(po["id"], po["modified"], data)
    po = po_action(p, po, "Send for Approval")
    frappe.set_user(MANAGER)
    po = po_action(p, po, "Approve")
    receipt = make_purchase_receipt(po["id"])
    receipt.posting_date = nowdate()
    receipt.insert()
    receipt.custom_bsp_delivery_note_file = evidence(receipt, "delivery note")
    receipt.custom_bsp_supplier_invoice_file = evidence(receipt, "supplier invoice")
    receipt.custom_bsp_supplier_invoice_no = "ZZTEST RECEIPT " + tag
    receipt.custom_bsp_supplier_invoice_date = nowdate()
    receipt.save()
    receipt.submit()
    invoice = a.prepare_payment_order("Purchase Receipt", receipt.name)
    frappe.set_user(ACCOUNTS)
    invoice.bill_no = "ZZTEST GL " + tag
    invoice.bill_date = invoice.posting_date = invoice.due_date = nowdate()
    invoice.insert()
    invoice.custom_bsp_supplier_invoice_file = evidence(invoice, "payment order invoice")
    invoice.save()
    view = a.get_payment_order(invoice.name)
    check("Draft exposes manual GL and journal coding", view["accounting"]["editable"] and not view["accounting"]["journalCode"])
    service_rows = [r for r in invoice.items if r.item_code != stock]
    stock_row = next(r for r in invoice.items if r.item_code == stock)
    lines = [dict(id=r.name, account=account) for r, account in zip(service_rows, accounts)]

    def save(code="UTIL-QC", values=None, modified=None):
        doc = frappe.get_doc("Purchase Invoice", invoice.name)
        return gl.save_accounting(doc.name, modified or str(doc.modified), code,
                                  lines if values is None else values)

    blocked("Stale edit is refused", lambda: save(modified="2000-01-01"), "another session")
    blocked("Unknown line cannot be inserted through accounting API", lambda: save(values=[dict(id="bad", account=accounts[0])]), "existing")
    blocked("Duplicate line is refused", lambda: save(values=[lines[0], lines[0]]), "once")
    blocked("Bank cannot be used as an expense GL", lambda: save(values=[dict(id=service_rows[0].name, account="RAK BANK - AE")]), "expense GL")
    blocked("Group account is refused", lambda: save(values=[dict(id=service_rows[0].name, account=parent)]), "expense GL")
    other_company_account = frappe.db.get_value("Account", {"company": ["!=", COMPANY], "is_group": 0, "root_type": "Expense"})
    blocked("Another company's GL cannot be selected", lambda: save(values=[dict(id=service_rows[0].name, account=other_company_account)]))
    frappe.db.savepoint("disabled_account")
    frappe.db.set_value("Account", accounts[0], "disabled", 1)
    frappe.clear_document_cache("Account", accounts[0])
    blocked("Disabled GL cannot be selected", lambda: save(values=[lines[0]]), "enabled expense")
    frappe.db.rollback(save_point="disabled_account")
    frappe.clear_document_cache("Account", accounts[0])
    blocked("Stock receipt accounting cannot be overridden", lambda: save(values=[dict(id=stock_row.name, account=accounts[0])]), "Stock")
    blocked("Invalid journal code is refused", lambda: save(code="<script>"), "Journal code")
    blocked("Blank journal code is refused", lambda: save(code=""), "journal code")
    view = save(code=" util-qc ")
    invoice.reload()
    check("Journal code is stored in a consistent format", invoice.get(gl.JOURNAL) == "UTIL-QC")
    check("Different service lines retain different selected GLs", [r.expense_account for r in invoice.items[:2]] == accounts)
    check("Displayed accounts include code and name", all("QC" + tag in r["label"] for r in view["accounting"]["lines"][:2]))
    check("Stock account and receipt linkage are preserved", invoice.items[2].expense_account == stock_row.expense_account and invoice.items[2].purchase_receipt == receipt.name)
    check("Draft coding creates no ledger postings", not frappe.db.count("GL Entry", {"voucher_type": "Purchase Invoice", "voucher_no": invoice.name}))
    check("Manual accounting confirmation is recorded", view["accounting"]["confirmed"])
    invoice = apply_workflow(invoice.reload(), "Send for Approval")
    blocked("Pending codes cannot be changed through BS screen", lambda: save(), "draft or rejected")

    def native_change(field):
        doc = frappe.get_doc("Purchase Invoice", invoice.name)
        if field == "journal":
            doc.set(gl.JOURNAL, "CHANGED")
        else:
            doc.items[0].expense_account = accounts[1]
        doc.save()

    blocked("Pending journal cannot be edited in native form", lambda: native_change("journal"), "locked")
    blocked("Pending GL cannot be edited in native form", lambda: native_change("account"), "locked")
    blocked("Accounts preparer cannot approve", lambda: a.invoice_action(invoice.name, str(invoice.modified), "Approve"), "Only Mohan")
    frappe.set_user(MANAGER)
    invoice = apply_workflow(invoice.reload(), "Reject")
    frappe.set_user(ACCOUNTS)
    check("Rejected invoice allows accounting correction", save()["accounting"]["editable"])
    invoice = apply_workflow(invoice.reload(), "Send for Approval")
    frappe.set_user(MANAGER)
    journals = frappe.db.count("Journal Entry")
    invoice = apply_workflow(invoice.reload(), "Approve")
    ledger = gl.get_ledger(invoice.name)
    check("Approval creates balanced invoice ledger entries", bool(ledger["records"]) and abs(sum(r["debit"]-r["credit"] for r in ledger["records"])) < .000001)
    check("Each selected expense account receives its actual invoice debit", all(abs(sum(r["debit"] for r in ledger["records"] if r["account"] == account)-90) < .000001 for account in accounts))
    check("Journal classification reaches every invoice GL entry", all(r["journalCode"] == "UTIL-QC" for r in ledger["records"]))
    check("Invoice remains the accounting voucher; no duplicate Journal Entry", frappe.db.count("Journal Entry") == journals)
    check("Approved invoice exposes ledger and keeps coding locked", a.get_payment_order(invoice.name)["accounting"]["canViewLedger"] and not a.get_payment_order(invoice.name)["accounting"]["editable"])
    blocked("Approved GL cannot change via native allow-on-submit field", lambda: native_change("account"), "cannot be changed")
    check("Approved Payment Order still prepares standard supplier payment", a.prepare_payment(invoice.name).doctype == "Payment Entry")
    frappe.set_user(BUYER)
    blocked("User without accounting access cannot read ledger", lambda: gl.get_ledger(invoice.name))
    blocked("User without invoice write access cannot save codes", lambda: save())
    frappe.set_user(MANAGER)
    invoice.reload()
    invoice.workflow_state = "Cancelled"
    invoice.cancel()
    reversed_ledger = gl.get_ledger(invoice.name)
    check("Cancellation preserves journal classification on ledger history", bool(reversed_ledger["records"]) and all(r["journalCode"] == "UTIL-QC" for r in reversed_ledger["records"]))
    check("Cancelled invoice has no active accounting effect", not frappe.db.count("GL Entry", {"voucher_type": "Purchase Invoice", "voucher_no": invoice.name,"is_cancelled":0}))
    print(json.dumps(dict(passed=len(RESULTS), tests=RESULTS), indent=2))


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    try:
        run()
    finally:
        cleanup_files()
        frappe.db.rollback()
        frappe.destroy()
