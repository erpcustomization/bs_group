import json, pathlib, unittest
from unittest.mock import patch
import oman_quote_flow_unit as fixture
frappe, Doc, flow, ValidationError = fixture.frappe, fixture.Doc, fixture.flow, fixture.ValidationError


class UAEFlowTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.FlowTests();self.base.setUp();self.q=self.base.q;self.s=self.base.s
        frappe.local.site='erp-bitssecureit.u.frappe.cloud'
        frappe.defaults.get_global_default.side_effect=lambda key: int(key in (flow.UAE_FLAG,'bs_oman_client_descriptions'))
        frappe.get_doc.return_value=self.s
        self.q.is_new=lambda:True

    def test_uae_requires_its_own_opt_in(self):
        self.assertTrue(flow.enabled())
        frappe.defaults.get_global_default.side_effect=lambda key:int(key==flow.FLAG)
        self.assertFalse(flow.enabled())

    def test_duplicate_insert_checks_all_quotes_under_dcs_lock(self):
        frappe.get_all.return_value=['Q-EXISTING']
        with self.assertRaisesRegex(ValidationError,'already exists'):flow.validate(self.q)
        frappe.get_doc.assert_called_with('Deal Cost Sheet','DCS-1',for_update=True)
        # The lookup is not restricted to the creator, so another user's quote is detected.
        self.assertEqual(frappe.get_all.call_args.kwargs['filters'],{'custom_deal_cost_sheet':'DCS-1','docstatus':['!=',2]})

    def test_duplicate_pair_blocks_revision_even_with_return_link(self):
        frappe.get_all.return_value=['Q-1','Q-2']
        with self.assertRaisesRegex(ValidationError,'multiple active'):flow.guard_dcs_revision(self.s)
        self.assertIsNone(flow.linked_quotation(self.s))
        self.assertEqual(self.s.custom_quotation,'Q-1')

    def test_conflict_context_is_read_only_and_flags_review(self):
        frappe.get_all.return_value=['Q-1','Q-2']
        result=flow.dcs_context('DCS-1')
        self.assertTrue(result['conflict']);self.assertFalse(result['auto_sync'])
        frappe.db.set_value.assert_not_called()

    def test_discount_policy_and_historical_isolation(self):
        self.q.apply_discount_on='Grand Total';flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Net Total')
        self.q.update(docstatus=1,custom_oman_flow=0,apply_discount_on='Grand Total')
        self.assertFalse(flow.pilot(self.q));flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Grand Total')

    def test_uae_administrator_setup_only(self):
        self.assertFalse(flow.setup_authorised())
        frappe.get_roles.return_value=['System Manager'];self.assertTrue(flow.setup_authorised())
        frappe.local.site='unrelated.example.com';self.assertFalse(flow.setup_authorised())

    def test_uae_template_supports_private_description_and_revision(self):
        from bsgroup.oman_item_description import print_html
        path=pathlib.Path(__file__).resolve().parents[1]/'bsgroup/bs_group/print_format/enterprise_quotation_3/enterprise_quotation_3.json'
        html=json.loads(path.read_text(encoding='utf-8'))['html']
        result=print_html(html)
        self.assertIn('custom_oman_use_costing_description',result)
        self.assertIn('custom_oman_client_description',result)
        self.assertEqual(result,print_html(result))
        self.assertEqual(html.count('{%- set rev = doc.name.split("-")|last if doc.amended_from else "0" -%}'),1)
        self.assertEqual(flow.print_formats(),('EnterPrise Quotation 3','Enterprise Quotation - UAE Workflow'))

    def test_hook_registration_preserves_existing_and_is_idempotent(self):
        from bsgroup.quotation_workflow_hooks import configure
        ns=dict(doc_events={'Quotation':{'validate':'existing.validate'}},doctype_js={},doctype_list_js={})
        configure(ns);configure(ns)
        self.assertEqual(ns['doc_events']['Quotation']['validate'],['bsgroup.oman_quotation_flow.validate','existing.validate'])
        self.assertEqual(ns['doc_events']['Deal Cost Sheet']['on_submit'],['bsgroup.oman_quotation_flow.dcs_submitted'])

if __name__=='__main__':unittest.main(verbosity=2)
