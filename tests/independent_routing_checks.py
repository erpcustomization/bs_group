"""Exercise actual draft creation for each routing choice; roll back test records."""
from pathlib import Path
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
frappe.init(site='rel1-test.local', sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
from bsgroup.opportunity_routing_setup import execute
from bsgroup.opportunity_intake import validate, create_no_survey_cost_sheet
from bsgroup.site_survey import create_requests
try:
    execute()
    frappe.db.commit()
    candidate = next(r.name for r in frappe.get_all('Opportunity', fields=['name'])
        if not any(frappe.db.exists(dt, {'opportunity': r.name}) for dt in ('Deal Cost Sheet', 'Presales Request', 'Site Survey Request')))
    for kind in ('Service', 'Supply and Installation'):
        for survey in ('No Site Survey Required', 'Site Survey by ELV', 'Site Survey by Technical Team'):
            for support in ('No', 'Yes'):
                frappe.db.savepoint('routing_case')
                doc = frappe.get_doc('Opportunity', candidate)
                values = dict(custom_business_type=kind, custom_service_type='ELV', custom_installation_type='3CX',
                    custom_service_survey=survey, custom_presales_support=support, custom_site_survey_request=None,
                    custom_presales_required=0, custom_elv_site_survey_required=0, custom_technical_site_survey_required=0,
                    custom_enquiry='Routing test', custom_survey_instructions='Inspect installation', custom_survey_location='Test location',
                    custom_survey_contact_name='Test contact', custom_survey_contact_phone='0500000000',
                    custom_decision_maker_known='Yes', custom_competition_known='No', custom_budget_confirmed='No', opportunity_amount=1000)
                doc.update(values)
                validate(doc)
                assert doc.custom_presales_required == int(support == 'Yes')
                for field in ('custom_presales_required', 'custom_elv_site_survey_required', 'custom_technical_site_survey_required', 'custom_survey_step'):
                    values[field] = doc.get(field)
                frappe.db.set_value('Opportunity', candidate, values, update_modified=False)
                create_requests(doc)
                create_requests(doc)
                create_no_survey_cost_sheet(doc)
                create_no_survey_cost_sheet(doc)
                assert frappe.db.count('Site Survey Request', {'opportunity':candidate}) == int(survey != 'No Site Survey Required'), (kind, survey, support, 'survey')
                assert frappe.db.count('Presales Request', {'opportunity':candidate}) == int(support == 'Yes'), (kind, survey, support, 'presales')
                assert frappe.db.count('Deal Cost Sheet', {'opportunity':candidate}) == int(support == 'No' and survey == 'No Site Survey Required'), (kind, survey, support, 'DCS')
                print('PASS', kind, survey, support)
                frappe.db.rollback(save_point='routing_case')
    print('PASS all 12 routes and repeated-save deduplication')
finally:
    frappe.db.rollback()
    frappe.destroy()
