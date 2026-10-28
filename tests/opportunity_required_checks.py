"""Local database checks; writes roll back."""
import importlib.util
import sys
from pathlib import Path
import frappe
from frappe.model.document import Document

frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
spec = importlib.util.spec_from_file_location("bsgroup.opportunity_required", Path(__file__).resolve().parents[1] / "bsgroup/opportunity_required.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
import bsgroup
bsgroup.opportunity_required = module
checks = []

def rejects(doc, label):
    try:
        module.validate(doc)
    except frappe.ValidationError:
        checks.append(label)
    else:
        raise AssertionError(label)

try:
    source = frappe.get_all("Opportunity", fields=["name", "company"], limit=1)[0]
    for dt in module.DOCTYPES:
        doc = Document({"doctype": dt, "__islocal": 1})
        doc.opportunity = None
        rejects(doc, dt + " requires Opportunity")
        doc.flags.ignore_permissions = True
        rejects(doc, dt + " cannot bypass source with permission flag")
        doc.flags.ignore_permissions = False
        doc.opportunity = "__missing_opportunity__"
        rejects(doc, dt + " rejects invalid source")
        doc.opportunity = source.name
        doc.company = source.company
        module.validate(doc)
        checks.append(dt + " accepts linked source")
        doc.company = "__different_company__"
        rejects(doc, dt + " rejects company mismatch")
        doc.company = source.company
        doc.set("__islocal", 0)
        doc.name = "__existing_fixture__"
        before = frappe._dict(opportunity=source.name)
        doc.get_doc_before_save = lambda: before
        doc.opportunity = None
        rejects(doc, dt + " cannot remove existing source")
        before.opportunity = None
        module.validate(doc)
        checks.append(dt + " preserves historical edits")
    print("PASS", len(checks), "checks:", "; ".join(checks))
finally:
    frappe.db.rollback()
    frappe.destroy()
