"""Authorization and data-boundary tests for the administration overview."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

class Doc(dict):
    def __getattr__(self, key): return self.get(key)

class UserManagementTests(unittest.TestCase):
    def setUp(self):
        self.f=MagicMock()
        self.f.whitelist=lambda *a,**k:lambda fn:fn
        self.f._=lambda value:value
        self.f.PermissionError=PermissionError
        self.f.throw.side_effect=lambda message,*a:(_ for _ in ()).throw(PermissionError(message))
        sys.modules['frappe']=self.f
        spec=importlib.util.spec_from_file_location('user_management',Path(__file__).parents[1]/'bsgroup/user_management.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.f.has_permission.return_value=True

    def test_non_manager_is_rejected_before_data_lookup(self):
        self.f.only_for.side_effect=PermissionError
        with self.assertRaises(PermissionError):self.m.directory()
        with self.assertRaises(PermissionError):self.m.details('someone@example.com')
        self.f.get_list.assert_not_called();self.f.get_doc.assert_not_called()

    def test_missing_user_read_permission_is_rejected(self):
        self.f.has_permission.return_value=False
        with self.assertRaises(PermissionError):self.m.directory()
        self.f.get_list.assert_not_called()

    def test_directory_uses_permission_filtered_query_and_safe_fields(self):
        self.f.get_list.return_value=[{'name':str(i)} for i in range(101)]
        result=self.m.directory(search='Sivaram',state='active',kind='System User')
        self.assertEqual(len(result['rows']),100);self.assertTrue(result['has_more'])
        query=self.f.get_list.call_args.kwargs
        self.assertEqual(query['filters']['enabled'],1)
        self.assertNotIn('api_key',query['fields']);self.assertNotIn('password',query['fields'])
        self.f.get_all.assert_not_called();self.f.db.set_value.assert_not_called()

    def test_details_checks_target_and_never_returns_secrets_or_writes(self):
        doc=Doc(name='employee@example.com',first_name='Employee',full_name='Employee Name',enabled=1,
                user_type='System User',last_login=None,roles=[],api_key='SECRET',api_secret='SECRET',
                check_permission=MagicMock())
        self.f.get_doc.return_value=doc;self.f.get_roles.return_value=['Employee']
        self.f.get_list.return_value=[];self.f.db.exists.return_value=False
        result=self.m.details(doc.name)
        doc.check_permission.assert_called_once_with('read')
        self.assertNotIn('SECRET',str(result));self.assertEqual(result['first_name'],'Employee')
        self.f.db.set_value.assert_not_called();self.f.db.sql.assert_not_called()

    def test_install_only_reloads_page_and_clears_cache(self):
        self.m.install()
        self.f.reload_doc.assert_called_once_with('bs_group','page','bs_user_management',force=True)
        self.f.get_doc.assert_not_called();self.f.db.set_value.assert_not_called()

if __name__=='__main__':unittest.main()
