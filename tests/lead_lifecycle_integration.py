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
opp_spec = importlib.util.spec_from_file_location("bsgroup.utils.opportunity", root / "bsgroup/utils/opportunity.py")
opp_module = importlib.util.module_from_spec(opp_spec)
sys.modules[opp_spec.name] = opp_module
opp_spec.loader.exec_module(opp_module)
import bsgroup.utils
bsgroup.utils.opportunity = opp_module
original_get_hooks = frappe.get_hooks

def hooks(hook=None, *args, **kwargs):
    result = original_get_hooks(hook, *args, **kwargs)
    if hook == "doc_events":
        result = dict(result)
        result["Lead"] = {"before_validate": ["bsgroup.lead_lifecycle.before_validate"], "validate": ["bsgroup.lead_lifecycle.validate"]}
        result["Opportunity"] = dict(result.get("Opportunity", {}))
        result["Opportunity"]["before_insert"] = list(result["Opportunity"].get("before_insert", [])) + ["bsgroup.lead_lifecycle.guard_conversion", "bsgroup.utils.opportunity.validate_creation_source"]
        result["Opportunity"]["after_delete"] = ["bsgroup.lead_lifecycle.opportunity_deleted"]
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
    for source, party in [("Prospect", "test"), ("Customer", ""), ("Customer", "__missing_customer__"), ("Lead", "__missing_lead__")]:
        rejects(lambda source=source, party=party: opp_module.validate_creation_source(frappe._dict(opportunity_from=source, party_name=party, opportunity_amount=100)), "reject invalid new opportunity source " + source + ":" + party)
    customer = frappe.get_doc({"doctype": "Customer", "customer_name": "Opportunity source test", "customer_type": "Company"}).insert()
    opp_module.validate_creation_source(frappe._dict(opportunity_from="Customer", party_name=customer.name, opportunity_amount=100))
    check(True, "existing customer accepted for manual opportunity")
    for amount in (None, 0, -1):
        rejects(lambda amount=amount: opp_module.validate_creation_source(frappe._dict(opportunity_from="Customer", party_name=customer.name, opportunity_amount=amount)), "reject missing or nonpositive amount " + str(amount))
    now = module.now_datetime()
    check(not module.overdue(now - timedelta(hours=24) + timedelta(seconds=1), now), "not delayed before 24 hours")
    check(module.overdue(now - timedelta(hours=24), now), "delayed at exactly 24 hours")
    lead = frappe.get_doc({"doctype":"Lead", "first_name":"Lifecycle transaction test", "company_name":"Lifecycle test"}).insert()
    check(lead.status == "Open", "new lead defaults Open")
    lead.title = "Network upgrade enquiry"
    lead.save()
    lead.reload()
    check(lead.title == "Network upgrade enquiry", "Open Lead title can be edited")
    lead.company_name = "Updated lifecycle organization"
    lead.save()
    lead.reload()
    check(lead.title == "Network upgrade enquiry", "manual title persists through later native saves")

    lead.custom_requirement = "Customer requires 20 network switches."
    lead.custom_next_follow_up_date = "2026-11-01"
    lead.save()
    lead.reload()
    check(lead.custom_requirement == "Customer requires 20 network switches.", "manual requirement persists after saving and reopening")
    check(str(lead.custom_next_follow_up_date) == "2026-11-01", "selected follow-up date persists on Lead")
    lead.custom_next_follow_up_date = None
    lead.save()
    lead.reload()
    check(not lead.custom_next_follow_up_date, "optional follow-up date can be cleared")
    lead.creation = now - timedelta(hours=25)
    frappe.db.set_value("Lead", lead.name, "creation", lead.creation, update_modified=False)
    lead.save()
    check(lead.status == "Delayed", "aged lead becomes Delayed on save")
    lead.title = "Not allowed after delay"
    rejects(lead.save, "Delayed Lead title edit is blocked")
    lead.reload()
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
    mapped.opportunity_amount = 100
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
    mapped.delete()
    check(frappe.db.get_value("Lead", lead.name, "status") == "Delayed", "deleting final Opportunity reopens aged Lead as Delayed")
    frappe.db.set_value("Lead", lead.name, "creation", now, update_modified=False)
    frappe.db.set_value("Lead", lead.name, "status", "Opportunity", update_modified=False)
    module.mark_delayed()
    check(frappe.db.get_value("Lead", lead.name, "status") == "Open", "scheduler repairs stale closed Lead under 24 hours")
    check(module.make_opportunity(lead.name).is_new(), "repaired Lead can convert again")
    lead.reload()
    lead.company = lead.company or frappe.db.get_value("Company", {}, "name")
    lead.save()
    converted = module.confirm_opportunity(lead.name, "Confirmed conversion test", 250)
    check(frappe.db.exists("Opportunity", converted), "OK creates a saved Opportunity")
    check(frappe.db.get_value("Lead", lead.name, "status") == "Opportunity", "confirmed conversion closes Lead only after insert")
    rejects(lambda: module.confirm_opportunity(lead.name, "Repeat click"), "duplicate confirmation cannot create a second Opportunity")
    frappe.delete_doc("Opportunity", converted)
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
