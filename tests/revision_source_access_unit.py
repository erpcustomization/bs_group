"""Narrow Lead sharing regression tests; no live data or permissions changed."""
import sys
import types
import unittest
from unittest.mock import Mock, patch
from quotation_revision_unit import RevisionTests, frappe
from bsgroup.dcs.revision_source_access import ensure_source_read


class SourceAccessTests(RevisionTests):
    def setUp(self):
        super().setUp()
        self.q.quotation_to = 'Lead'; self.q.party_name = 'L-1'
        self.p.presales_owner = 'presales@example.com'
        frappe.get_roles.return_value = ['BS Scoped Presales']
        frappe.db.get_value.side_effect = lambda dt, *a, **kw: 1 if dt == 'User' else None
        self.read = patch.object(frappe, 'has_permission', return_value=False, create=True)
        self.read.start(); self.addCleanup(self.read.stop)
        self.add = Mock()
        p = patch.dict(sys.modules, {'frappe.share': types.SimpleNamespace(add=self.add)})
        p.start(); self.addCleanup(p.stop)

    # Only run this class's source-access cases, not the inherited revision suite.
    def test_exact_lead_read_only(self):
        ensure_source_read(self.d, self.q, self.p)
        self.add.assert_called_once_with('Lead', 'L-1', user='presales@example.com',
            read=1, write=0, share=0, submit=0, notify=0, flags={'ignore_share_permission': True})

    def test_existing_read_is_retry_safe(self):
        frappe.has_permission.return_value = True
        ensure_source_read(self.d, self.q, self.p)
        self.add.assert_not_called()

    def test_mismatched_link_denied(self):
        self.p.custom_deal_cost_sheet = 'OTHER'
        ensure_source_read(self.d, self.q, self.p)
        self.add.assert_not_called()

    def test_customer_not_shared(self):
        self.q.quotation_to = 'Customer'
        ensure_source_read(self.d, self.q, self.p)
        self.add.assert_not_called()

    def test_disabled_user_not_shared(self):
        frappe.db.get_value.side_effect = lambda *a, **kw: 0
        ensure_source_read(self.d, self.q, self.p)
        self.add.assert_not_called()

    def test_other_role_not_shared(self):
        frappe.get_roles.return_value = ['Employee']
        ensure_source_read(self.d, self.q, self.p)
        self.add.assert_not_called()

    def test_existing_grants_preserved(self):
        frappe.db.get_value.side_effect = lambda dt, *a, **kw: 1 if dt == 'User' else {'write':1,'share':0,'submit':0}
        ensure_source_read(self.d, self.q, self.p)
        self.assertEqual(self.add.call_args.kwargs['write'], 1)


if __name__ == '__main__':
    names = [name for name in SourceAccessTests.__dict__ if name.startswith('test_')]
    result = unittest.TextTestRunner().run(unittest.TestSuite(SourceAccessTests(n) for n in names))
    sys.exit(not result.wasSuccessful())
