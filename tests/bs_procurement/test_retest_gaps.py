"""Independent QC reproductions. rel1-test.local only; all postings roll back."""
import hashlib
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.utils import add_days, nowdate
from frappe.utils.file_manager import save_file
from test_standard_documents import (
    check, blocked, RESULTS, BUYER, MANAGER, COMPANY, action, new_order, po_action, payload,
)
from test_cash_and_closed_orders import journal, ACCOUNTS
from test_closed_po_invoicing import project_budget, request, approve_order
from test_sales_handover import sample_pdf
from qc_fixtures import cleanup_files
from bsgroup.tests.dcs_fixtures import make_user, make_dcs
from bsgroup import procurement as p
from bsgroup.dcs import procurement as handover

PREFIX = "ZZTEST-RETEST-GAPS-"
FILES = {}


def unique():
    return PREFIX + uuid.uuid4().hex[:12]


def negative_journals():
    # These are read-only sources: never save or submit the user's QC records.
    originals = {n: frappe.get_doc("Journal Entry", "ACC-JV-2026-" + str(n))
                 for n in range(15343, 15348)}
    for user in (MANAGER, ACCOUNTS, "Administrator"):
        frappe.set_user(user)
        for number, source in originals.items():
            blocked(f"C-1 negative variant {number} cannot save / {user}",
                    lambda source=source: frappe.copy_doc(source).insert(set_name=unique()), "negative")
    frappe.set_user(MANAGER)
    for number, source in originals.items():
        # Simulate an already-saved old draft using only our own temporary fixture.
        old = journal("ADIB Bank - AE").insert(set_name=unique())
        for target, row in zip(old.accounts, source.accounts):
            frappe.db.set_value("Journal Entry Account", target.name, {
                f: row.get(f) for f in ("account", "party_type", "party", "debit", "credit",
                    "debit_in_account_currency", "credit_in_account_currency")})
        blocked(f"C-1 existing negative draft {number} cannot submit",
                lambda name=old.name: frappe.get_doc("Journal Entry", name).submit(), "negative")
        check(f"C-1 rejected submission {number} created no ledger",
              not frappe.db.count("GL Entry", {"voucher_type": "Journal Entry", "voucher_no": old.name}))
    for field in ("debit", "credit", "debit_in_account_currency", "credit_in_account_currency"):
        from bsgroup.procurement_journals import validate_cash_journal
        doc = journal("ADIB Bank - AE")
        doc.accounts[0].set(field, -1)
        blocked("C-1 every amount field rejects a negative: " + field,
                lambda doc=doc: validate_cash_journal(doc), "negative")
    for name in ("ACC-JV-2026-15334", "ACC-JV-2026-15335"):
        check("Original cancelled QC journal remains cancelled: " + name,
              frappe.db.get_value("Journal Entry", name, "docstatus") == 2)
    for name in originals:
        check("Original QC draft remains a draft: " + str(name),
              frappe.db.get_value("Journal Entry", "ACC-JV-2026-" + str(name), "docstatus") == 0)


