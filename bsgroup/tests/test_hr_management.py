import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class HRManagementTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda f: f
        self.f.PermissionError = PermissionError
        self.f.throw = lambda *args: (_ for _ in ()).throw(PermissionError())
        self.f.session = types.SimpleNamespace(user='muskan@bitssecureit.com')
        self.f.get_roles = lambda: ['HR User']
        self.f.db = types.SimpleNamespace(exists=lambda *args: True)
        self.f.has_permission = lambda *args, **kwargs: True
        self.f.get_meta = lambda *args: types.SimpleNamespace(has_field=lambda f: True)
        self.f.get_list = Mock(side_effect=lambda dt, **kw: [types.SimpleNamespace(total=3)] if any(isinstance(f, dict) and f.get('COUNT') for f in kw['fields']) else [])
        utils = types.ModuleType('frappe.utils')
        utils.nowdate = lambda: '2026-11-07'
        self.patch = patch.dict(sys.modules, {'frappe':self.f, 'frappe.utils':utils})
        self.patch.start()
        spec = importlib.util.spec_from_file_location('hr_management_test', Path(__file__).resolve().parents[1] / 'hr_management.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        self.patch.stop()

    def test_employee_and_guest_cannot_read_management_data(self):
        self.f.session.user = 'employee@example.com'
        self.f.get_roles = lambda: ['Employee']
        with self.assertRaises(PermissionError): self.m.overview()
        self.f.get_roles = lambda: ['System Manager']
        self.f.session.user = 'Guest'
        with self.assertRaises(PermissionError): self.m.overview()
        self.f.get_list.assert_not_called()

    def test_bs_hr_is_limited_to_muskan_and_system_administrators(self):
        self.assertTrue(self.m.can_manage())
        self.f.session.user = 'another-hr@example.com'
        self.f.get_roles = lambda: ['HR Manager']
        self.assertFalse(self.m.can_manage())
        self.f.get_roles = lambda: ['System Manager']
        self.assertTrue(self.m.can_manage())
        self.f.session.user = 'Administrator'
        self.f.get_roles = lambda: []
        self.assertTrue(self.m.can_manage())

    def test_access_setup_requires_system_manager_before_any_changes(self):
        self.f.only_for = Mock(side_effect=PermissionError())
        for action in (self.m.grant_muskan_access, self.m.muskan_access_review):
            with self.assertRaises(PermissionError): action()

    def test_denied_doctype_is_not_queried_or_counted(self):
        self.f.has_permission = lambda *args: False
        result = self.m.overview()
        self.assertTrue(all(not s['available'] and s['count'] is None for s in result['sections']))
        self.f.get_list.assert_not_called()

    def test_permission_filtered_lists_used_for_counts_and_rows(self):
        result = self.m.overview()
        self.assertEqual(len(result['sections']), 9)
        for call in self.f.get_list.call_args_list:
            self.assertNotIn('ignore_permissions', call.kwargs)
        checkin = [call for call in self.f.get_list.call_args_list if call.args[0] == 'Employee Checkin']
        self.assertEqual(checkin[0].kwargs['filters'], checkin[1].kwargs['filters'])
        self.assertEqual(checkin[0].kwargs['filters']['time'][1], ['2026-11-07 00:00:00','2026-11-07 23:59:59'])

    def test_setup_never_replaces_existing_records_or_permissions(self):
        self.f.only_for = Mock()
        self.f.reload_doc = Mock()
        self.m.setup_registers()
        self.f.only_for.assert_called_once_with('System Manager')
        self.f.reload_doc.assert_not_called()

    def test_new_registers_admin_only_and_audited(self):
        for slug in ('hr_warning', 'hr_service_request'):
            path = Path(__file__).resolve().parents[1] / 'bs_group' / 'doctype' / slug / (slug+'.json')
            doc = json.loads(path.read_text())
            self.assertEqual([p['role'] for p in doc['permissions']], ['System Manager'])
            self.assertEqual(doc['track_changes'], 1)
            self.assertFalse(doc['permissions'][0].get('share'))
            self.assertFalse(doc['permissions'][0].get('delete'))

    def test_organization_keeps_reporting_lines_and_masks_hidden_managers(self):
        class Row(dict):
            __getattr__ = dict.get
        self.f.get_list = Mock(return_value=[
            Row(name='manager', reports_to=None),
            Row(name='staff', reports_to='manager'),
            Row(name='restricted', reports_to='outside-permission-scope'),
        ])
        rows = self.m.organization()['employees']
        self.assertEqual(rows[1]['reports_to'], 'manager')
        self.assertIsNone(rows[2]['reports_to'])
        self.assertTrue(rows[2]['manager_outside_view'])
        args = self.f.get_list.call_args.kwargs
        self.assertEqual(args['filters'], {'status': 'Active'})
        self.assertEqual(args['limit_page_length'], 0)
        self.assertNotIn('ignore_permissions', args)

    def test_organization_denies_employee_access_before_reading(self):
        self.f.has_permission = lambda *args: False
        with self.assertRaises(PermissionError): self.m.organization()
        self.f.get_list.assert_not_called()


if __name__ == '__main__':
    unittest.main()
