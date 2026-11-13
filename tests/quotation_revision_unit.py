"""Revision routing, identity, permissions, retry and rollback regression tests."""
import importlib
import types
import unittest
from unittest.mock import Mock, patch
from oman_quote_flow_unit import Doc, ValidationError, frappe, utils, flow

utils.now = lambda: '2026-11-13 12:00:00'
frappe.generate_hash = lambda **kw: 'test'
frappe.QueryDeadlockError = type('Deadlock', (Exception,), {})
frappe.clear_document_cache = Mock()
revision = importlib.import_module('bsgroup.quotation_revision')


class RevisionTests(unittest.TestCase):
    def setUp(self):
        frappe.db.reset_mock(); frappe.get_doc.reset_mock()
        frappe.get_roles.return_value = ['BS Scoped Sales']
        frappe.session.user = 'sales@example.com'
        self.q = Doc(doctype='Quotation', name='Q-1', docstatus=0, modified='M1',
            custom_deal_cost_sheet='D-1', custom_pipeline_stage='Sent')
        self.d = Doc(doctype='Deal Cost Sheet', name='D-1', docstatus=1, modified='D1',
            custom_quotation='Q-1', presales_request='P-1', custom_deal_status='Quoted',
            opportunity='O-1', party_type='Lead', party='L-1', company='AE')
        self.p = Doc(doctype='Presales Request', name='P-1', docstatus=1,
            custom_deal_cost_sheet='D-1', opportunity='O-1', party_type='Lead', party='L-1',
            company='AE', status='Submitted to Sales')
        self.docs = {('Quotation','Q-1'):self.q, ('Deal Cost Sheet','D-1'):self.d,
                     ('Presales Request','P-1'):self.p}
        frappe.get_doc.side_effect = lambda *a, **kw: Doc(a[0]) if isinstance(a[0], dict) else self.docs[a[:2]]
        self.original = {key:dict(value) for key,value in self.docs.items()}
        def write(dt, name, values, **kw):
            self.docs[dt,name].update(values)
        frappe.db.set_value.side_effect = write
        def rollback(**kw):
            for key, values in self.original.items():
                self.docs[key].clear(); self.docs[key].update(values)
        frappe.db.rollback.side_effect = rollback
        self.identity = patch.dict('sys.modules', {
            'bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet':types.SimpleNamespace(quotation_deal_identity=lambda s,q:''),
            'bsgroup.api.dcs._common':types.SimpleNamespace(CUSTOMER_SIDE=['BS Scoped Sales','Sales User','Managing Director'])})
        self.identity.start(); self.addCleanup(self.identity.stop)
        for target, value in [(flow,'_quotation'), (flow,'guard_dcs_revision')]:
            p = patch.object(target,value,return_value=self.q if value=='_quotation' else True)
            p.start();self.addCleanup(p.stop)
        self.event_patch = patch.object(revision,'record_governance_event')
        self.event = self.event_patch.start();self.addCleanup(self.event_patch.stop)

    def begin(self, choice='Yes'):
        return revision.begin('Q-1',choice,'M1')

    def test_yes_changes_only_linked_states_and_is_retry_safe(self):
        result=self.begin()
        self.assertEqual(result['dcs'],'D-1')
        self.assertEqual(self.d.custom_deal_status,'To be revised')
        self.assertEqual(self.p.status,'Rework')
        self.assertEqual(self.d.docstatus,1)
        self.assertEqual(self.q,self.original['Quotation','Q-1'])
        self.begin()
        self.assertEqual(frappe.db.set_value.call_count,2)
        self.assertEqual(self.event.call_count,1)
        self.assertIn('write',self.d._permissions)
        self.assertIn('read',self.p._permissions)

    def test_no_returns_same_sheet_without_status_writes(self):
        self.assertEqual(self.begin('No')['dcs'],'D-1')
        frappe.db.set_value.assert_not_called()

    def test_yes_then_successful_boq_completion_returns_to_sales(self):
        self.begin(); revision.finish(self.d)
        self.assertEqual(self.d.custom_deal_status,'Submitted to Sales')
        self.assertEqual(self.p.status,'Submitted to Sales')
        self.assertEqual(self.event.call_count,2)

    def test_missing_request_does_not_silently_create_one(self):
        self.d.presales_request=None
        with self.assertRaisesRegex(ValidationError,'no linked Presales'):self.begin()
        frappe.db.set_value.assert_not_called()

    def test_wrong_deal_or_reverse_link_is_rejected(self):
        for field in ('opportunity','party','company','custom_deal_cost_sheet'):
            with self.subTest(field=field):
                self.p[field]='OTHER'
                with self.assertRaisesRegex(ValidationError,'does not link'):self.begin()
                frappe.db.set_value.assert_not_called()

    def test_won_lost_and_submitted_quotes_remain_frozen(self):
        for stage in ('Won','Lost'):
            self.q.custom_pipeline_stage=stage
            with self.assertRaisesRegex(ValidationError,'frozen'):self.begin()
        self.q.custom_pipeline_stage='Sent';self.q.docstatus=1
        with self.assertRaisesRegex(ValidationError,'frozen'):self.begin()
        frappe.db.set_value.assert_not_called()

    def test_stale_quote_and_awarded_costing_rejected(self):
        self.q.modified='M2'
        with self.assertRaisesRegex(ValidationError,'changed'):self.begin()
        self.q.modified='M1';self.d.custom_award_state='Awarded'
        with self.assertRaisesRegex(ValidationError,'awarded'):self.begin()
        frappe.db.set_value.assert_not_called()

    def test_sales_role_required(self):
        frappe.get_roles.return_value=['System Manager']
        with self.assertRaisesRegex(ValidationError,'Sales access'):self.begin()
        frappe.db.set_value.assert_not_called()

    def test_cannot_silently_take_over_pending_presales_work(self):
        self.begin()
        with self.assertRaisesRegex(ValidationError,'already with Presales'):self.begin('No')

    def test_audit_failure_rolls_back_both_status_updates(self):
        self.event.side_effect=RuntimeError('audit failure')
        with self.assertRaisesRegex(RuntimeError,'audit failure'):self.begin()
        self.assertEqual(self.d.custom_deal_status,'Quoted')
        self.assertEqual(self.p.status,'Submitted to Sales')
        frappe.db.rollback.assert_called_once()


if __name__ == '__main__': unittest.main()