def legitimate_cash():
    employee = frappe.db.get_value("Employee", {"company": COMPANY, "status": "Active"})
    assert employee
    cases = (
        ("Payroll Payable - AE", "Employee settlement", None),
        ("Employee Advances - AE", "Employee settlement", employee),
        ("Secured Loans - AE", "Financing or capital settlement", None),
        ("Bank Charges - AE", "Bank charges", None),
    )
    check("H-3 Bank charges is installed in Journal Entry category options",
          "Bank charges" in frappe.get_meta("Journal Entry").get_field("custom_bsp_cash_category").options)
    for account, category, party in cases:
        frappe.set_user(ACCOUNTS)
        doc = journal(account, custom_bsp_cash_category=category,
                      custom_bsp_cash_reason="QC documented non-procurement settlement; fully rolled back.")
        if party:
            doc.accounts[0].party_type, doc.accounts[0].party = "Employee", party
        doc.insert(set_name=unique())
        check("H-3 Accounts can prepare " + account, doc.docstatus == 0)
        blocked("H-3 Accounts cannot approve " + account, lambda: doc.submit(), "Only Mohan")
        frappe.set_user(MANAGER)
        doc.reload().submit()
        check("H-3 Mohan approves and posts " + account,
              doc.docstatus == 1 and doc.custom_bsp_cash_approved_by == MANAGER
              and bool(doc.custom_bsp_cash_approved_on)
              and frappe.db.count("GL Entry", {"voucher_type": "Journal Entry",
                  "voucher_no": doc.name, "is_cancelled": 0}) == 2)
        doc.cancel()
    for category in ("Employee settlement", "Financing or capital settlement", "Bank charges"):
        blocked("H-3 category cannot disguise utility expense / " + category,
                lambda category=category: journal("Cooling Energy Bill - AE",
                    custom_bsp_cash_category=category,
                    custom_bsp_cash_reason="Invalid attempt to treat utility as an exception").insert(),
                "Direct expense")
    frappe.set_user(ACCOUNTS)
    def reclassify():
        account = frappe.get_doc("Account", "Cooling Energy Bill - AE")
        account.custom_bsp_cash_category = "Bank charges"
        account.save()
    blocked("H-3 Accounts cannot grant itself a bank-charge exception", reclassify, "Only Mohan")


def manual_budget_and_notes():
    frappe.set_user("Administrator")
    item = frappe.copy_doc(frappe.get_doc("Item", "ZZTEST-CLAUDE-DCS-ITEM-A"))
    item.item_code = item.item_name = unique()
    item.insert()
    frappe.get_doc(dict(doctype="Item Price", item_code=item.name, price_list="Standard Buying",
                        buying=1, price_list_rate=80, currency="AED", uom=item.stock_uom)).insert()
    frappe.db.set_single_value("Buying Settings", "buying_price_list", "Standard Buying")
    frappe.clear_document_cache("Buying Settings", "Buying Settings")
    frappe.set_user(BUYER)
    req = p.create_request(dict(key=str(uuid.uuid4()), company=COMPANY, title=unique(),
        schedule_date=add_days(nowdate(), 7), warehouse="Stores - AE",
        supporting=dict(exception=True, explanation="Only the authorized utility provider can supply this service."),
        items=[dict(item_code=item.name, qty=3, rate=100)]))
    def assert_budget(label):
        doc = frappe.get_doc("Material Request", req["id"])
        check(label, doc.items[0].rate == 100 and doc.items[0].amount == 300 and not doc.buying_price_list)
    assert_budget("M-1 new PR retains 100 budget rather than 80 buying price")
    for reason in (".", "...", "....................", "N/A", "aaaaaaaaaaaaaaaaaaaa", "   "):
        current = p.get_request(req["id"])
        current = p.save_request_evidence(current["id"], current["modified"],
            dict(exception=True, explanation=reason))
        blocked("L-1 inadequate reason cannot request approval: " + repr(reason),
                lambda current=current: action(p, current, "Send for Approval"), "meaningful notes")
    current = p.get_request(req["id"])
    req = p.save_request_evidence(current["id"], current["modified"],
        dict(exception=True, explanation="The sole authorized provider supplies this utility service."))
    assert_budget("M-1 supporting-document saves preserve the entered budget")
    req = action(p, req, "Send for Approval")
    assert_budget("M-1 approval request preserves the entered budget")
    frappe.set_user(MANAGER)
    req = action(p, req, "Approve")
    assert_budget("M-1 Mohan approval preserves the entered budget")
    check("L-1 meaningful exception can complete PR approval", req["approval"] == "Approved")
    return item


