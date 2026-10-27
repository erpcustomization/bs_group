"""LOCAL site only. Installs additive schema; business test records roll back."""
import sys
from pathlib import Path
import frappe

frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
original_enqueue = frappe.enqueue
def enqueue(method, *args, **kwargs):
    # Run schema cleanup synchronously in this local test rather than requiring
    # capacity in the unrelated background worker queue.
    if method == 'frappe.model.delete_doc.delete_dynamic_links':
        kwargs['now'] = True
        kwargs['enqueue_after_commit'] = False
    return original_enqueue(method, *args, **kwargs)
frappe.enqueue = enqueue
root = Path(__file__).resolve().parents[1]
import bsgroup, bsgroup.hooks, bsgroup.bs_group, bsgroup.bs_group.doctype
frappe.clear_cache()
bsgroup.__path__.insert(0, str(root / "bsgroup"))
bsgroup.bs_group.__file__ = str(root / "bsgroup/bs_group/__init__.py")
bsgroup.bs_group.__path__.insert(0, str(root / "bsgroup/bs_group"))
bsgroup.bs_group.doctype.__path__.insert(0, str(root / "bsgroup/bs_group/doctype"))
from bsgroup import site_survey, site_survey_setup, opportunity_intake
original_hooks = frappe.get_hooks

