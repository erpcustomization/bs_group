import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


class AnnualAllocationTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.throw = lambda message: (_ for _ in ()).throw(ValueError(message))
        self.doc = types.SimpleNamespace(name='LAL', employee='EMP', leave_type='Annual Vacation',
            new_leaves_allocated=30, unused_leaves=0, total_leaves_allocated=30, docstatus=1,
            modified='version-1', expired=0, from_date='2026-11-07', to_date='2026-12-31',
            check_permission=Mock(), save=Mock(), add_comment=Mock(),
            get_doc_before_save=Mock(return_value=None))
        self.f.get_doc = Mock(return_value=self.doc)
        utils = types.ModuleType('frappe.utils')
        utils.flt = lambda v: float(v or 0)
        utils.getdate = lambda v: date.fromisoformat(str(v))
        utils.escape_html = lambda v: v.replace('<', '&lt;')
        management = types.ModuleType('bsgroup.hr_management')
        self.guard = management._guard = Mock()
        dashboard = types.ModuleType('bsgroup.dashboard_leave')
        dashboard.dubai_today = lambda: '2026-11-08'
        self.native = types.ModuleType('hrms.hr.doctype.leave_application.leave_application')
        self.native.get_leave_details = lambda *a: {'leave_allocation': {'Annual Vacation': {
            'remaining_leaves': 10, 'leaves_pending_approval': 2}}}
        self.patch = patch.dict(sys.modules, {'frappe': self.f, 'frappe.utils': utils,
            'bsgroup.hr_management': management, 'bsgroup.dashboard_leave': dashboard,
            'hrms.hr.doctype.leave_application.leave_application': self.native})
        self.patch.start()
        spec = importlib.util.spec_from_file_location('allocation_test', Path(__file__).resolve().parents[1] / 'hr_annual_allocation.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        self.patch.stop()

    def test_limits_finite_and_fractional_days(self):
        for value in [0, 0.5, 25.5, 26]:
            self.assertEqual(self.m.allocation_days(value), value)
        for value in [-1, 26.01, 30, 'nan', 'Infinity', 'bad', None]:
            with self.assertRaises(ValueError): self.m.allocation_days(value)

    def test_oman_keeps_native_policy_and_never_copies_uae_cap(self):
        self.f.conf = {'host_name': 'https://erp-om.bitssecureit.com'}
        self.f.get_cached_value = Mock(return_value=30)
        self.assertEqual(self.m.allocation_limit(), 30)
        self.assertEqual(self.m.allocation_days(30), 30)
        with self.assertRaisesRegex(ValueError, '30'): self.m.allocation_days(30.01)
        self.f.get_cached_value.return_value = 0
        self.assertIsNone(self.m.allocation_limit())
        self.assertEqual(self.m.allocation_days(35), 35)

    def test_guard_and_document_permission_precede_mutation(self):
        self.guard.side_effect = PermissionError()
        with self.assertRaises(PermissionError): self.m.save('LAL', 26, 'version-1', 'Cap')
        self.f.get_doc.assert_not_called()
        self.guard.side_effect = None
        self.doc.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): self.m.save('LAL', 26, 'version-1', 'Cap')
        self.doc.save.assert_not_called()
        self.assertEqual(self.doc.new_leaves_allocated, 30)

    def test_stale_version_and_reason_required(self):
        with self.assertRaisesRegex(ValueError, 'someone else'): self.m.save('LAL', 26, 'old', 'Cap')
        with self.assertRaisesRegex(ValueError, 'reason'): self.m.save('LAL', 26, 'version-1', '')
        self.doc.save.assert_not_called()

    def test_native_save_preserves_ledger_path_and_audit(self):
        self.doc.unused_leaves = 2
        self.m.save('LAL', 26, 'version-1', 'Chairman approved 26-day limit')
        self.assertEqual(self.doc.new_leaves_allocated, 24)
        self.assertEqual(self.doc.total_leaves_allocated, 26)
        self.doc.save.assert_called_once_with()
        self.doc.add_comment.assert_called_once()
        self.assertEqual(self.doc.check_permission.call_args_list[0].args, ('read',))
        self.assertEqual(self.doc.check_permission.call_args_list[1].args, ('write',))

    def test_carry_forward_counts_towards_cap_and_other_types_unchanged(self):
        self.doc.new_leaves_allocated = 25
        self.doc.unused_leaves = 2
        with self.assertRaisesRegex(ValueError, '26'): self.m.validate_allocation(self.doc)
        self.doc.leave_type = 'Sick Leave'
        self.m.validate_allocation(self.doc)

    def test_reduction_cannot_consume_used_or_pending_days(self):
        self.doc.get_doc_before_save.return_value = types.SimpleNamespace(docstatus=1,total_leaves_allocated=30)
        self.doc.new_leaves_allocated = 21  # remaining 10 - reduction 9 < pending 2
        with self.assertRaisesRegex(ValueError, 'reserved'): self.m.validate_allocation(self.doc)
        self.doc.new_leaves_allocated = 22
        self.m.validate_allocation(self.doc)
        self.assertEqual(self.doc.total_leaves_allocated, 22)

    def test_readonly_total_cannot_bypass_cap_or_diverge_from_ledger(self):
        self.doc.new_leaves_allocated = 26
        self.doc.total_leaves_allocated = 99
        self.m.validate_allocation(self.doc)
        self.assertEqual(self.doc.total_leaves_allocated, 26)


if __name__ == '__main__': unittest.main()
