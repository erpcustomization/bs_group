"""Regression checks against the restored bench; all writes roll back."""
from pathlib import Path
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
frappe.init(site='rel1-test.local', sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
try:
    from bsgroup.utils.quotation import set_sales_person_from_customer
    sheet = frappe.get_all('Deal Cost Sheet', filters={'opportunity':['is','set']}, fields=['name','opportunity'], limit=1)[0]
    frappe.db.set_value('Opportunity', sheet.opportunity, 'opportunity_owner', 'gopinath@bitssecureit.com')
    frappe.db.set_value('Deal Cost Sheet', sheet.name, 'deal_owner', 'paul@bitssecureit.com')
    q = frappe.new_doc('Quotation')
    q.owner = 'sanisha@bitssecureit.com'
    q.quotation_to = 'Lead'
    q.opportunity = sheet.opportunity
    q.custom_deal_cost_sheet = sheet.name
    q.custom_sales_person = 'Sanisha Thomas'
    set_sales_person_from_customer(q)
    assert q.custom_sales_person == 'Gopinath Sundaram'
    assert q.owner == 'sanisha@bitssecureit.com'
    q.quotation_to = 'Customer'
    q.custom_sales_person = 'Sanisha Thomas'
    set_sales_person_from_customer(q)
    assert q.custom_sales_person == 'Gopinath Sundaram'
    q.opportunity = None
    set_sales_person_from_customer(q)
    assert q.custom_sales_person == 'Gopinath Sundaram', 'exact linked DCS supplies opportunity'
    frappe.db.set_value('Opportunity', sheet.opportunity, 'opportunity_owner', None)
    set_sales_person_from_customer(q)
    assert q.custom_sales_person == 'Paul', 'DCS owner fallback'
    frappe.db.set_value('Deal Cost Sheet', sheet.name, 'deal_owner', 'Administrator')
    set_sales_person_from_customer(q)
    assert not q.custom_sales_person, 'unmapped owner must not use preparer'
    q.custom_deal_cost_sheet = None
    q.party_name = None
    q.custom_sales_person = 'Paul'
    set_sales_person_from_customer(q)
    assert q.custom_sales_person == 'Paul', 'unlinked legacy values preserved'
    print('PASS opportunity precedence, exact DCS linkage, Lead/Customer, owner fallback, missing mapping, preparer retained, legacy preservation')
finally:
    frappe.db.rollback()
    frappe.destroy()
