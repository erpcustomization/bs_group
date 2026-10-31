"""Restored LOCAL bench only. Configuration, fixtures and transfers roll back."""
from pathlib import Path
from unittest.mock import patch
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
frappe.init(site='rel1-test.local', sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
try:
    from bsgroup import scoped_sales_access as access, lead_assignment as api
    from frappe.desk.form import assign_to
    from frappe import share
    with patch.object(frappe, 'enqueue'), patch.object(assign_to, 'notify_assignment'):
        access.configure_dubai()
        role = 'BS Lead Intake Manager'
        if not frappe.db.exists('Role',role):
            frappe.get_doc({'doctype':'Role','role_name':role,'desk_access':1}).insert()
        frappe.get_doc({'doctype':'Has Role','parent':'priya@bitssecureit.com','parenttype':'User',
            'parentfield':'roles','role':role}).db_insert()
        for user in ['priya@bitssecureit.com','paul@bitssecureit.com','gopinath@bitssecureit.com']:
            frappe.db.set_value('User',user,{'enabled':1,'user_type':'System User'})
            frappe.clear_cache(user=user)
        native_hooks = frappe.get_hooks
        def hooks(name=None,*args,**kwargs):
            result=native_hooks(name,*args,**kwargs)
            if name in ('has_permission','permission_query_conditions'):
                result=dict(result)
                result['Lead']=['bsgroup.scoped_sales_access.'+('permission' if name=='has_permission' else 'lead_query')]
            if name=='doc_events':
                result=dict(result)
                result['Lead']={'before_validate':['bsgroup.lead_lifecycle.before_validate'],
                    'on_update':['bsgroup.lead_lifecycle.sync_assignment']}
            return result
        with patch.object(frappe,'get_hooks',side_effect=hooks):
            def fixture():
                frappe.set_user('Administrator')
                d=frappe.get_doc({'doctype':'Lead','name':'ZZTEST-HANDOVER-'+frappe.generate_hash(length=7),
                    'first_name':'ZZTEST handover','lead_name':'ZZTEST handover','status':'Open',
                    'company':'Bits Secure IT Infrastructure LLC - AE','owner':'Administrator',
                    'lead_owner':'priya@bitssecureit.com'})
                d.db_insert()
                assign_to.add({'doctype':'Lead','name':d.name,'assign_to':['priya@bitssecureit.com']})
                share.add('Lead',d.name,'priya@bitssecureit.com',read=1,write=1)
                frappe.set_user('priya@bitssecureit.com')
                return frappe.get_doc('Lead',d.name)
            def denied(fn):
                try: fn()
                except (frappe.PermissionError,frappe.ValidationError): return
                raise AssertionError('Expected refusal')
            d=fixture()
            options={r['value'] for r in api.choices(d.name)}
            assert {'paul@bitssecureit.com','gopinath@bitssecureit.com'} <= options
            assert 'sanisha@bitssecureit.com' not in options
            denied(lambda:api.transfer(d.name,'sanisha@bitssecureit.com',str(d.modified)))
            denied(lambda:api.transfer(d.name,'paul@bitssecureit.com','stale'))
            assert frappe.db.get_value('Lead',d.name,'lead_owner')=='priya@bitssecureit.com'
            result=api.transfer(d.name,'paul@bitssecureit.com',str(d.modified))
            assert result['lead_owner']=='paul@bitssecureit.com' and not result['can_read']
            d.reload()
            assert d.owner=='Administrator' and d.status=='Open'
            assert d.has_permission('write',user='paul@bitssecureit.com')
            assert not d.has_permission('read',user='priya@bitssecureit.com')
            assert [r.owner for r in assign_to.get({'doctype':'Lead','name':d.name})]==['paul@bitssecureit.com']
            assert not frappe.db.exists('DocShare',{'share_doctype':'Lead','share_name':d.name,'user':'priya@bitssecureit.com'})
            assert frappe.db.exists('Comment',{'reference_doctype':'Lead','reference_name':d.name,'content':['like','Sales handover by%']})
            assert not frappe.get_list('Lead',filters={'name':d.name})
            frappe.set_user('paul@bitssecureit.com')
            assert frappe.get_list('Lead',filters={'name':d.name})
            denied(lambda:api.transfer(d.name,'gopinath@bitssecureit.com',str(d.modified)))
            frappe.set_user('priya@bitssecureit.com')
            denied(lambda:api.transfer(d.name,'gopinath@bitssecureit.com',str(d.modified)))
            second=fixture()
            rows=api.assign(doctype='Lead',name=second.name,assign_to=['gopinath@bitssecureit.com'])
            assert [r.owner for r in rows]==['gopinath@bitssecureit.com']
            assert frappe.get_doc('Lead',second.name).has_permission('write',user='gopinath@bitssecureit.com')
            third=fixture()
            denied(lambda:api.assign(doctype='Lead',name=third.name,assign_to=['gopinath@bitssecureit.com','paul@bitssecureit.com']))
            # A late failure must restore owner, assignment, share and audit together.
            with patch.object(assign_to,'_remove',side_effect=frappe.ValidationError('ZZTEST late failure')):
                denied(lambda:api.transfer(third.name,'paul@bitssecureit.com',str(third.modified)))
            assert frappe.db.get_value('Lead',third.name,'lead_owner')=='priya@bitssecureit.com'
            assert [r.owner for r in assign_to.get({'doctype':'Lead','name':third.name})]==['priya@bitssecureit.com']
            assert not frappe.db.exists('Comment',{'reference_doctype':'Lead','reference_name':third.name,'content':['like','Sales handover by%']})
            print('PASS transfer and native Assign To, sales-only choices, recipient read/write/list access, previous owner removed, original creator/status preserved, audit, stale/foreign/unauthorised/multiple-recipient denial, atomic rollback',flush=True)
finally:
    frappe.set_user('Administrator')
    frappe.db.rollback()
    frappe.clear_cache()
    frappe.destroy()
