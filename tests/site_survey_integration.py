"""LOCAL site only. Installs additive schema; business test records roll back."""
import sys
from pathlib import Path
import frappe

frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
root = Path(__file__).resolve().parents[1]
import bsgroup, bsgroup.bs_group, bsgroup.bs_group.doctype
bsgroup.__path__.insert(0, str(root / "bsgroup"))
bsgroup.bs_group.__file__ = str(root / "bsgroup/bs_group/__init__.py")
bsgroup.bs_group.__path__.insert(0, str(root / "bsgroup/bs_group"))
bsgroup.bs_group.doctype.__path__.insert(0, str(root / "bsgroup/bs_group/doctype"))
from bsgroup import site_survey, site_survey_setup
original_hooks = frappe.get_hooks

def hooks(hook=None, *args, **kwargs):
    result = original_hooks(hook, *args, **kwargs)
    if hook == "doc_events":
        result = dict(result)
        result["Opportunity"] = dict(result.get("Opportunity", {}))
        result["Opportunity"]["validate"] = ["bsgroup.site_survey.validate_opportunity"]
        result["Opportunity"]["on_update"] = ["bsgroup.site_survey.create_requests"]
        result["Presales Request"] = dict(result.get("Presales Request", {}))
        result["Presales Request"]["validate"] = ["bsgroup.site_survey.validate_presales"]
    return result
frappe.get_hooks = hooks
if "--skip-setup" not in sys.argv:
    site_survey_setup.execute()
frappe.db.commit()  # schema only, before business fixtures
checks = []
def check(ok, title):
    assert ok, title
    checks.append(title)
def rejects(fn, title):
    try:
        fn()
    except frappe.ValidationError:
        checks.append(title)
    else:
        raise AssertionError(title)

try:
    customer = frappe.get_doc(dict(doctype="Customer", customer_name="Survey integration fixture", customer_type="Company")).insert()
    company = frappe.db.get_value("Company", {}, "name")
    def opportunity(elv=0, technical=0):
        return frappe.get_doc(dict(doctype="Opportunity", opportunity_from="Customer", party_name=customer.name,
            opportunity_amount=1234, company=company, currency=frappe.db.get_value("Company", company, "default_currency"),
            opportunity_owner="Administrator", sales_stage=frappe.db.get_value("Sales Stage", {}, "name"), custom_subject="Survey fixture", custom_organization_name=customer.customer_name,
            custom_presales_required=1, custom_elv_site_survey_required=elv, custom_technical_site_survey_required=technical)).insert()
    plain = opportunity()
    check(not plain.custom_site_survey_request, "no survey without survey options")
    for elv, tech in ((1,0), (0,1), (1,1)):
        opp = opportunity(elv, tech)
        survey = frappe.get_doc("Site Survey Request", opp.custom_site_survey_request)
        pre = frappe.get_doc("Presales Request", survey.presales_request)
        check((survey.elv_required, survey.technical_required)==(elv,tech), "correct survey selections "+str((elv,tech)))
        check(pre.status == site_survey.WAITING, "presales waits for results")
        check(pre.opportunity == opp.name and pre.custom_site_survey_request == survey.name, "bidirectional links")
        check(survey.salesperson == "Administrator" and survey.opportunity_amount == 1234 and survey.company == company, "sales and Opportunity details copied")
        check(not pre.presales_owner and not pre.scope_details, "no invented owner or findings")
        opp.reload().save()
        check(frappe.db.count("Site Survey Request", {"opportunity":opp.name}) == 1, "repeat save has one survey")
        check(frappe.db.count("Presales Request", {"opportunity":opp.name}) == 1, "repeat save has one presales request")
    pre.status = "Open"
    rejects(pre.save, "cannot skip pending survey")
    pre.reload()
    survey.status = "Completed"
    rejects(survey.save, "completion needs results")
    survey.reload()
    survey.status = "Completed"
    survey.results = "Site measured. Rack location confirmed."
    survey.save()
    pre.reload()
    check(pre.status == site_survey.RECEIVED, "results received releases waiting status")
    check(bool(survey.completed_by and survey.completed_on), "completion audit recorded")
    pre.status = "Open"
    rejects(pre.save, "normal presales details required after handoff")
    opp.reload()
    opp.custom_elv_site_survey_required = 0
    rejects(opp.save, "cannot silently change routed survey scope")
    check("salesperson" in site_survey.survey_query("Guest"), "restricted users see only relevant surveys")
    check(site_survey.survey_permission(survey, user="Guest") is False, "unrelated direct access denied")
    existing = frappe.get_doc(dict(doctype="Presales Request", opportunity=plain.name,
        party_type="Customer", party=customer.name, subject="Existing intake", status="Open", company=company,
        estimated_value=1234, presales_owner="Administrator", requested_by="Administrator", priority="Medium",
        request_date=frappe.utils.nowdate(), due_date=frappe.utils.nowdate(), solution_summary="Existing scope",
        scope_details="Existing customer requirement")).insert()
    plain.reload()
    plain.custom_elv_site_survey_required = 1
    plain.save()
    existing.reload()
    check(existing.status == site_survey.WAITING and bool(existing.custom_site_survey_request), "reuses existing open presales")
    check(existing.solution_summary == "Existing scope", "existing presales details preserved")
    check(frappe.db.count("Presales Request", {"opportunity":plain.name}) == 1, "no duplicate when reusing existing intake")
    invalid = opportunity()
    invalid.custom_presales_required = 0
    invalid.custom_elv_site_survey_required = 1
    rejects(invalid.save, "survey checkbox requires presales support")
    survey.reload()
    survey.requested_by = "Guest"
    rejects(survey.save, "request origin cannot be forged")
    # Setup is repeatable and must not insert duplicate navigation entries.
    for dt in ("Sidebar", "Workspace Sidebar"):
        if frappe.db.exists("DocType",dt):
            for n in frappe.get_all(dt,pluck="name"):
                items=frappe.get_doc(dt,n).get("items") or []
                check(sum(r.link_to=="Site Survey Request" for r in items)<=1, "unique survey sidebar link "+n)
    print("PASS",len(checks),"checks")
finally:
    frappe.db.rollback()
    frappe.destroy()
