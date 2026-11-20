"""Discount, cost preservation, authorisation and retry regression checks."""
import importlib
import math
import sys
import types
import unittest
from unittest.mock import Mock, patch
from oman_quote_flow_unit import Doc, ValidationError, frappe, utils, flow

utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)
discount = importlib.import_module('bsgroup.dcs.quotation_discount')


class DiscountTests(unittest.TestCase):
    def setUp(self):
        self.q = Doc(name='Q1', docstatus=0, custom_deal_cost_sheet='D1',
            custom_oman_flow=1, net_total=900, apply_discount_on='Net Total', discount_amount=100)
        self.d = Doc(name='D1', currency='AED', total_selling=1000, total_cost=700,
            custom_working_total_selling=1000, custom_dcs_revision_no=1,
            items=[Doc(qty=10, selling_rate=100, cost_rate=70)], addtional_charges=[])
        self.d.reload = Mock()
        frappe.db.reset_mock(); frappe.db.get_value.side_effect=None
        frappe.get_roles.return_value=['BS Scoped Sales']
        frappe.defaults.get_global_default.side_effect=None
        frappe.defaults.get_global_default.return_value=1
        frappe.local.site='erp-bitssecureit.u.frappe.cloud'
        self.baseline=Mock()
        self.modules=patch.dict(sys.modules, {
            'bsgroup.api.dcs._common':types.SimpleNamespace(CUSTOMER_SIDE=['BS Scoped Sales', 'Managing Director']),
            'bsgroup.dcs.baseline':types.SimpleNamespace(ensure_baseline=self.baseline)})
        self.modules.start(); self.addCleanup(self.modules.stop)

    def test_amount_and_percentage_both_currencies(self):
        for currency,gross,amount,net in [('AED',1000,100,900),('OMR',100.126,1.123,99.003)]:
            with self.subTest(currency=currency):
                self.q.discount_amount=amount
                self.assertEqual(discount.net_selling(gross,self.q,currency),net)
                self.q.additional_discount_percentage=10
                self.assertEqual(discount.net_selling(gross,self.q,currency),round(gross-round(gross*.1,3 if currency=='OMR' else 2),3 if currency=='OMR' else 2))
                self.q.additional_discount_percentage=0

    def test_removing_discount_restores_gross(self):
        self.q.discount_amount=0
        self.assertEqual(discount.net_selling(1000,self.q,'AED'),1000)

    def test_invalid_discounts_rejected(self):
        for key,value in [('discount_amount',-1),('discount_amount',1001),('discount_amount',math.inf),
                          ('discount_amount',math.nan),('additional_discount_percentage',-1),('additional_discount_percentage',101)]:
            with self.subTest(key=key,value=value):
                q=Doc(self.q);q[key]=value
                with self.assertRaises(ValidationError):discount.net_selling(1000,q,'AED')

    def test_vat_inclusive_discount_rejected(self):
        self.q.apply_discount_on='Grand Total'
        with self.assertRaisesRegex(ValidationError,'Net Total'):discount.net_selling(1000,self.q,'AED')

    def test_po_gross_preserves_line_amounts_and_customs(self):
        self.d.items=[Doc(qty=q,selling_rate=round(a/q,9)) for q,a in [(10,7500),(10,37976.88),(10,2676.79),(330,137265.66),(1,55000)]]
        self.d.addtional_charges=[Doc(selling_amount=1370,amount=0)]
        self.assertEqual(discount.gross_selling(self.d),241789.33)
        self.q.discount_amount=23789.33
        self.assertEqual(discount.net_selling(discount.gross_selling(self.d),self.q,'AED'),218000)

    def test_sync_each_site_preserves_costs_and_same_quote(self):
        for site in ('erp-bitssecureit.u.frappe.cloud','erp-om.k.frappe.cloud'):
            frappe.local.site=site
            with patch.object(flow,'require_single_quote') as single, patch.object(discount,'record_net_revision') as revision:
                discount.sync(self.q,self.d)
                single.assert_called_once_with(self.d)
                self.assertEqual(revision.call_args.args[1],900)
                self.assertEqual(self.d.total_cost,700)
                self.assertEqual(self.d.items[0].cost_rate,70)
                self.assertEqual(self.q.name,'Q1')

    def test_retry_does_not_create_another_revision(self):
        self.d.total_selling=self.d.custom_working_total_selling=900
        with patch.object(discount,'record_net_revision') as revision:
            discount.sync(self.q,self.d);discount.sync(self.q,self.d)
            revision.assert_not_called()

    def test_frozen_discount_change_rejected(self):
        self.d.custom_baseline_frozen=1
        with self.assertRaisesRegex(ValidationError,'awarded'):discount.sync(self.q,self.d)

    def test_changed_net_rejected(self):
        self.q.net_total=899
        with self.assertRaisesRegex(ValidationError,'net total'):discount.sync(self.q,self.d)

    def test_non_commercial_change_rejected(self):
        frappe.get_roles.return_value=['Presales']
        with patch.object(flow,'require_single_quote'), self.assertRaisesRegex(ValidationError,'commercial'):
            discount.sync(self.q,self.d)
        self.baseline.assert_not_called()

    def test_existing_submitted_and_cancelled_not_rewritten(self):
        with patch.object(discount,'record_net_revision') as revision:
            for state in (1,2):
                self.q.docstatus=state
                discount.sync(self.q,self.d)
            revision.assert_not_called()

    def test_submission_from_draft_reconciles_before_award(self):
        self.q.docstatus=1;self.q._before=Doc(docstatus=0)
        with patch.object(flow,'require_single_quote'),patch.object(discount,'record_net_revision') as revision:
            discount.sync(self.q,self.d)
            revision.assert_called_once()

    def test_boq_revision_preserves_existing_percentage_discount(self):
        self.d.custom_quotation='Q1';self.d.total_selling=2000
        frappe.db.get_value.return_value=Doc(custom_deal_cost_sheet='D1',docstatus=0,apply_discount_on='Net Total',additional_discount_percentage=10,discount_amount=100)
        discount.apply_to_calculated_sheet(self.d)
        self.assertEqual(self.d.total_selling,1800)
        self.assertEqual(self.d.total_cost,700)

    def test_boq_wrong_link_does_not_apply_discount(self):
        self.d.custom_quotation='Q1'
        frappe.db.get_value.return_value=Doc(custom_deal_cost_sheet='OTHER',docstatus=0)
        discount.apply_to_calculated_sheet(self.d)
        self.assertEqual(self.d.total_selling,1000)

    def test_rate_precision_only_not_amount_or_cost(self):
        row=Doc(precision=lambda field,parent=None:2)
        q=Doc(items=[row],precision=lambda field,parent=None:2)
        discount.preserve_rate_precision(q)
        self.assertEqual(q.precision('rate','items'),9)
        self.assertEqual(q.precision('amount','items'),2)
        self.assertEqual(row.precision('rate'),9)
        self.assertEqual(row.precision('amount'),2)
        self.assertEqual(row.precision('custom_cost_rate'),2)

    def test_net_revision_margin_approval_and_cost_preservation(self):
        # Exercise the production approval functions without their service imports.
        import ast, pathlib
        tree=ast.parse((pathlib.Path(__file__).resolve().parents[1]/'bsgroup/api/dcs/negotiation.py').read_text())
        names={'pct','requirement','gate_for','state_for','rev_state_for','why_approval','why_gate','display_percent'}
        module=types.ModuleType('bsgroup.api.dcs.negotiation')
        module.__dict__.update(CEILING=26,MD_THRESHOLD=16,MARGIN_FLOOR=20)
        exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'negotiation','exec'),module.__dict__)
        module.write_revision=Mock(return_value='R2')
        self.d.total_cost=174609;self.d.custom_working_total_selling=240420.5;self.d.custom_baseline_selling=240420.5
        with patch.dict(sys.modules,{'bsgroup.api.dcs.negotiation':module,'bsgroup.dcs.governance':types.SimpleNamespace(record_governance_event=Mock())}):
            discount.record_net_revision(self.d,218000,'Test')
        values=frappe.db.set_value.call_args.args[2]
        self.assertEqual(values['margin_value'],43391)
        self.assertAlmostEqual(values['margin_percent'],19.90412844036697)
        self.assertEqual(values['custom_approval_state'],'Pending Manager')
        self.assertNotIn('total_cost',values)
        self.assertNotIn('custom_working_total_cost',values)
        args=module.write_revision.call_args.args
        self.assertEqual(args[4],174609);self.assertEqual(args[8],174609)


if __name__=='__main__':unittest.main()
