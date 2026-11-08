import copy
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Record(dict):
    def __getattr__(self,key):return self.get(key)
    def as_dict(self):return dict(self)


class Sidebar:
    def __init__(self):
        self.items=[Record(type='Section Break',label='BS Project',roles='existing-role-filter',keep_closed=0),
                    Record(type='Link',label='Project',link_type='DocType',link_to='Project',child=1),
                    Record(type='Section Break',label='BS HR')]
        self.save=Mock()
    def append(self,field,values):self.items.append(Record(values));return self.items[-1]


class ProjectModuleTests(unittest.TestCase):
    def setUp(self):
        self.f=types.ModuleType('frappe');self.f._=lambda s:s;self.f.whitelist=lambda **kw:lambda fn:fn
        self.f.throw=lambda text,exc=ValueError:(_ for _ in ()).throw(exc(text))
        self.f.PermissionError=PermissionError;self.f.only_for=Mock()
        self.f.has_permission=Mock(return_value=True);self.f.get_list=Mock(return_value=[])
        self.fields={};self.page_exists=False;self.sidebar=Sidebar()
        self.f.flags=types.SimpleNamespace(in_migrate=False)
        self.f.get_doc=Mock(return_value=self.sidebar)
        self.f.db=Record(exists=lambda dt,name:self.page_exists if dt=='Page' else True)
        self.f.get_meta=lambda dt:Record(get_field=lambda name:self.fields.get(name),has_field=lambda name:name in self.fields or dt!='Project')
        self.f.clear_cache=Mock();self.f.reload_doc=Mock(side_effect=self.reload)
        custom=types.ModuleType('frappe.custom.doctype.custom_field.custom_field')
        custom.create_custom_fields=self.create_fields=Mock(side_effect=self.add_fields)
        self.p=patch.dict(sys.modules,{'frappe':self.f,'frappe.custom.doctype.custom_field.custom_field':custom});self.p.start()
        spec=importlib.util.spec_from_file_location('pm_test',Path(__file__).resolve().parents[1]/'project_modules.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)

    def reload(self,*a,**kw):self.page_exists=True
    def add_fields(self,values,**kw):self.fields.update({row['fieldname']:Record(row) for row in values['Project']})
    def tearDown(self):self.p.stop()

    def test_installer_preserves_existing_sidebar_and_is_idempotent(self):
        before=copy.deepcopy(self.sidebar.items)
        self.m.install()
        self.assertEqual(self.sidebar.items[:len(before)],before)
        self.assertEqual(len(self.fields),4)
        for row in self.fields.values():self.assertEqual(row.fieldtype,'Check')
        added=[row for row in self.sidebar.items[len(before):] if row.type=='Section Break']
        self.assertEqual(len(added),4)
        self.assertTrue(all(row.roles=='existing-role-filter' for row in added))
        after=copy.deepcopy(self.sidebar.items)
        self.m.install()
        self.assertEqual(self.sidebar.items,after)
        self.sidebar.save.assert_called_once()
        self.create_fields.assert_called_once()

    def test_other_site_without_sidebar_is_unchanged(self):
        self.f.db['exists']=lambda *args:False
        self.assertFalse(self.m.install()['installed'])
        self.create_fields.assert_not_called();self.f.get_doc.assert_not_called()

    def test_setup_requires_system_manager(self):
        self.f.only_for.side_effect=PermissionError()
        with self.assertRaises(PermissionError):self.m.setup()
        self.create_fields.assert_not_called()

    def test_existing_field_conflict_is_not_overwritten(self):
        self.fields['custom_bs_supply_projects']=Record(fieldtype='Data')
        with self.assertRaisesRegex(ValueError,'incompatible'):self.m.install()
        self.create_fields.assert_not_called();self.sidebar.save.assert_not_called()

    def test_project_permission_precedes_any_records(self):
        self.f.has_permission.return_value=False
        with self.assertRaises(PermissionError):self.m.overview('elv')
        self.f.get_list.assert_not_called()

    def test_module_and_section_allowlists(self):
        with self.assertRaises(ValueError):self.m.overview('User')
        with self.assertRaises(ValueError):self.m.overview('elv','users')
        self.f.get_list.assert_not_called()

    def test_membership_is_independent_and_uses_native_permissions(self):
        self.m.install()
        shared=Record(name='P1',project_name='Shared',status='Open')
        self.f.get_list.return_value=[shared]
        self.assertEqual(self.m.overview('elv')['projects'],[shared])
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'custom_bs_elv_projects':1})
        self.assertEqual(self.m.overview('infra')['projects'],[shared])
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'custom_bs_infra_projects':1})
        self.assertNotIn('ignore_permissions',self.f.get_list.call_args.kwargs)

    def test_related_records_limited_to_visible_module_projects(self):
        self.m.install()
        projects=[Record(name='P1')]
        self.m.records('tasks',projects)
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'project':['in',['P1']]})
        self.m.records('labor',projects)
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'source':'Project','reference':['in',['P1']]})
        self.m.records('timesheets',projects)
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],[['Timesheet Detail','project','in',['P1']]])
        self.assertTrue(self.f.get_list.call_args.kwargs['distinct'])

    def test_no_access_or_no_projects_never_queries_unfiltered_records(self):
        self.m.records('expenses',[])
        self.f.get_list.assert_not_called()
        self.f.has_permission.return_value=False
        self.assertFalse(self.m.records('advances',[Record(name='P1')])['available'])
        self.f.get_list.assert_not_called()


if __name__=='__main__':unittest.main()
