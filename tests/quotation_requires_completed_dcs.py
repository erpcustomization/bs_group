"""Exercise quotation entry points against Frappe; roll back all writes."""
from pathlib import Path
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
frappe.init(site='rel1-test.local', sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
from bsgroup.dcs.quotation_control import validate_quotation
from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation, refuse_stale_quotation_source
from bsgroup.utils.quotation import make_quotation as from_opportunity

def refused(action):
    try:
        action()
    except frappe.ValidationError as exc:
        assert 'Deal Cost Sheet' in str(exc), str(exc)
    else:
        raise AssertionError('Expected costing gate to refuse')

try:
    for status in (0, 1):
        q = frappe.new_doc('Quotation')
        q.docstatus = status
        refused(lambda: validate_quotation(q))
    print('PASS orphan draft and submission refused', flush=True)
    refused(lambda: from_opportunity('unused'))
    print('PASS direct Opportunity mapping refused', flush=True)
    name = frappe.db.get_value('Deal Cost Sheet', {'docstatus': 0}, 'name')
    assert name
    refused(lambda: make_quotation(name))
    print('PASS draft DCS quotation endpoint refused', flush=True)
    for status, superseded in ((0, None), (2, None), (1, 'replacement')):
        refused(lambda: refuse_stale_quotation_source(frappe._dict(docstatus=status, custom_superseded_by=superseded)))
    refuse_stale_quotation_source(frappe._dict(docstatus=1, custom_superseded_by=None, custom_dcs_revision_no=0))
    print('PASS submitted current source accepted; other states refused', flush=True)
finally:
    frappe.db.rollback()
    frappe.destroy()
