import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Record(dict):
    __getattr__ = dict.get


class ProjectWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f._ = lambda value: value
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.throw = lambda text: (_ for _ in ()).throw(ValueError(text))
        self.project = Record(name='P-A', project_name='Project A', company='Company A', status='Open', check_permission=Mock())
        self.f.get_doc = Mock(return_value=self.project)
        self.f.db = Record(exists=Mock(return_value=True), get_value=Mock(return_value='CC-A'))
        self.f.get_meta = Mock(return_value=Record(has_field=lambda name: True))
        self.f.has_permission = Mock(return_value=True)
        self.f.get_list = Mock(return_value=[Record(name='A-1')])
        self.f.get_all = Mock(return_value=[Record(name='EMP-A')])
        self.f.get_attr = Mock(side_effect=ModuleNotFoundError('not deployed on site'))
        self.f.session = Record(user='employee@example.com')
        self.p = patch.dict(sys.modules, {'frappe': self.f}); self.p.start()
        spec = importlib.util.spec_from_file_location('workspace_test', Path(__file__).resolve().parents[1] / 'project_workspace.py')
        self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        self.m.find_spec = Mock(return_value=None)

    def tearDown(self): self.p.stop()

    def test_project_read_permission_precedes_child_access(self):
        self.project.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): self.m.context('P-A')
        self.f.get_list.assert_not_called(); self.f.get_all.assert_not_called()

    def test_invalid_or_missing_context_never_queries_records(self):
        for args in [('', 'tasks'), ('P-A', 'users')]:
            with self.assertRaises(ValueError): self.m.context(*args)
        self.f.get_doc.assert_not_called(); self.f.get_list.assert_not_called()

    def test_each_activity_filters_one_project(self):
        expected = {
            'tasks': {'project':'P-A'}, 'expenses': {'project':'P-A'},
            'advances': {'custom_project':'P-A'}, 'labor': {'reference':'P-A','source':'Project'},
            'timesheets': [['Timesheet Detail','project','=','P-A']],
            'scheduler': [['Tech Task Scheduler List','project','=','P-A']],
        }
        for section, filters in expected.items():
            with self.subTest(section=section):
                self.m.context('P-A', section)
                self.assertEqual(self.f.get_list.call_args.kwargs['filters'], filters)
                self.assertNotIn('ignore_permissions', self.f.get_list.call_args.kwargs)
                self.assertTrue(self.f.get_list.call_args.kwargs['distinct'])

    def test_changing_project_changes_filters_and_creation_defaults(self):
        a=self.m.context('P-A','tasks')
        self.project.update(name='P-B',project_name='Project B',company='Company B')
        b=self.m.context('P-B','tasks')
        self.assertEqual(a['defaults']['project'],'P-A')
        self.assertEqual(b['defaults'],{'project':'P-B','company':'Company B'})
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'project':'P-B'})

    def test_child_creation_keeps_project_and_scheduler_category(self):
        self.assertEqual(self.m.context('P-A','timesheets')['child'],dict(field='time_logs',values={
            'project':'P-A','custom_reference_type':'Project','custom_reference':'P-A'}))
        values=self.m.context('P-A','scheduler')['child']['values']
        self.assertEqual(values,dict(project='P-A',category='Project',category_doctype='Project',category_name='P-A'))

    def test_existing_expense_controls_and_owner_filter_are_reused(self):
        self.m.find_spec.return_value = object()
        handler=Mock(return_value=dict(can_create=False,problem='No independent manager',employee='EMP-A',expense_approver=None,claims=[Record(name='OWN-CLAIM')]))
        self.f.get_attr=Mock(return_value=handler)
        result=self.m.context('P-A','expenses')
        handler.assert_called_once_with('P-A')
        self.assertFalse(result['can_create']); self.assertEqual(result['rows'],[{'name':'OWN-CLAIM'}])
        self.f.get_list.assert_not_called()

    def test_existing_request_permission_error_is_not_bypassed(self):
        self.m.find_spec.return_value = object()
        self.f.get_attr=Mock(return_value=Mock(side_effect=PermissionError()))
        with self.assertRaises(PermissionError):self.m.context('P-A','advances')
        self.f.get_list.assert_not_called()

    def test_broken_installed_control_is_not_silently_bypassed(self):
        self.m.find_spec.return_value = object()
        self.f.get_attr.side_effect = ImportError('broken installed control')
        with self.assertRaises(ImportError): self.m.context('P-A','expenses')
        self.f.get_list.assert_not_called()

    def test_install_removes_only_generic_project_links_and_is_idempotent(self):
        fields={}
        self.f.get_meta.return_value=Record(fields=[Record(fieldname='last_field')],get_field=lambda name:fields.get(name))
        custom=types.ModuleType('frappe.custom.doctype.custom_field.custom_field')
        def create(definitions, **kw):
            fields.update({row['fieldname']:Record(row) for row in definitions['Project']})
        custom.create_custom_fields=Mock(side_effect=create)
        sidebar=Record(items=[
            Record(type='Section Break',label='BS Project'),
            Record(type='Link',link_type='DocType',link_to='Project'),
            Record(type='Link',link_type='DocType',link_to='Task'),
            Record(type='Section Break',label='BS Approvals'),
            Record(type='Link',link_type='DocType',link_to='Employee Advance'),
            Record(type='Section Break',label='BS Infra Projects'),
            Record(type='Link',link_to='bs-project-modules',route_options='{"bs_section":"tasks"}'),
            Record(type='Link',link_to='bs-project-modules',route_options='{"bs_section":"projects"}'),
            Record(type='Link',link_to='custom-page')])
        # Frappe documents expose .items as a child list, unlike dict.items.
        sidebar=types.SimpleNamespace(items=sidebar['items'],save=Mock())
        sidebar.set=lambda field,value:setattr(sidebar,field,value)
        self.f.get_doc.return_value=sidebar
        self.f.flags=Record(in_migrate=False);self.f.clear_cache=Mock()
        with patch.dict(sys.modules,{'frappe.custom.doctype.custom_field.custom_field':custom}):
            self.m.install();self.m.install()
        self.assertEqual(len(fields),2)
        self.assertEqual(len(sidebar.items),7)
        self.assertTrue(any(row.link_to=='Employee Advance' for row in sidebar.items))
        self.assertTrue(any(row.link_to=='custom-page' for row in sidebar.items))
        sidebar.save.assert_called_once();custom.create_custom_fields.assert_called_once()

    def test_no_activity_permission_never_lists_records(self):
        self.f.has_permission.return_value=False
        result=self.m.context('P-A','tasks')
        self.assertFalse(result['available']);self.assertFalse(result['can_create'])
        self.f.get_list.assert_not_called()

    def test_cancelled_project_or_missing_employee_blocks_creation(self):
        self.project['status']='Cancelled'
        self.assertFalse(self.m.context('P-A','tasks')['can_create'])
        self.project['status']='Open';self.f.get_all.return_value=[]
        self.assertFalse(self.m.context('P-A','advances')['can_create'])

    def test_missing_project_link_fails_closed(self):
        self.f.get_meta.return_value=Record(has_field=lambda name:False)
        result=self.m.context('P-A','advances')
        self.assertFalse(result['available']);self.assertFalse(result['can_create'])
        self.f.get_list.assert_not_called()


if __name__ == '__main__': unittest.main()
