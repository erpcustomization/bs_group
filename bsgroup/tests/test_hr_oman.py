import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class OmanHRTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kwargs: lambda fn: fn
        self.f.conf = {'host_name': 'https://erp-om.bitssecureit.com'}
        self.f.local = types.SimpleNamespace(site='test', response={})
        self.management = types.ModuleType('bsgroup.hr_management')
        self.management.can_manage = Mock(return_value=True)
        self.modules = patch.dict(sys.modules, {'frappe': self.f, 'bsgroup.hr_management': self.management})
        self.modules.start()
        spec = importlib.util.spec_from_file_location('oman_test', Path(__file__).resolve().parents[1] / 'hr_oman.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        self.modules.stop()

    def test_site_detection_is_exact_and_accepts_cloud_site(self):
        self.assertTrue(self.m.is_oman())
        self.f.conf = {'host_name': 'https://erp-om.bitssecureit.com.invalid'}
        self.assertFalse(self.m.is_oman())
        self.f.local.site = 'erp-om.k.frappe.cloud'
        self.assertTrue(self.m.is_oman())

    def test_hooks_preserve_existing_mail_permissions_and_leave_validation(self):
        hooks = dict(app_include_js=['existing.js'], boot_session='sales.boot',
            doc_events={'Leave Allocation': {'validate': 'native.validate'}, 'Notification': {'validate': 'mail.validate'}})
        self.m.configure_hooks(hooks)
        self.m.configure_hooks(hooks)
        self.assertEqual(len(hooks['app_include_js']), 2)
        self.assertEqual(hooks['boot_session'], ['sales.boot', 'bsgroup.hr_oman.boot_session'])
        self.assertEqual(hooks['doc_events']['Notification']['validate'], 'mail.validate')
        self.assertEqual(hooks['doc_events']['Leave Allocation']['validate'],
            ['native.validate', 'bsgroup.hr_annual_allocation.validate_allocation'])

    def test_asset_bundle_respects_site_and_existing_audience(self):
        self.f.get_app_path = Mock(return_value='source.js')
        with patch.object(self.m.Path, 'read_text', return_value='/* existing HR UI */') as read:
            self.m.navigation_script()
            self.assertEqual(read.call_count, 5)
            self.assertEqual(self.f.local.response['content_type'], 'application/javascript')
            self.management.can_manage.return_value = False
            self.m.navigation_script()
            self.assertEqual(self.f.local.response['filecontent'], '')
            self.management.can_manage.return_value = True
            self.f.conf = {'host_name': 'https://erp.bitssecureit.com'}
            self.m.navigation_script()
            self.assertEqual(self.f.local.response['filecontent'], '')

    def test_boot_only_marks_authorized_oman_sessions(self):
        info = types.SimpleNamespace()
        self.m.boot_session(info)
        self.assertTrue(info.bs_hr_management)
        self.management.can_manage.return_value = False
        self.m.boot_session(info)
        self.assertFalse(info.bs_hr_management)


if __name__ == '__main__':
    unittest.main()
