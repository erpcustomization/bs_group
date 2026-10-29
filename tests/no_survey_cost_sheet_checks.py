"""Exercise draft creation and repeat clicks in a rolled-back local transaction."""
from pathlib import Path
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
frappe.init(site='rel1-test.local', sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
from bsgroup.opportunity_intake import create_supply_cost_sheet, create_no_survey_cost_sheet
try:
    rows = frappe.get_all('Opportunity', fields=['name'], limit_page_length=100)
    candidate = next((r.name for r in rows if not frappe.db.exists('Deal Cost Sheet', {'opportunity':r.name}) and not frappe.db.exists('Presales Request', {'opportunity':r.name})), None)
    assert candidate, 'Need a local Opportunity without a DCS'
    frappe.db.set_value('Opportunity', candidate, {'custom_business_type':'Supply', 'opportunity_amount':1000}, update_modified=False)
    first = create_supply_cost_sheet(candidate)
    assert first['created']
    sheet = frappe.get_doc('Deal Cost Sheet', first['name'])
    assert sheet.docstatus == 0 and sheet.opportunity == candidate
    second = create_supply_cost_sheet(candidate)
    assert not second['created'] and second['name'] == first['name']
    frappe.db.set_value('Opportunity', candidate, 'custom_business_type', 'Service', update_modified=False)
    try:
        create_supply_cost_sheet(candidate)
        raise AssertionError('Service accepted by Supply action')
    except frappe.ValidationError:
        pass
    frappe.db.set_value('Opportunity', candidate, 'custom_service_survey', 'No Site Survey Required', update_modified=False)
    doc = frappe.get_doc('Opportunity', candidate)
    doc.custom_enquiry = 'Direct costing test'
    doc.custom_presales_required = doc.custom_elv_site_survey_required = doc.custom_technical_site_survey_required = 0
    doc.custom_site_survey_request = None
    create_no_survey_cost_sheet(doc)
    assert frappe.db.count('Deal Cost Sheet', {'opportunity':candidate}) == 1
    for kind in ('Service', 'Supply', 'Supply and Installation'):
        frappe.db.delete('Deal Cost Sheet', {'opportunity':candidate})
        doc.custom_business_type = kind
        doc.custom_installation_type = '3CX' if kind == 'Supply and Installation' else None
        create_no_survey_cost_sheet(doc)
        create_no_survey_cost_sheet(doc)
        assert frappe.db.count('Deal Cost Sheet', {'opportunity':candidate, 'docstatus':0}) == 1
    frappe.db.delete('Deal Cost Sheet', {'opportunity':candidate})
    doc.custom_presales_required = 1
    create_no_survey_cost_sheet(doc)
    assert not frappe.db.exists('Deal Cost Sheet', {'opportunity':candidate})
    print('PASS Service, Supply and Installation draft creation, duplicate prevention and presales exclusion')
finally:
    frappe.db.rollback()
    frappe.destroy()

