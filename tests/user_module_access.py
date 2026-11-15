import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

class Doc(dict):
    def __getattr__(self,key):return self.get(key)

class ModuleAccessTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock();self.f.whitelist=lambda *a,**k:lambda f:f
        self.f.throw.side_effect=lambda msg,*a:(_ for _ in ()).throw(ValueError(msg))
        self.f.parse_json=json.loads
        sys.modules['frappe']=self.f
        spec=importlib.util.spec_from_file_location('module_access',Path(__file__).parents[1]/'bsgroup/user_module_access.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.doc=Doc(name='person@example.com',modified='v1',user_type='System User',roles=[Doc(role='Employee')],check_permission=MagicMock(),save=MagicMock(),add_comment=MagicMock())
        self.doc['set']=lambda k,v:self.doc.__setitem__(k,v)
        self.doc['append']=lambda k,v:self.doc[k].append(Doc(v))
        self.rules=[dict(parent='Employee',role='Employee',read=1,write=0),dict(parent='Task',role='Projects User',read=1,write=1,create=1),dict(parent='Project',role='Projects User',read=1,write=1),dict(parent='Expense Claim',role='Projects Manager',read=1,submit=1),dict(parent='Labor Preapproval',role='Projects Manager',read=1,write=1,submit=1)]
        self.context=dict(available={m:list(s['records']) for m,s in self.m.MODULES.items()},rules=self.rules,assigned={'Employee'},base={'Employee'},implicit=set(),state={},owned=set(),fixed_sales=True,approval_roles={'HR':{'Leave Approver','Expense Approver'},'Projects':{'Projects Manager'}})
        self.f.db.exists.return_value=True
        self.m.context_for=lambda doc:self.context

    def test_preview_is_read_only_and_preserves_inherited_roles(self):
        payload,public,_=self.m.plan(self.doc,{'Projects.edit':True})
        self.assertEqual(set(payload['roles']),{'Employee','Projects User'})
        self.assertTrue(public['has_changes']);self.assertTrue(public['impact'])
        self.doc.save.assert_not_called();self.f.db.set_value.assert_not_called()
        self.assertEqual(payload['state']['owned_roles'],['Projects User'])

    def test_empty_preview_is_not_a_change(self):
        self.assertFalse(self.m.plan(self.doc,{})[1]['has_changes'])

    def test_fixed_sales_and_procurement_approval_cannot_be_granted(self):
        for module in ('Sales','Procurement'):
            with self.assertRaisesRegex(ValueError,'Mohan'):self.m.plan(self.doc,{module+'.approve':True})

    def test_hr_management_gate_is_preserved(self):
        with self.assertRaisesRegex(ValueError,'Muskan'):self.m.plan(self.doc,{'HR.edit':True})

    def test_scoped_sales_cannot_expand_to_other_modules(self):
        self.context['assigned'].add('BS Scoped Sales');self.context['base'].add('BS Scoped Sales')
        with self.assertRaisesRegex(ValueError,'Sales-only'):self.m.plan(self.doc,{'Projects.edit':True})

    def test_profiles_are_protected(self):
        self.doc['role_profile_name']='Existing'
        with self.assertRaisesRegex(ValueError,'profile'):self.m.plan(self.doc,{'Projects.edit':True})

    def test_remove_only_console_owned_grant(self):
        self.context.update(assigned={'Employee','Projects User'},owned={'Projects User'},state={'grants':{'Projects.edit':['Projects User']},'owned_roles':['Projects User']})
        payload,_,_=self.m.plan(self.doc,{'Projects.edit':False})
        self.assertEqual(payload['roles'],['Employee']);self.assertEqual(payload['state']['owned_roles'],[])

    def test_existing_role_shared_with_a_new_grant_is_not_removed(self):
        self.context.update(assigned={'Employee','Projects User'},base={'Employee','Projects User'},state={'grants':{'Projects.edit':['Projects User']},'owned_roles':[]})
        payload,_,_=self.m.plan(self.doc,{'Projects.edit':False})
        self.assertIn('Projects User',payload['roles'])

    def test_approval_preview_includes_cross_module_rights(self):
        _,public,_=self.m.plan(self.doc,{'Projects.approve':True})
        self.assertTrue(any(r['record']=='Expense Claim' and 'Submit' in r['added'] for r in public['impact']))

    def test_submit_is_not_treated_as_approval(self):
        self.context['assigned']={'Submitter'};self.context['base']={'Submitter'}
        self.rules.append(dict(parent='Task',role='Submitter',submit=1))
        projects=next(r for r in self.m.summarize(self.doc,self.context) if r['module']=='Projects')
        self.assertEqual(projects['cells']['approve']['status'],'Not granted')

    def test_unknown_inputs_are_rejected(self):
        for change in ({'Admin.edit':True},{'Sales.delete':True},{'Projects.edit':'true'}):
            with self.assertRaises(ValueError):self.m.plan(self.doc,change)

    def test_preview_token_changes_when_permission_rules_change(self):
        first=self.m.plan(self.doc,{'Projects.edit':True})[1]['token']
        self.rules[1]['export']=1
        self.assertNotEqual(first,self.m.plan(self.doc,{'Projects.edit':True})[1]['token'])

    def test_save_requires_current_preview_and_does_not_write_on_mismatch(self):
        self.m.load_target=lambda *a:self.doc
        with self.assertRaisesRegex(ValueError,'preview'):self.m.save(self.doc.name,'v1',{'Projects.edit':True},'bad')
        self.doc.save.assert_not_called()

    def test_save_uses_native_user_validation_and_tracks_only_new_roles(self):
        self.m.load_target=lambda *a:self.doc;self.m.ensure_viewers=MagicMock()
        changes={'Projects.edit':True};token=self.m.plan(self.doc,changes)[1]['token']
        self.m.save(self.doc.name,'v1',changes,token)
        self.doc.save.assert_called_once_with()
        self.assertEqual({r['role'] for r in self.doc.roles},{'Employee','Projects User'})
        self.assertEqual(json.loads(self.doc[self.m.FIELD])['owned_roles'],['Projects User'])

    def test_load_target_requires_manager_write_and_fresh_version(self):
        manager=MagicMock();sys.modules['bsgroup.user_management']=manager
        self.f.get_doc.return_value=self.doc
        self.m.load_target(self.doc.name,'v1');self.doc.check_permission.assert_called_with('write')
        with self.assertRaisesRegex(ValueError,'changed'):self.m.load_target(self.doc.name,'old')
        manager.require_manager.side_effect=PermissionError
        with self.assertRaises(PermissionError):self.m.load_target(self.doc.name,'v1')

if __name__=='__main__':unittest.main()
