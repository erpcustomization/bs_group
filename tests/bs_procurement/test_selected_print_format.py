"""Read-only check of the existing September print format and BS PDF route."""
import hashlib
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import frappe
from pypdf import PdfReader

frappe.init(site="rel1-test.local",sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
checks=[]
def check(label,value):
    assert value,label
    checks.append(label)
    print("PASS",label,flush=True)
try:
    from bsgroup import procurement as p
    name="PUR-ORD-2026-02408"
    original=frappe.get_doc("Print Format","Purchase Order Print Format").as_dict()
    letterhead=frappe.get_doc("Letter Head","Order Letterhead").as_dict()
    with patch("frappe.utils.print_format.download_pdf") as download:
        p.pdf(name)
        check("BS PDF selects September format and existing Order Letterhead",
              download.call_args.kwargs==dict(format="Purchase Order Print Format",
                                              no_letterhead=0,letterhead="Order Letterhead"))
    p.pdf(name)
    pdf=frappe.local.response.filecontent
    text="\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    for label in ("Vendor Address","Deliver To","Tax %","Sub Total","Terms & Conditions","E- Approved"):
        check("September PDF retains "+label,label in text)
    check("Original print format is unchanged",
          original==frappe.get_doc("Print Format","Purchase Order Print Format").as_dict())
    check("Original letterhead is unchanged",
          letterhead==frappe.get_doc("Letter Head","Order Letterhead").as_dict())
    target=Path(frappe.get_app_path("bsgroup")).parent/"qa_reports/September_PO_format_verified.pdf"
    target.write_bytes(pdf)
    print(json.dumps(dict(passed=len(checks),tests=checks,
                         format_hash=hashlib.sha256(original["format_data"].encode()).hexdigest(),
                         letterhead_hash=hashlib.sha256(letterhead["content"].encode()).hexdigest()),indent=2),flush=True)
finally:
    frappe.db.rollback()
    frappe.destroy()
