import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


class BalanceTests(unittest.TestCase):
    def setUp(self):
        self.fake = types.ModuleType('frappe')
        self.fake.whitelist = lambda **kw: lambda f: f
        self.fake.session = types.SimpleNamespace(user='own@example.com')
        self.fake.PermissionError = PermissionError
        self.fake.throw = lambda *args: (_ for _ in ()).throw(PermissionError())
        self.fake.get_all = lambda *args, **kw: []
        utils = types.ModuleType('frappe.utils')
        utils.flt = lambda v: float(v or 0)
        utils.getdate = lambda v: date.fromisoformat(str(v))
        leave = types.ModuleType('bsgroup.dashboard_leave')
        leave.dubai_today = lambda: '2026-11-07'
        self.modules = patch.dict(sys.modules, {'frappe': self.fake, 'frappe.utils': utils,
                                                'bsgroup.dashboard_leave': leave})
        self.modules.start()
        spec = importlib.util.spec_from_file_location('balance_test', Path(__file__).resolve().parents[1] / 'dashboard_leave_balance.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.payload = dict(valid_from='2026-11-07', valid_to='2026-12-31',
                            rows=[dict(user='own@example.com', current='-19'),
                                  dict(user='other@example.com', current='39.5')])

    def tearDown(self):
        self.modules.stop()

    def test_preserves_negative_zero_and_dash_without_other_user_data(self):
        for value in ['-19', '0', '-', '39.5']:
            self.payload['rows'][0]['current'] = value
            self.assertEqual(self.m.reference_row(self.payload, 'own@example.com', '2026-11-07'), value)
        self.assertIsNone(self.m.reference_row(self.payload, 'unknown', '2026-11-07'))

    def test_duplicate_invalid_and_expired_source_is_not_used(self):
        self.assertIsNone(self.m.reference_row(self.payload, 'own@example.com', '2027-01-01'))
        self.payload['rows'][0]['current'] = 'nan'
        self.assertIsNone(self.m.reference_row(self.payload, 'own@example.com', '2026-11-07'))
        self.payload['rows'].append(dict(user='own@example.com', current='1'))
        self.assertIsNone(self.m.reference_row(self.payload, 'own@example.com', '2026-11-07'))

    def test_context_reads_only_session_user_and_does_not_grant_allowance(self):
        called = []
        self.m.imported_reference = lambda user, today: called.append(user) or '-19'
        result = self.m.context()
        self.assertEqual(called, ['own@example.com'])
        self.assertEqual(result['source'], 'reference')
        self.assertEqual(result['balance'], '-19')
        self.assertNotIn('available', result)
        with self.assertRaises(TypeError):
            self.m.context(user='other@example.com')

    def test_guest_rejected(self):
        self.fake.session.user = 'Guest'
        with self.assertRaises(PermissionError):
            self.m.context()

    def test_native_balance_takes_precedence_and_pending_is_not_spendable(self):
        self.fake.get_all = lambda *args, **kw: [types.SimpleNamespace(name='OWN-EMPLOYEE')]
        native = types.ModuleType('hrms.hr.doctype.leave_application.leave_application')
        calls = []
        def details(employee, date):
            calls.append((employee, date))
            return {'leave_allocation': {'Annual Vacation': {'remaining_leaves': 15, 'leaves_pending_approval': 2}}}
        native.get_leave_details = details
        self.m.imported_reference = lambda *args: self.fail('Live allocation must win')
        with patch.dict(sys.modules, {'hrms.hr.doctype.leave_application.leave_application': native}):
            result = self.m.context()
        self.assertEqual(calls, [('OWN-EMPLOYEE', '2026-11-07')])
        self.assertEqual(result, dict(balance=15, pending=2, available=13, source='hrms', employee_linked=True, annual_status='available'))

    def test_zero_negative_unknown_and_pending_are_distinct(self):
        for value in ('0', '-8', '-19'):
            self.assertEqual(self.m.request_status('reference', value), 'empty')
        self.assertEqual(self.m.request_status('reference', '-'), 'unknown')
        self.assertEqual(self.m.request_status('reference', '39.5'), 'pending')
        self.assertEqual(self.m.request_status('hrms', 5, 0), 'empty')

    def test_selected_date_is_used_for_balance_and_expiry(self):
        calls=[]
        self.m.imported_reference=lambda user, day: calls.append(day) or None
        self.m.context(date='2027-01-01')
        self.assertEqual(calls, ['2027-01-01'])


if __name__ == '__main__':
    unittest.main()
