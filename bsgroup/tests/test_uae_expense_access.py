import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class ExpenseAccessTests(unittest.TestCase):
    def setUp(self):
        self.profile = Mock(return_value={'region': 'UAE'})
        self.setup = Mock()
        self.rule = Mock()
        self.user = Mock(roles=[types.SimpleNamespace(role='Employee')])
        self.f = types.ModuleType('frappe')
        self.f.db = types.SimpleNamespace(get_value=Mock(side_effect=lambda dt,*a,**k: 1 if dt == 'User' else None), exists=Mock(return_value=True))
        self.f.get_doc = Mock(side_effect=lambda dt,*a: self.rule if isinstance(dt,dict) or dt == 'Custom DocPerm' else self.user)
        self.f.clear_cache = Mock()
        self.p = patch.dict(sys.modules, {'frappe':self.f,
            'frappe.permissions':types.SimpleNamespace(setup_custom_perms=self.setup),
            'bsgroup.hr_email':types.SimpleNamespace(site_profile=self.profile)})
        self.p.start()
        spec = importlib.util.spec_from_file_location('expense_access_test', Path(__file__).resolve().parents[1]/'uae_expense_access.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self): self.p.stop()

    def test_only_select_added_to_dedicated_role_and_user(self):
        self.m.install()
        self.setup.assert_called_once_with('Account')
        self.assertEqual(self.rule.update.call_args.args[0], {**{k:0 for k in self.m.DENIED}, 'select':1})
        self.user.append.assert_called_once_with('roles', {'role':self.m.ROLE})
        self.assertEqual(self.f.get_doc.call_args.args, ('User',self.m.USER))

    def test_oman_and_unknown_sites_untouched(self):
        for value in ({'region':'Oman'}, None):
            self.profile.return_value = value
            self.m.install()
        self.setup.assert_not_called()
        self.f.get_doc.assert_not_called()

    def test_disabled_user_untouched(self):
        self.f.db.get_value.side_effect = None
        self.f.db.get_value.return_value = 0
        self.m.install()
        self.setup.assert_not_called()

    def test_existing_role_not_duplicated_and_permissions_not_broadened(self):
        self.user.roles.append(types.SimpleNamespace(role=self.m.ROLE))
        self.f.db.get_value.side_effect = lambda dt,*a,**k: 1 if dt == 'User' else 'RULE'
        self.m.install()
        self.user.append.assert_not_called()
        self.user.save.assert_not_called()
        self.assertEqual(self.rule.update.call_args.args[0]['read'], 0)

if __name__ == '__main__': unittest.main()
