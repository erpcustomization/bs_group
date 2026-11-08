import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Doc:
    def __init__(self, **fields):
        self.__dict__.update(fields)
        self.check_permission = Mock()
        self.save = Mock()
        self.add_comment = Mock()

    def get(self, key):
        return getattr(self, key, None)

    def update(self, values):
        self.__dict__.update(values)


class OrganizationEditorTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.parse_json = lambda value: json.loads(value) if isinstance(value, str) else value
        self.f.throw = lambda message: (_ for _ in ()).throw(ValueError(message))
        self.employee = Doc(name='staff', employee_name='Staff', first_name='Staff',
                            reports_to='manager', company='UAE', modified='version-1', status='Active')
        self.manager = Doc(name='manager', reports_to=None, status='Active')
        self.docs = {'staff': self.employee, 'manager': self.manager}
        self.f.get_doc = Mock(side_effect=lambda dt, name, **kw: self.docs[name])
        management = types.ModuleType('bsgroup.hr_management')
        self.guard = management._guard = Mock()
        self.patch = patch.dict(sys.modules, {'frappe': self.f, 'bsgroup.hr_management': management})
        self.patch.start()
        spec = importlib.util.spec_from_file_location('org_test', Path(__file__).resolve().parents[1] / 'hr_org.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        self.patch.stop()

    def test_guard_denies_before_read_or_write(self):
        self.guard.side_effect = PermissionError()
        with self.assertRaises(PermissionError): self.m.employee_details('staff')
        with self.assertRaises(PermissionError): self.m.save_employee('staff', {'first_name':'X'}, 'version-1')
        self.f.get_doc.assert_not_called()

    def test_document_permissions_checked_before_mutation(self):
        self.employee.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): self.m.save_employee('staff', {'first_name':'X'}, 'version-1')
        self.employee.save.assert_not_called()
        self.assertEqual(self.employee.first_name, 'Staff')

    def test_concurrent_edit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'updated by someone else'):
            self.m.save_employee('staff', {'first_name':'X'}, 'old-version')
        self.employee.save.assert_not_called()

    def test_privilege_and_employment_fields_not_accepted(self):
        for values in ({'user_id':'admin'}, {'status':'Left'}, {'company':'Other'}, {'roles':[]}, {'first_name':['X']}):
            with self.assertRaises(ValueError): self.m.save_employee('staff', values, 'version-1')
        self.employee.save.assert_not_called()

    def test_self_and_indirect_cycles_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'circular'):
            self.m.save_employee('staff', {'reports_to':'staff'}, 'version-1')
        self.docs['other'] = Doc(name='other', reports_to='staff', status='Active')
        with self.assertRaisesRegex(ValueError, 'circular'):
            self.m.save_employee('staff', {'reports_to':'other'}, 'version-1')
        self.employee.save.assert_not_called()

    def test_remove_line_only_detaches_manager_and_uses_native_save(self):
        self.m.save_employee('staff', {'reports_to':None}, 'version-1')
        self.assertIsNone(self.employee.reports_to)
        self.assertEqual(self.employee.status, 'Active')
        self.employee.save.assert_called_once_with()
        self.employee.add_comment.assert_called_once()

    def test_manager_access_and_native_validation_remain_enforced(self):
        self.docs['new'] = Doc(name='new', reports_to=None, status='Active')
        self.employee.save.side_effect = RuntimeError('native workflow validation')
        with self.assertRaisesRegex(RuntimeError, 'native workflow'):
            self.m.save_employee('staff', {'reports_to':'new'}, 'version-1')
        self.docs['new'].check_permission.assert_called_once_with('read')
        self.employee.add_comment.assert_not_called()

    def test_department_must_belong_to_employee_company(self):
        self.docs['team'] = Doc(company='Other')
        with self.assertRaisesRegex(ValueError, 'employee’s company'):
            self.m.save_employee('staff', {'department':'team'}, 'version-1')
        self.employee.save.assert_not_called()

    def test_detail_returns_only_editor_fields(self):
        self.employee.bank_account_no='private'
        result=self.m.employee_details('staff')
        self.assertNotIn('bank_account_no',result)
        self.assertEqual(result['modified'],'version-1')
        self.assertEqual([c.args[0] for c in self.employee.check_permission.call_args_list],['read','write'])


if __name__ == '__main__':
    unittest.main()
