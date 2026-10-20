"""Generate a QC-only approved PO PDF; roll back all ERP business transactions."""
from pathlib import Path
import frappe
from test_qc_gaps import approved_pr,ready_po
from test_standard_documents import BUYER,MANAGER,po_action
from qc_fixtures import cleanup_files

frappe.init(site="rel1-test.local",sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
frappe.flags.in_test=True
try:
    from bsgroup.tests.dcs_fixtures import make_user
    from bsgroup import procurement as p
    make_user(BUYER,["Purchase User"])
    make_user(MANAGER,["Purchase User","Purchase Manager"])
    r=approved_pr(p)
    po=ready_po(p,r)
    po=po_action(p,po,"Send for Approval")
    frappe.set_user(MANAGER)
    po=po_action(p,po,"Approve")
    pdf=frappe.get_print("Purchase Order",po["id"],print_format="BS Procurement Purchase Order",
                         no_letterhead=1,as_pdf=True)
    assert pdf.startswith(b"%PDF-")
    path=Path(frappe.get_app_path("bsgroup")) / "../qa_reports/QC_ONLY_approved_PO.pdf"
    path.write_bytes(pdf)
    print("PASS Approved PO PDF generated with native ERP print engine.",flush=True)
finally:
    frappe.db.rollback()
    cleanup_files()
    frappe.destroy()
