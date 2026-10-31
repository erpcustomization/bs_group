"""Exercise the inherited Desk User create grant; rollback local configuration."""
from pathlib import Path
from unittest.mock import patch
import frappe
import bsgroup

bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
frappe.init(site='rel1-test.local', sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
try:
    from bsgroup import scoped_sales_access as access
    user = 'helpdesk@bitssecureit.com'
    doc = frappe.get_doc('User', user)
    doc.set('block_modules', [r for r in doc.block_modules if r.module != 'CRM'])
    with patch.object(frappe, 'enqueue'):
        doc.save()
    real_hooks = frappe.get_hooks
    def hooks(name=None, *args, **kwargs):
        result = real_hooks(name, *args, **kwargs)
        if name == 'has_permission':
            result = dict(result)
            result['Lead'] = ['bsgroup.scoped_sales_access.permission']
        return result
    with patch.object(frappe, 'get_hooks', side_effect=hooks):
        lead = frappe.get_doc({'doctype': 'Lead', 'owner': user})
        assert lead.has_permission('create', user=user), 'baseline create grant required'
        doc.append('block_modules', {'module': 'CRM'})
        with patch.object(frappe, 'enqueue'):
            doc.save()
        assert not lead.has_permission('create', user=user)
        assert not lead.has_permission('read', user=user)
        assert access.lead_query(user) == '1=0'
        assert lead.has_permission('create', user='Administrator')
        assert access.condition('Lead', 'Administrator') is None
        assert access.condition('HD Ticket', user) is None
    print('PASS: blocked Help Desk Lead creation/read/query, Admin and Helpdesk unaffected; rollback')
finally:
    frappe.db.rollback()
    frappe.clear_cache()
    frappe.destroy()
