"""Installer safety: no user mutation, no approval grants, repeatable migration."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Doc(dict):
    __getattr__=dict.get
    def save(self, **kw):
        self.db[self['name']]=self
        return self
    insert=save
    def append(self,key,row):self[key].append(Doc(row))
    def set(self,key,value):self[key]=value


class Tests(unittest.TestCase):
    def setUp(self):
        self.records={}
        self.f=types.ModuleType('frappe')
        self.f.clear_cache=Mock()
        self.f.get_roles=Mock(return_value=[])
        self.f.session=Doc(user='manager@example.com')
        def exists(dt,name):
            return dt!='Role' or name in self.records
        def value(dt,filters,field):
            return next((k for k,v in self.records.items() if v.get('doctype')==dt and all(v.get(a)==b for a,b in filters.items())),None)
        self.f.db=Doc(exists=exists,get_value=value)
        self.f.get_meta=lambda dt:Doc(is_submittable=dt in ('Timesheet','Tech Task Scheduler'))
        def get_doc(dt,name=None):
            if isinstance(dt,dict):
                doc=Doc(dt);doc['name']=doc.get('role_name') or 'new-'+str(len(self.records));doc.db=self.records;return doc
            if dt=='Report' and name not in self.records:
                doc=Doc(doctype=dt,name=name,roles=[Doc(role='Existing Role')]);doc.db=self.records;self.records[name]=doc
            return self.records[name]
        self.f.get_doc=Mock(side_effect=get_doc)
        self.modules=patch.dict(sys.modules,{'frappe':self.f,
            'frappe.custom.doctype.custom_field.custom_field':types.SimpleNamespace(create_custom_fields=Mock()),
            'frappe.permissions':types.SimpleNamespace(setup_custom_perms=Mock()),
            'bsgroup.hr_email':types.SimpleNamespace(site_profile=lambda:{'region':'Oman'})})
        self.modules.start()
        spec=importlib.util.spec_from_file_location('role_test',Path(__file__).parents[1]/'bsgroup/project_manager_access.py')
        self.role=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.role)

    def tearDown(self):self.modules.stop()

    def test_repeat_install_and_no_user_or_old_role_changes(self):
        self.role.install();before=repr(self.records);self.role.install()
        self.assertEqual(before,repr(self.records))
        self.assertFalse(any(v.get('doctype') in ('User','Has Role','DocShare') for v in self.records.values()))
        rules=[v for v in self.records.values() if v.get('doctype')=='Custom DocPerm']
        self.assertTrue(rules)
        self.assertTrue(all(v.role==self.role.ROLE for v in rules))
        for v in rules:
            self.assertFalse(v.get('delete') or v.get('cancel') or v.get('share'))
            if v.parent in self.role.LINKS:
                self.assertEqual(v.select,1);self.assertFalse(v.read or v.write)
            if v.parent in self.role.OWN_REQUESTS:
                self.assertEqual(v.if_owner,1);self.assertFalse(v.submit)
            if v.parent=='Labor Preapproval':self.assertFalse(v.submit)
        self.assertFalse(any(v.parent in ('Purchase Order','Payment Order','User') and v.write for v in rules))

    def test_only_explicit_role_enables(self):
        self.assertFalse(self.role.enabled())
        self.f.get_roles.return_value=[self.role.ROLE]
        self.assertTrue(self.role.enabled())

    def test_companion_grant_removed_but_preexisting_role_preserved(self):
        for existing in (False, True):
            doc=Doc(user_type='System User',roles=[Doc(role=self.role.ROLE)],
                    meta=Doc(has_field=lambda name:True))
            if existing:doc.roles.append(Doc(role='Projects User'))
            self.role.sync_user(doc)
            self.assertEqual(sum(r.role=='Projects User' for r in doc.roles),1)
            self.role.sync_user(doc)
            self.assertEqual(sum(r.role=='Projects User' for r in doc.roles),1)
            doc['roles']=[r for r in doc.roles if r.role!=self.role.ROLE]
            self.role.sync_user(doc)
            self.assertEqual(any(r.role=='Projects User' for r in doc.roles),existing)


if __name__=='__main__':unittest.main()
