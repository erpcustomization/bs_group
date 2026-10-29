"""Real document completion and status checks; all business records rolled back."""
from pathlib import Path
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
frappe.init(site='rel1-test.local', sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
from bsgroup.opportunity_intake import validate
from bsgroup.site_survey import create_requests, presales_handoff, opportunity_survey_results, RECEIVED
from bsgroup.opportunity_progress import resolve_many
try:
    candidate = next(r.name for r in frappe.get_all('Opportunity', fields=['name'])
        if not any(frappe.db.exists(dt, {'opportunity': r.name}) for dt in
                   ('Deal Cost Sheet', 'Presales Request', 'Site Survey Request')))
    for support in ('No', 'Yes'):
        frappe.db.savepoint('completion_case')
        doc = frappe.get_doc('Opportunity', candidate)
        values = dict(status='Open', custom_business_type='Service', custom_service_type='ELV',
            custom_service_survey='Site Survey by ELV', custom_presales_support=support,
            custom_site_survey_request=None, custom_enquiry='Survey completion routing test',
            custom_survey_instructions='Inspect installation', custom_survey_location='Test location',
            custom_survey_contact_name='Test contact', custom_survey_contact_phone='0500000000',
            custom_decision_maker_known='Yes', custom_competition_known='No', custom_budget_confirmed='No')
        doc.update(values)
        validate(doc)
        for field in ('custom_presales_required', 'custom_elv_site_survey_required',
                      'custom_technical_site_survey_required', 'custom_survey_step'):
            values[field] = doc.get(field)
        frappe.db.set_value('Opportunity', candidate, values, update_modified=False)
        create_requests(doc)
        survey = frappe.get_doc('Site Survey Request', doc.custom_site_survey_request)
        assert not frappe.db.exists('Deal Cost Sheet', {'opportunity': candidate})
        if support == 'Yes':
            assert presales_handoff(survey.presales_request)['label'] == 'Awaiting Site Survey'
        survey.results = 'Survey completed: install two network points.'
        survey.status = 'Completed'
        survey.save()
        survey.save()
        assert opportunity_survey_results(candidate)[0].results == survey.results
        label = resolve_many([doc])[candidate]['label']
        if support == 'No':
            assert frappe.db.count('Deal Cost Sheet', {'opportunity': candidate}) == 1
            assert label == 'Deal Cost Sheet in Progress', label
        else:
            assert not frappe.db.exists('Deal Cost Sheet', {'opportunity': candidate})
            pre = frappe.get_doc('Presales Request', survey.presales_request)
            assert pre.status == RECEIVED and pre.custom_survey_results == survey.results
            assert presales_handoff(pre.name)['label'] == 'Open with Presales'
            assert label == 'Open with Presales', label
        print('PASS survey completion, repeat save, results and status; presales=' + support, flush=True)
        frappe.db.rollback(save_point='completion_case')
finally:
    frappe.db.rollback()
    frappe.destroy()
