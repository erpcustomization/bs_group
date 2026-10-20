"""Manual PR quotations, exceptions and utility invoice evidence. Rollback only."""
import copy
import hashlib
import json
import uuid
from pathlib import Path
import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import nowdate, add_days
from bsgroup.procurement_controls import PROCUREMENT_APPROVER
from test_standard_documents import RESULTS, check, blocked, new_request, action, BUYER, OTHER, COMPANY
from qc_fixtures import FILES, pdf_content, cleanup_files

SUPPLIERS = ["A plus typing", "A Rehman tech services", "A Z I TECHNOLOGY L.L.C"]


def file_for(pr, label, content=None, private=1):
    doc = frappe.get_doc(dict(doctype="File", file_name="ZZTEST-PR-"+uuid.uuid4().hex+".pdf",
        content=content if content is not None else pdf_content(label+" "+uuid.uuid4().hex),
        is_private=private, attached_to_doctype="Material Request", attached_to_name=pr)).insert()
    FILES.append(doc.get_full_path())
    return doc


def save(p, r, data):
    r = p.get_request(r["id"])
    return p.save_request_evidence(r["id"], r["modified"], data)


def run():
    from bsgroup import procurement as p
    from bsgroup.tests.dcs_fixtures import make_user
    make_user(BUYER, ["Purchase User"])
    make_user(OTHER, ["Sales User"])
    frappe.set_user(BUYER)
    r = new_request(p, supporting={})
    check("Manual PR begins as an editable draft without supporting documents",
          r["approval"] == "Draft" and r["manual"] and r["canEditSupporting"])
    blocked("Empty manual PR cannot be sent for approval", lambda: action(p, r, "Send for Approval"), "three quotations")
    blocked("Native workflow cannot bypass the quotation requirement",
            lambda: apply_workflow(frappe.get_doc("Material Request", r["id"]), "Send for Approval"), "three quotations")
    r = save(p, r, dict(exception=True, explanation="   "))
    blocked("Exception with whitespace notes cannot be submitted",
            lambda: action(p, r, "Send for Approval"), "Enter notes")
    copies = [file_for(r["id"], "Supplier quote "+str(i)) for i in range(3)]
    quotes = [dict(supplier=s, file=f.name) for s, f in zip(SUPPLIERS, copies)]
    for count in (1, 2):
        r = save(p, r, dict(quotes=quotes[:count]))
        blocked(str(count)+" quotation(s) cannot be submitted without exception",
                lambda: action(p, r, "Send for Approval"), "three quotations")
    bad = copy.deepcopy(quotes)
    bad[1]["supplier"] = bad[0]["supplier"]
    r = save(p, r, dict(quotes=bad))
    blocked("Three files from repeated suppliers are rejected", lambda: action(p, r, "Send for Approval"), "different suppliers")
    duplicate = file_for(r["id"], "duplicate", content=copies[0].get_content())
    bad = copy.deepcopy(quotes); bad[1]["file"] = duplicate.name
    r = save(p, r, dict(quotes=bad))
    blocked("Renamed duplicate quotation content is rejected", lambda: action(p, r, "Send for Approval"), "duplicate content")
    other = new_request(p, supporting={})
    borrowed = file_for(other["id"], "another request")
    blocked("Another PR's attachment cannot be borrowed",
            lambda: save(p, r, dict(quotes=[dict(supplier=SUPPLIERS[0], file=borrowed.name)])), "this PR")
    # Change attachment privacy while it is still unreferenced, then verify refusal.
    public = file_for(r["id"], "privacy probe")
    public.is_private = 0; public.save()
    public_path = Path(public.get_full_path()).resolve()
    try:
        blocked("Public attachments cannot be evidence",
                lambda: save(p, r, dict(quotes=[dict(supplier=SUPPLIERS[0], file=public.name)])), "private uploads")
    finally:
        # Restore private storage so the rollback cleanup can remove this test blob.
        public.reload(); public.is_private = 1; public.save()
        FILES.append(public.get_full_path())
        if public_path.exists():
            assert public_path.is_relative_to(Path(frappe.get_site_path("public", "files")).resolve())
            public_path.unlink()
    r = save(p, r, dict(quotes=quotes))
    check("Saved quotations survive a reload with file names and supplier links",
          p.get_request(r["id"])["supporting"]["quotes"][2]["file"] == copies[2].name)
    blocked("Stale evidence save cannot overwrite current choices",
            lambda: p.save_request_evidence(r["id"], "2000-01-01", dict(exception=True, explanation="stale")))
    r = action(p, r, "Send for Approval")
    check("Three distinct supplier quotations permit submission", r["approval"] == "Pending Approval")
    check("Submission history preserves quotation file hashes",
          len(r["history"][-1]["snapshot"]["request_evidence"]["quotes"]) == 3
          and bool(r["history"][-1]["snapshot"]["request_evidence"]["quotes"][0]["sha256"]))
    blocked("Pending PR evidence cannot be edited", lambda: save(p, r, dict(exception=True, explanation="replace")), "draft or rejected")
    def native_edit():
        d = frappe.get_doc("Material Request", r["id"])
        d.custom_bsp_request_evidence = "{}"
        d.save()
    blocked("Native form cannot change protected PR evidence", native_edit, "BS approval evidence")
    expected_hash = hashlib.sha256(copies[0].get_content()).hexdigest()
    blocked("Submitted quotation cannot be deleted", lambda: frappe.delete_doc("File", copies[0].name), "procurement evidence")
    check("Blocked deletion preserves quotation bytes", hashlib.sha256(Path(copies[0].get_full_path()).read_bytes()).hexdigest() == expected_hash)
    def make_public():
        d = frappe.get_doc("File", copies[0].name); d.is_private = 0; d.save()
    blocked("Submitted quotation cannot become public", make_public, "procurement evidence")
    check("Blocked privacy change preserves the private file", Path(copies[0].get_full_path()).is_file())
    frappe.set_user(PROCUREMENT_APPROVER)
    r = p.get_request(r["id"])
    check("Mohan sees all three quotation copies and approval actions",
          "Approve" in r["actions"] and all(q["url"].startswith("/private/files/") for q in r["supporting"]["quotes"]))
    r = action(p, r, "Reject", "QC replace quotation with a justified exception")
    frappe.set_user(BUYER)
    r = save(p, r, dict(exception=True, explanation="Emergency repair: only the original supplier can provide this part."))
    r = action(p, r, "Send for Approval")
    blocked("Earlier submitted evidence remains protected after replacement",
            lambda: frappe.delete_doc("File", copies[0].name), "procurement evidence")
    check("Resubmission retains both quotation and exception snapshots",
          len([e for e in r["history"] if e["action"] == "Pending Approval"]) == 2)
    frappe.set_user(PROCUREMENT_APPROVER)
    r = action(p, r, "Approve")
    check("Mohan can approve the explained exception", r["approval"] == "Approved")
    frappe.set_user(BUYER)
    # The existing test Item is non-stock; no fake utility master is persisted.
    assert not frappe.db.get_value("Item", "ZZTEST-CLAUDE-DCS-ITEM-A", "is_stock_item")
    utility = p.create_request(dict(key=str(uuid.uuid4()), company=COMPANY,
        title="ZZTEST electricity bill — QC ONLY", schedule_date=add_days(nowdate(), 7),
        supporting=dict(kind="direct_invoice"),
        items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A", qty=1, rate=250)]))
    check("Non-stock utility PR can be created without a warehouse or sales documents",
          utility["manual"] and not utility["quotation"] and not utility["customerPO"]
          and not frappe.get_doc("Material Request", utility["id"]).items[0].warehouse)
    blocked("Utility PR without an invoice cannot be sent",
            lambda: action(p, utility, "Send for Approval"), "invoice copy")
    invoice = file_for(utility["id"], "QC electricity invoice AED 250")
    invoice2 = file_for(utility["id"], "QC second invoice copy")
    utility = save(p, utility, dict(kind="direct_invoice", invoices=[dict(file=invoice.name)]))
    blocked("Invoice alone does not waive quotations",
            lambda: action(p, utility, "Send for Approval"), "No three quotations required")
    utility = save(p, utility, dict(kind="direct_invoice", exception=True, invoices=[dict(file=invoice.name)]))
    blocked("Utility exception still requires notes",
            lambda: action(p, utility, "Send for Approval"), "Enter notes")
    good = dict(kind="direct_invoice", exception=True,
        explanation="Electricity bill for October. Regulated utility provider; competitive quotations do not apply.",
        invoices=[dict(file=invoice.name), dict(file=invoice2.name)])
    utility = save(p, utility, good)
    blocked("Duplicate invoice copies are rejected",
            lambda: save(p, utility, dict(good, invoices=[dict(file=invoice.name)]*2)), "more than once")
    utility = action(p, utility, "Send for Approval")
    check("Invoice copies plus exception and notes allow utility submission",
          utility["approval"] == "Pending Approval" and len(utility["supporting"]["invoices"]) == 2)
    blocked("Invoice evidence cannot be deleted after submission",
            lambda: frappe.delete_doc("File", invoice.name), "procurement evidence")
    frappe.set_user(PROCUREMENT_APPROVER)
    utility = p.get_request(utility["id"])
    check("Mohan sees utility invoice copies and the explanation",
          "Regulated utility" in utility["supporting"]["explanation"]
          and all(f["url"] for f in utility["supporting"]["invoices"]))
    utility = action(p, utility, "Approve")
    check("Approved utility PR remains a submitted standard Material Request",
          frappe.get_doc("Material Request", utility["id"]).docstatus == 1)
    blocked("Approved invoice evidence is locked", lambda: save(p, utility, good), "draft or rejected")
    frappe.set_user(OTHER)
    blocked("Unauthorised user cannot change PR evidence", lambda: save(p, utility, good))
    frappe.set_user("Administrator")
    source = p.get_request("MAT-MR-2026-00007")
    check("Sales-handover PR retains its separate source packet", not source["manual"] and len(source["handoverFiles"]) == 3)
    blocked("Sales PR cannot be reclassified as a manual utility PR", lambda: save(p, source, good), "manual PRs")
    print(json.dumps(dict(passed=len(RESULTS), tests=RESULTS), indent=2), flush=True)


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect(); frappe.set_user("Administrator"); frappe.flags.in_test = True
    try:
        run()
    finally:
        frappe.db.rollback()
        cleanup_files()
        frappe.destroy()