def exact_customer_po():
    frappe.set_user("Administrator")
    # The reported binary PDF is a read-only fixture, copied to a new synthetic quotation.
    source_pr = frappe.get_doc("Material Request", "MAT-MR-2026-00040")
    source = frappe.get_doc("File", json.loads(source_pr.custom_bsp_source_snapshot)["source_po"])
    expected = Path(source.get_full_path()).read_bytes()
    dcs = make_dcs(suffix=unique(), submit=True, company=COMPANY, currency="AED",
                  items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A", qty=1, cost_rate=100, selling_rate=150)])
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation
    q = frappe.get_doc("Quotation", make_quotation(dcs.name))
    q.flags.ignore_mandatory = q.flags.ignore_links = True
    q.custom_pipeline_stage = "Sent"
    q.submit()
    file = frappe.get_doc(dict(doctype="File", file_name=unique() + ".pdf", content=expected,
        attached_to_doctype="Quotation", attached_to_name=q.name, is_private=1)).insert()
    FILES[Path(file.get_full_path()).resolve()] = file.file_url
    q.custom_customer_po, q.custom_customer_po_reference = file.file_url, unique()
    q.custom_pipeline_stage = "Won"
    q.save()
    with (patch.object(frappe, "get_print", return_value=sample_pdf("Quotation")),
          patch.object(handover, "costing_pdf", return_value=sample_pdf("Costing"))):
        result = handover.send_to_procurement(q.name, add_days(nowdate(), 7), "Stores - AE")
    mr = frappe.get_doc("Material Request", result["name"])
    manifest = json.loads(mr.custom_bsp_source_snapshot)
    for entry in manifest["files"]:
        f = frappe.get_doc("File", entry["file"])
        FILES[Path(f.get_full_path()).resolve()] = f.file_url
    copied = next(f for f in manifest["files"] if f["kind"] == "customer_po")
    actual = Path(frappe.get_doc("File", copied["file"]).get_full_path()).read_bytes()
    check("M-2 original and handed-over customer PO have identical bytes", actual == expected)
    check("M-2 original and copy both retain the reported 1443-byte length", len(actual) == len(expected) == 1443)
    check("M-2 manifest hash represents the original binary content",
          copied["sha256"] == hashlib.sha256(expected).hexdigest())


def reject_over_budget(item):
    project, baseline = project_budget(item)
    req = request(item.name, project.name)
    approved = approve_order(new_order(p, req, qty=1))
    pending = new_order(p, req, qty=1)
    pending = p.save_order(pending["id"], pending["modified"], payload(pending))
    pending = po_action(p, pending, "Send for Approval")
    # Only this synthetic baseline is lowered to recreate a pre-existing overrun.
    frappe.db.set_value("Project Cost Baseline", baseline.name, "baseline_amount", 50)
    frappe.set_user(MANAGER)
    blocked("M-3 over-budget pending PO still cannot be approved",
            lambda: po_action(p, pending, "Approve"), "exceeds")
    rejected = po_action(p, pending, "Reject", "Project is already over budget; procurement must revise scope.")
    check("M-3 Mohan can reject an unchanged pending PO despite the existing overrun",
          rejected["status"] == "Rejected" and rejected["docstatus"] == 0)
    check("M-3 rejection does not change the already-approved PO",
          frappe.db.get_value("Purchase Order", approved["id"], "docstatus") == 1)


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect(); frappe.set_user("Administrator"); frappe.flags.in_test = True
    base = Path(frappe.get_site_path("private", "files")).resolve()
    existing = set(base.iterdir())
    try:
        make_user(BUYER, ["Purchase User"])
        make_user(ACCOUNTS, ["Accounts User", "Accounts Manager"])
        negative_journals()
        legitimate_cash()
        item = manual_budget_and_notes()
        exact_customer_po()
        reject_over_budget(item)
        print(json.dumps(dict(passed=len(RESULTS), tests=RESULTS), indent=2), flush=True)
    finally:
        frappe.db.rollback()
        cleanup_files()
        for path, url in FILES.items():
            assert path.is_relative_to(base)
            if path not in existing and not frappe.db.exists("File", {"file_url": url}):
                path.unlink(missing_ok=True)
        frappe.clear_cache(user=ACCOUNTS)
        frappe.destroy()
        print("All new test transactions rolled back; original QC records preserved.", flush=True)
