"""Run with bench Python against a LOCAL test site; every write is rolled back."""
import importlib.util
import sys
from pathlib import Path
from datetime import timedelta
import frappe

frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bsgroup.lead_lifecycle", root / "bsgroup/lead_lifecycle.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
import bsgroup
bsgroup.lead_lifecycle = module
original_get_hooks = frappe.get_hooks

def hooks(hook=None, *args, **kwargs):
    result = original_get_hooks(hook, *args, **kwargs)
    if hook == "doc_events":
        result = dict(result)
        result["Lead"] = {"before_validate": ["bsgroup.lead_lifecycle.before_validate"], "validate": ["bsgroup.lead_lifecycle.validate"]}
        result["Opportunity"] = dict(result.get("Opportunity", {}))
        result["Opportunity"]["before_insert"] = list(result["Opportunity"].get("before_insert", [])) + ["bsgroup.lead_lifecycle.guard_conversion"]
    return result
frappe.get_hooks = hooks

checks = []
def check(condition, name):
    assert condition, name
    checks.append(name)

def rejects(fn, name):
    try:
        fn()
    except frappe.ValidationError:
        checks.append(name)
    else:
        raise AssertionError(name)

try:
    module.setup()
    now = module.now_datetime()
    check(not module.overdue(now - timedelta(hours=24) + timedelta(seconds=1), now), "not delayed before 24 hours")
    check(module.overdue(now - timedelta(hours=24), now), "delayed at exactly 24 hours")
    lead = frappe.get_doc({"doctype":"Lead", "first_name":"Lifecycle transaction test", "company_name":"Lifecycle test"}).insert()
    check(lead.status == "Open", "new lead defaults Open")
    lead.creation = now - timedelta(hours=25)
    frappe.db.set_value("Lead", lead.name, "creation", lead.creation, update_modified=False)
    lead.save()
    check(lead.status == "Delayed", "aged lead becomes Delayed on save")
    lead.status = "Open"
    lead.save()
    check(lead.status == "Delayed", "editing cannot reset age")
    lead.status = "Dropped"
    rejects(lead.save, "drop requires fresh note")
    lead.reload()
    lead.append("notes", {"note":"Unrelated earlier note", "added_by":"Administrator", "added_on":now})
    lead.save()
    lead.status = "Dropped"
    rejects(lead.save, "old note cannot justify drop")
    lead.reload()
    lead.status = "Dropped"
    lead.append("notes", {"note":"<p> &nbsp; </p>"})
    rejects(lead.save, "HTML-only note rejected")
    lead.reload()
    lead.status = "Dropped"
    lead.append("notes", {"note":"Dropped: outside service scope"})
    lead.save()
    check(lead.status == "Dropped", "drop with reason persists")
    check(lead.notes[-1].added_by == "Administrator", "drop note attributed to actor")
    module.mark_delayed()
    check(frappe.db.get_value("Lead", lead.name, "status") == "Dropped", "scheduler leaves dropped lead untouched")
    rejects(lambda: module.make_opportunity(lead.name), "dropped conversion blocked")
    lead.status = "Open"
    lead.save()
    check(lead.status == "Delayed", "reopened older lead stays delayed")
    lead.status = "Opportunity"
    rejects(lead.save, "manual closure without Opportunity rejected")
    lead.reload()
    frappe.get_doc({"doctype":"ToDo", "reference_type":"Lead", "reference_name":lead.name, "allocated_to":"Administrator", "description":"Lead lifecycle assignment test"}).insert()
    module.load_responsibility(lead)
    check(lead.get_onload("bsi_sales_responsibility")["source"] == "Lead", "direct Lead assignment is displayed")
    mapped = module.make_opportunity(lead.name)
    check(mapped.is_new(), "mapper returns unsaved Opportunity")
    check(frappe.db.get_value("Lead", lead.name, "status") == "Delayed", "opening mapper does not close lead")
    mapped.company = lead.company or frappe.db.get_value("Company", {}, "name")
    mapped.currency = frappe.db.get_value("Company", mapped.company, "default_currency")
    mapped.opportunity_type = "Sales"
    mapped.custom_subject = "Lifecycle conversion test"
    mapped.sales_stage = frappe.db.get_value("Sales Stage", {}, "name")
    mapped.insert()
    check(frappe.db.get_value("Lead", lead.name, "status") == "Opportunity", "saved Opportunity closes lead natively")
    lead.reload()
    module.load_responsibility(lead)
    responsibility = lead.get_onload("bsi_sales_responsibility")
    check(responsibility["source"] == "Opportunity" and responsibility["users"][0]["user"] == "Administrator", "converted Lead displays transferred Opportunity assignment")
    lead.status = "Dropped"
    lead.append("notes", {"note":"Cannot drop a converted lead"})
    rejects(lead.save, "linked lead cannot be dropped")
    module.mark_delayed()
    check(frappe.db.get_value("Lead", lead.name, "status") == "Opportunity", "scheduler leaves closed lead untouched")
    frappe.set_user("Guest")
    try:
        module.make_opportunity(lead.name)
    except frappe.PermissionError:
        checks.append("conversion enforces write permission")
    else:
        raise AssertionError("permission check missing")
    print("PASS", len(checks), "checks:", "; ".join(checks))
finally:
    frappe.db.rollback()
    frappe.set_user("Administrator")
    frappe.clear_cache(doctype="Lead")
    frappe.destroy()