def hooks(hook=None, *args, **kwargs):
    result = original_hooks(hook, *args, **kwargs)
    if hook == "doc_events":
        result = dict(result)
        result["Opportunity"] = dict(result.get("Opportunity", {}))
        result["Opportunity"]["validate"] = ["bsgroup.opportunity_intake.validate", "bsgroup.site_survey.validate_opportunity"]
        result["Opportunity"]["on_update"] = ["bsgroup.site_survey.create_requests"]
        result["Presales Request"] = dict(result.get("Presales Request", {}))
        result["Presales Request"]["validate"] = ["bsgroup.site_survey.validate_presales", "bsgroup.opportunity_intake.guard_presales"]
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
    site_survey_setup.ensure_navigation()
    customer = frappe.get_doc(dict(doctype="Customer", customer_name="Survey integration fixture", customer_type="Company")).insert()
    company = frappe.db.get_value("Company", {}, "name")
    def opportunity(elv=0, technical=0, **intake):
        return frappe.get_doc(dict(doctype="Opportunity", opportunity_from="Customer", party_name=customer.name,
            opportunity_amount=1234, company=company, currency=frappe.db.get_value("Company", company, "default_currency"),
            opportunity_owner="Administrator", sales_stage=frappe.db.get_value("Sales Stage", {}, "name"), custom_subject="Survey fixture", custom_organization_name=customer.customer_name,
            custom_presales_required=1, custom_elv_site_survey_required=elv, custom_technical_site_survey_required=technical,
            **dict(dict(custom_enquiry='Inspect the existing network and propose improvements.',custom_business_type='Supply and Installation',custom_installation_type='Other',custom_survey_step=3,
                custom_survey_instructions='Maintain the existing customer system.',custom_survey_location='Customer office, Dubai',custom_survey_contact_name='Survey contact',custom_survey_contact_phone='+971501234567'), **intake))).insert()
    plain = opportunity()
    check(not plain.custom_site_survey_request, "no survey without survey options")
    for solution in opportunity_intake.ADDITIONAL_SOLUTIONS:
        service = opportunity(custom_business_type='Service', custom_service_type=solution,
            custom_service_survey='No Site Survey Required', custom_service_details='Service scope')
        check(service.custom_service_type == solution, 'service category '+solution)
        installation = opportunity(custom_installation_type=solution)
        check(installation.custom_installation_type == solution, 'installation category '+solution)
    staged = opportunity(1,0,custom_survey_step=0,custom_survey_instructions='',custom_survey_location='',custom_survey_contact_name='',custom_survey_contact_phone='')
    check(not staged.custom_site_survey_request, 'no request before instructions confirmed')
    staged.custom_survey_instructions = 'Inspect camera coverage and cable routes.'
    staged.custom_survey_step = 1
    staged.save()
    staged.reload()
    check(staged.custom_survey_instructions=='Inspect camera coverage and cable routes.' and not staged.custom_site_survey_request, 'instructions persist without dispatch')
    staged.custom_survey_step = 2
    rejects(staged.save,'location required at second confirmation')
    staged.reload()
    staged.custom_survey_step = 2
    staged.custom_survey_location = 'Building A, floor 2, reception'
    staged.save()
    staged.reload()
    check(staged.custom_survey_step==2 and not staged.custom_site_survey_request, 'location saved without dispatch')
    staged.custom_survey_step = 3
    rejects(staged.save,'contact phone required before dispatch')
    staged.reload()
    staged.custom_survey_step = 3
    staged.custom_survey_contact_phone = '+971501234567'
    rejects(staged.save,'contact name required before dispatch')
    staged.reload()
    staged.custom_survey_step = 3
    staged.custom_survey_contact_phone = '+971501234567'
    staged.custom_survey_contact_name = 'Site contact'
    staged.save()
    staged.reload()
    dispatched = frappe.get_doc('Site Survey Request',staged.custom_site_survey_request)
    for field in ('custom_enquiry','custom_survey_instructions','custom_survey_location','custom_survey_contact_name','custom_survey_contact_phone'):
        check(staged.get(field) in dispatched.survey_request_details, 'request snapshot includes '+field)
    original_details = dispatched.survey_request_details
    dispatched.survey_request_details = 'Overwritten'
    check(dispatched.custom_survey_instructions==staged.custom_survey_instructions and dispatched.site_address==staged.custom_survey_location and dispatched.contact_phone==staged.custom_survey_contact_phone,'complete instructions location and phone reach Projects')
    dispatched.save()
    check(dispatched.survey_request_details == original_details, 'request snapshot cannot be overwritten on survey save')
    check(dispatched.contact_phone==staged.custom_survey_contact_phone,'survey phone retained on later saves')
    check(dispatched.contact_person==staged.custom_survey_contact_name,'survey contact name retained on later saves')
    staged.save()
    check(frappe.db.count('Site Survey Request',{'opportunity':staged.name})==1,'repeated final save creates no duplicate')
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
    for kind in ('', 'Invalid'):
        rejects(lambda: opportunity(custom_business_type=kind), "category mandatory "+kind)
    rejects(lambda: opportunity(custom_business_type='Service',custom_service_type=''), "service subtype mandatory")
    for service_type in ('CCTV', '3CX', 'ELV'):
        for decision, expected in (('Site Survey by ELV',(1,0)), ('Site Survey by Technical Team',(0,1)), ('No Site Survey Required',(0,0))):
            service = opportunity(custom_business_type='Service', custom_service_type=service_type,
                custom_service_survey=decision, custom_service_details='Maintain the existing customer system.')
            check((service.custom_elv_site_survey_required,service.custom_technical_site_survey_required)==expected, 'service team routing '+service_type+decision)
            check(bool(service.custom_site_survey_request)==any(expected), 'service survey creation '+decision)
            if any(expected):
                request = frappe.get_doc('Site Survey Request',service.custom_site_survey_request)
                check(request.custom_service_details==service.custom_service_details, 'service requirement reaches Projects')
                check(frappe.db.get_value('Presales Request', request.presales_request, 'custom_service_details')==service.custom_service_details, 'service requirement reaches Presales')
                service.reload().save()
                check(frappe.db.count('Site Survey Request', {'opportunity':service.name})==1, 'service repeat save does not duplicate')
    rejects(lambda: opportunity(custom_business_type='Service',custom_service_type='CCTV'), 'service survey decision mandatory')
    rejects(lambda: opportunity(custom_business_type='Service',custom_service_type='CCTV',custom_service_survey='No Site Survey Required'), 'service details mandatory without survey')
    for category in ('CCTV', '3CX', 'Networking', 'Other'):
        if category == 'CCTV':
            for number in (0, -1):
                rejects(lambda: opportunity(custom_business_type='Supply and Installation', custom_installation_type=category, custom_camera_count=number), "invalid camera count")
            rejects(lambda: opportunity(custom_business_type='Supply and Installation', custom_installation_type=category, custom_camera_count=30), "30 requires survey decision")
            high = opportunity(custom_business_type='Supply and Installation', custom_installation_type=category, custom_camera_count=30, custom_site_survey_needed='Yes')
            check(bool(high.custom_site_survey_request), "30 cameras and Yes creates survey")
            high = opportunity(custom_business_type='Supply and Installation', custom_installation_type=category, custom_camera_count=31, custom_site_survey_needed='No')
            check(not high.custom_site_survey_request and not high.custom_presales_required, "No survey decision respected")
        else:
            other = opportunity(custom_business_type='Supply and Installation', custom_installation_type=category)
            check(not other.custom_site_survey_request, "no invented specific routing for "+category)
    for intake in (dict(custom_business_type='Supply'), dict(custom_business_type='Supply and Installation', custom_installation_type='CCTV', custom_camera_count=29)):
        rejects(lambda: opportunity(**intake), "supply/small CCTV blocks presales flags")
        draft = frappe.get_doc(dict(doctype='Opportunity', opportunity_from='Customer',party_name=customer.name,company=company,
            opportunity_amount=200,custom_subject='Direct costing fixture',custom_organization_name=customer.customer_name,**intake)).insert()
        check(not draft.custom_site_survey_request and not draft.custom_presales_required, "direct costing without survey")
        rejects(lambda: opportunity_intake.guard_presales(frappe.get_doc(dict(doctype='Presales Request',opportunity=draft.name))), "direct Presales creation blocked")
    existing = frappe.get_doc(dict(doctype="Presales Request", opportunity=plain.name,
        party_type="Customer", party=customer.name, subject="Existing intake", status="Open", company=company,
        estimated_value=1234, presales_owner="Administrator", requested_by="Administrator", priority="Medium",
        request_date=frappe.utils.nowdate(), due_date=frappe.utils.nowdate(), solution_summary="Existing scope",
        scope_details="Existing customer requirement")).insert()
    plain.reload()
    plain.custom_elv_site_survey_required = 1
    plain.custom_survey_step = 3
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
    for dt in ("Sidebar", "Workspace Sidebar", "Custom Sidebar"):
        if frappe.db.exists("DocType",dt):
            for n in frappe.get_all(dt,pluck="name"):
                items=frappe.get_doc(dt,n).get("sidebar_items" if dt == "Custom Sidebar" else "items") or []
                check(sum(r.link_to=="Site Survey Request" for r in items)<=1, "unique survey sidebar link "+n)
                project = next((i for i,r in enumerate(items) if r.link_type=="DocType" and r.link_to=="Project"),None)
                if project is not None:
                    check(project > 0 and items[project-1].link_to=="Site Survey Request", "survey immediately before Project "+n)
    print("PASS",len(checks),"checks")
finally:
    frappe.enqueue = original_enqueue
    frappe.db.rollback()
    frappe.clear_cache()
    frappe.destroy()
