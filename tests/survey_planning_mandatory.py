"""Local Frappe integration: mandatory planning without blocking automatic intake."""
from pathlib import Path
import importlib.util
import frappe
import bsgroup

root = Path(__file__).resolve().parents[1]
bsgroup.__path__.insert(0, str(root / "bsgroup"))
frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
spec = importlib.util.spec_from_file_location("planning_controller", root / "bsgroup/bs_group/doctype/site_survey_request/site_survey_request.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
frappe.controllers.setdefault(frappe.local.site, {})["Site Survey Request"] = module.SiteSurveyRequest
meta = frappe.get_meta("Site Survey Request")
for field in ("assigned_to", "planned_date"):
    meta.get_field(field).reqd = 1

def rejected(doc, missing):
    try:
        doc.save()
    except frappe.MandatoryError as exc:
        assert missing in str(exc), str(exc)
        doc.reload()
    else:
        raise AssertionError("Saved without " + missing)

try:
    from bsgroup.site_survey import create_requests
    candidate = next(n for n in frappe.get_all("Opportunity", pluck="name")
                     if not frappe.db.exists("Site Survey Request", {"opportunity": n}))
    opp = frappe.get_doc("Opportunity", candidate)
    opp.update(dict(custom_elv_site_survey_required=1, custom_technical_site_survey_required=0,
                    custom_presales_required=0, custom_survey_step=3))
    frappe.db.set_value("Opportunity", candidate, {
        "custom_elv_site_survey_required": 1, "custom_technical_site_survey_required": 0,
        "custom_presales_required": 0, "custom_survey_step": 3}, update_modified=False)
    create_requests(opp)
    survey = frappe.get_doc("Site Survey Request", opp.custom_site_survey_request)
    assert survey.status == "Requested" and not survey.assigned_to and not survey.planned_date
    rejected(survey, "assigned_to")
    survey.assigned_to = "Administrator"
    rejected(survey, "planned_date")
    survey.assigned_to = "Administrator"
    survey.planned_date = frappe.utils.nowdate()
    survey.save()
    assert survey.status == "Scheduled"
    survey.assigned_to = None
    rejected(survey, "assigned_to")
    survey.status = "Completed"
    survey.assigned_to = None
    survey.results = "Survey result fixture"
    rejected(survey, "assigned_to")
    new = module.SiteSurveyRequest({"doctype": "Site Survey Request", "__islocal": 1})
    new.flags.from_opportunity = True
    missing = dict(new._get_missing_mandatory_fields())
    assert "opportunity" in missing and "company" in missing
    assert "assigned_to" not in missing and "planned_date" not in missing
    new.flags.from_opportunity = False
    assert "assigned_to" in dict(new._get_missing_mandatory_fields())
    print("PASS: automatic intake, both planning requirements, schedule save, completion blocked without planning, other mandatory fields preserved; rollback", flush=True)
finally:
    frappe.db.rollback()
    frappe.destroy()
