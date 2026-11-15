import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.db = types.SimpleNamespace(get_value=Mock(return_value=1))
        self.f.get_all = Mock(return_value=['PROJ-1', 'PROJ-2'])
        self.f.clear_cache = Mock()
        self.profile = Mock(return_value={'region': 'UAE'})
        self.add = Mock()
        self.p = patch.dict(sys.modules, {
            'frappe': self.f,
            'frappe.share': types.SimpleNamespace(add_docshare=self.add),
            'bsgroup.hr_email': types.SimpleNamespace(site_profile=self.profile),
        })
        self.p.start()
        spec = importlib.util.spec_from_file_location('uae_access_test', Path(__file__).resolve().parents[1] / 'uae_project_access.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        self.p.stop()

    def test_oman_and_unknown_sites_untouched(self):
        for profile in ({'region': 'Oman'}, None):
            self.profile.return_value = profile
            self.m.install()
        self.f.get_all.assert_not_called()
        self.add.assert_not_called()

    def test_disabled_account_not_granted(self):
        self.f.db.get_value.return_value = 0
        self.m.install()
        self.add.assert_not_called()

    def test_all_uae_projects_only_no_hr_or_role_changes(self):
        self.f.db.get_value.side_effect = lambda dt, *a, **kw: 1 if dt == 'User' else None
        self.m.install()
        self.f.get_all.assert_called_once_with('Project', filters={'company': self.m.COMPANY}, pluck='name')
        self.assertEqual(self.add.call_count, 2)
        for call in self.add.call_args_list:
            self.assertEqual(call.args[0], 'Project')
            self.assertEqual(call.kwargs['user'], 'mithun@bitssecureit.com')
            self.assertEqual(call.kwargs['read'], 1)
            self.assertEqual(call.kwargs['write'], 1)
            self.assertEqual(call.kwargs['notify'], 0)

    def test_existing_access_is_idempotent(self):
        self.f.db.get_value.return_value = types.SimpleNamespace(read=1, write=1)
        self.m.grant('PROJ-1')
        self.add.assert_not_called()

    def test_new_project_hook_is_company_scoped(self):
        self.m.grant = Mock()
        self.m.project_updated(types.SimpleNamespace(name='PROJ-OM', company='Oman'))
        self.m.grant.assert_not_called()
        self.m.project_updated(types.SimpleNamespace(name='PROJ-AE', company=self.m.COMPANY))
        self.m.grant.assert_called_once_with('PROJ-AE')


if __name__ == '__main__':
    unittest.main()
