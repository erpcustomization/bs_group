import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Record(dict):
    __getattr__ = dict.get


class ProjectRequestsTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f._ = lambda text: text
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.throw = lambda text: (_ for _ in ()).throw(ValueError(text))
        self.f.has_permission = Mock(return_value=True)
        self.f.get_roles = Mock(return_value=['Employee'])
        self.f.get_list = Mock(return_value=[])
        self.f.db = Record(get_value=Mock(side_effect=lambda dt,name,field: 'AED' if field == 'default_currency' else 'CC-A'))
        self.f.get_meta = lambda dt: Record(has_field=lambda field: field in (
            {'workflow_state','status','currency','employee_name'} if dt=='Employee Advance' else {'workflow_state','task'}))
        helpers = types.ModuleType('bsgroup.project_expenses')
        self.project = Record(name='PROJECT-A',project_name='Project A',company='Company A',status='Open')
        helpers.project_doc = self.guard = Mock(return_value=self.project)
        helpers.own_employee = self.employee = Mock(return_value='EMP-A')
        self.patch = patch.dict(sys.modules,{'frappe':self.f,'bsgroup.project_expenses':helpers})
        self.patch.start()
        spec = importlib.util.spec_from_file_location('project_request_test',Path(__file__).resolve().parents[1]/'project_requests.py')
        self.m = importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)

    def tearDown(self):self.patch.stop()

    def test_unknown_request_type_rejected_before_data_access(self):
        with self.assertRaises(ValueError):self.m.context('PROJECT-A','User')
        self.guard.assert_not_called();self.f.get_list.assert_not_called()

    def test_project_permission_required_before_reading_requests(self):
        self.guard.side_effect = PermissionError()
        with self.assertRaises(PermissionError):self.m.context('PROJECT-A','advance')
        self.f.get_list.assert_not_called()

    def test_advance_prefills_own_employee_and_project_and_preserves_permissions(self):
        result = self.m.context('PROJECT-A','advance')
        self.assertEqual(result['defaults'],{'custom_project':'PROJECT-A','company':'Company A','employee':'EMP-A'})
        args = self.f.get_list.call_args.kwargs
        self.assertEqual(args['filters'],{'custom_project':'PROJECT-A','employee':'EMP-A'})
        self.assertNotIn('ignore_permissions',args)
        self.assertTrue(result['can_create'])

    def test_missing_employee_prevents_advance_but_not_labor(self):
        self.employee.return_value = None
        self.assertFalse(self.m.context('PROJECT-A','advance')['can_create'])
        self.assertTrue(self.m.context('PROJECT-A','labor')['can_create'])

    def test_labor_excludes_ticket_requests_and_keeps_task_selection(self):
        result = self.m.context('PROJECT-A','labor')
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'reference':'PROJECT-A','source':'Project'})
        self.assertEqual(result['defaults'],{'reference':'PROJECT-A','company':'Company A','source':'Project','cost_center':'CC-A'})
        self.assertNotIn('task',result['defaults'])
        self.assertNotIn('currency',self.f.get_list.call_args.kwargs['fields'])

    def test_no_read_permission_does_not_read_records(self):
        self.f.has_permission.side_effect = lambda dt,action:action=='create'
        result = self.m.context('PROJECT-A','advance')
        self.assertEqual(result['records'],[]);self.f.get_list.assert_not_called()

    def test_no_create_permission_hides_request_action(self):
        self.f.has_permission.side_effect = lambda dt,action:action=='read'
        result = self.m.context('PROJECT-A','labor')
        self.assertFalse(result['can_create']);self.assertIn('existing access',result['problem'])

    def test_cancelled_projects_cannot_create_requests(self):
        self.project['status']='Cancelled'
        for kind in ('advance','labor'):
            self.assertFalse(self.m.context('PROJECT-A',kind)['can_create'])

    def test_existing_approver_visibility_retains_native_permission_filtering(self):
        self.f.get_roles.return_value = ['Expense Approver']
        self.m.context('PROJECT-A','advance')
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'],{'custom_project':'PROJECT-A'})
        self.assertNotIn('ignore_permissions',self.f.get_list.call_args.kwargs)


if __name__=='__main__':unittest.main()
