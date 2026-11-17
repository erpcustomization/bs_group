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
        self.manager=MagicMock();self.manager.delegated.return_value=False
        self.manager.PROTECTED_ROLES={'System Manager','BS User Administrator'}
        self.manager.save_target.side_effect=lambda doc:doc.save()
        self.manager.check_target.side_effect=lambda doc:doc.check_permission('write')
        sys.modules['bsgroup.user_management']=self.manager
        sys.modules['frappe']=self.f
        spec=importlib.util.spec_from_file_location('bsgroup.project_support_access',Path(__file__).parents[1]/'bsgroup/project_support_access.py')
        support=importlib.util.module_from_spec(spec);spec.loader.exec_module(support)
        sys.modules['bsgroup.project_support_access']=support
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
        self.assertEqual(set(payload['roles']),{'Employee','Projects User','BS Project Support Viewer'})
        self.assertTrue(public['has_changes']);self.assertTrue(public['impact'])
        self.doc.save.assert_not_called();self.f.db.set_value.assert_not_called()
        self.assertEqual(payload['state']['owned_roles'],['BS Project Support Viewer','Projects User'])

    def test_empty_preview_is_not_a_change(self):
        self.assertFalse(self.m.plan(self.doc,{})[1]['has_changes'])

    def test_fixed_sales_and_procurement_approval_cannot_be_granted(self):
        for module in ('Sales','Procurement'):
            with self.assertRaisesRegex(ValueError,'Mohan'):self.m.plan(self.doc,{module+'.approve':True})

    def test_hr_management_gate_is_preserved(self):
        with self.assertRaisesRegex(ValueError,'Muskan'):self.m.plan(self.doc,{'HR.edit':True})

    def test_scoped_sales_can_add_other_module_without_removing_scope(self):
        self.context['assigned'].add('BS Scoped Sales');self.context['base'].add('BS Scoped Sales')
        payload,_,_=self.m.plan(self.doc,{'Projects.edit':True})
        self.assertIn('BS Scoped Sales',payload['roles'])
        self.assertIn('Projects User',payload['roles'])

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
        self.assertEqual({r['role'] for r in self.doc.roles},{'Employee','Projects User','BS Project Support Viewer'})
        self.assertEqual(json.loads(self.doc[self.m.FIELD])['owned_roles'],['BS Project Support Viewer','Projects User'])

    def test_load_target_requires_manager_write_and_fresh_version(self):
        manager=self.manager
        self.f.get_doc.return_value=self.doc
        self.m.load_target(self.doc.name,'v1');self.doc.check_permission.assert_called_with('write')
        with self.assertRaisesRegex(ValueError,'changed'):self.m.load_target(self.doc.name,'old')
        manager.require_manager.side_effect=PermissionError
        with self.assertRaises(PermissionError):self.m.load_target(self.doc.name,'v1')

    def test_delegate_rejects_module_role_with_user_admin_rights(self):
        self.manager.delegated.return_value=True
        self.rules.append(dict(parent='User',role='Projects User',write=1))
        with self.assertRaisesRegex(ValueError,'administration'):self.m.plan(self.doc,{'Projects.edit':True})

    def test_navigation_uses_only_recorded_grants_with_live_roles(self):
        self.f.get_roles.return_value=['Employee','Projects User']
        self.f.db.get_value.return_value=json.dumps({'grants':{'Projects.edit':['Projects User'],'Procurement.edit':['Purchase User']}})
        self.assertIn('Project',self.m.granted_screens('person@example.com'))
        self.assertNotIn('Purchase Order',self.m.granted_screens('person@example.com'))

    def test_delegate_can_preview_project_manager_with_full_scope_and_companions(self):
        self.manager.delegated.return_value=True
        self.rules.extend([dict(parent='Project',role='BS Projects Manager',read=1,write=1,create=1),
                           dict(parent='User',role='BS Projects Manager',select=1)])
        payload,public,_=self.m.plan(self.doc,{'Projects.manager':True})
        self.assertEqual(set(payload['roles']),{'Employee'}|self.m.PROJECT_MANAGER_ROLES)
        self.assertEqual(set(payload['state']['owned_roles']),self.m.PROJECT_MANAGER_ROLES)
        self.assertIn('all projects and AMCs',public['note'])
        self.assertIn('assignment-only',public['note'])
        self.assertEqual(public['changes'][0]['permission'],self.m.PROJECT_MANAGER_LABEL)
        self.doc.save.assert_not_called()
        self.assertNotIn('Projects Manager',payload['roles'])
        self.assertNotIn('System Manager',payload['roles'])

    def test_delegate_manager_save_matches_actual_user_hooks(self):
        self.manager.delegated.return_value=True
        self.m.load_target=lambda *a:self.doc;self.m.ensure_viewers=MagicMock()
        self.doc['meta']=Doc(has_field=lambda name:True)
        def save_with_hooks(doc):
            for name in ('project_manager_access','project_support_access'):
                spec=importlib.util.spec_from_file_location(name,Path(__file__).parents[1]/('bsgroup/'+name+'.py'))
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                module.sync_user(doc)
            doc.save()
        self.doc['enabled']=1
        self.manager.save_target.side_effect=save_with_hooks
        change={'Projects.manager':True}
        self.m.save(self.doc.name,'v1',change,self.m.plan(self.doc,change)[1]['token'])
        self.assertEqual({r.role for r in self.doc.roles},{'Employee'}|self.m.PROJECT_MANAGER_ROLES)
        self.doc.save.assert_called_once()
        state=json.loads(self.doc[self.m.FIELD])
        self.context.update(assigned={'Employee'}|self.m.PROJECT_MANAGER_ROLES,state=state,owned=self.m.PROJECT_MANAGER_ROLES)
        self.assertFalse(self.m.plan(self.doc,change)[1]['has_changes'])
        change={'Projects.manager':False}
        self.m.save(self.doc.name,'v1',change,self.m.plan(self.doc,change)[1]['token'])
        self.assertEqual({r.role for r in self.doc.roles},{'Employee'})

    def test_manager_removal_retains_existing_and_shared_roles(self):
        roles=self.m.PROJECT_MANAGER_ROLES
        self.context.update(assigned={'Employee'}|roles,base={'Employee','Projects User'},
            state={'grants':{'Projects.manager':sorted(roles),'Projects.view':['BS Console Projects View']},
                   'owned_roles':sorted(roles-{'Projects User'})})
        self.context['assigned'].add('BS Console Projects View')
        after=self.m.plan(self.doc,{'Projects.manager':False})[0]
        self.assertEqual(set(after['roles']),{'Employee','Projects User','BS Console Projects View','BS Project Support Viewer'})

    def test_preexisting_manager_is_protected(self):
        self.context['assigned'].add('BS Projects Manager');self.context['base'].add('BS Projects Manager')
        row=next(r for r in self.m.summarize(self.doc,self.context) if r['module']=='Projects')
        self.assertTrue(row['cells']['manager']['checked'])
        self.assertFalse(row['cells']['manager']['editable'])
        self.assertIn('BS Projects Manager',self.m.plan(self.doc,{'Projects.manager':False})[0]['roles'])

    def test_manager_requires_complete_roles_and_fresh_preview(self):
        self.f.db.exists.side_effect=lambda dt,filters: not (dt=='Role' and isinstance(filters,dict) and filters.get('name')=='BS Projects Manager')
        with self.assertRaisesRegex(ValueError,'incomplete'):self.m.plan(self.doc,{'Projects.manager':True})
        self.f.db.exists.side_effect=None
        self.m.load_target=lambda *a:self.doc
        token=self.m.plan(self.doc,{'Projects.manager':True})[1]['token']
        self.rules.append(dict(parent='Project',role='BS Projects Manager',delete=1))
        with self.assertRaisesRegex(ValueError,'preview'):self.m.save(self.doc.name,'v1',{'Projects.manager':True},token)
        self.doc.save.assert_not_called()

    def test_delegate_rejects_tampered_manager_admin_permissions(self):
        self.manager.delegated.return_value=True
        self.rules.append(dict(parent='User',role='BS Projects Manager',write=1))
        with self.assertRaisesRegex(ValueError,'administration'):self.m.plan(self.doc,{'Projects.manager':True})

    def test_manager_option_not_accepted_on_other_modules_or_profiles(self):
        with self.assertRaises(ValueError):self.m.plan(self.doc,{'Sales.manager':True})
        self.doc['role_profile_name']='Protected profile'
        with self.assertRaisesRegex(ValueError,'profile'):self.m.plan(self.doc,{'Projects.manager':True})

    def test_manager_keeps_sales_scope_and_other_permissions(self):
        self.context['assigned'].update({'BS Scoped Sales','Purchase User'})
        self.context['base'].update({'BS Scoped Sales','Purchase User'})
        after=self.m.plan(self.doc,{'Projects.manager':True})[0]
        self.assertTrue({'Employee','BS Scoped Sales','Purchase User'}<=set(after['roles']))
        self.assertEqual(set(after['roles'])-self.context['assigned'],self.m.PROJECT_MANAGER_ROLES)

    def test_disabled_account_cannot_receive_new_manager_grant(self):
        self.doc['enabled']=0
        with self.assertRaisesRegex(ValueError,'Enable'):self.m.plan(self.doc,{'Projects.manager':True})

if __name__=='__main__':unittest.main()
