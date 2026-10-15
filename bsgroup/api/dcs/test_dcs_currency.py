"""Currency regressions; staging only. No cross-currency conversion is performed."""
from unittest.mock import patch
import frappe
from frappe.tests import IntegrationTestCase
from bsgroup.tests.dcs_fixtures import make_dcs, make_user
from bsgroup.api.dcs.test_dcs_boq_revision import payload
from bsgroup.api.dcs.boq_revision import line_history
from bsgroup.api.dcs.negotiation import scenario
from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation

class IntegrationTestDCSCurrency(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()
        cls.md=make_user("zztest-currency-md@example.com",["System Manager","Managing Director","Sales Manager","Presales","Accounts User"])

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def roundtrip(self, suffix, currency, selling, revised):
        frappe.set_user("Administrator")
        company="Bits Secure IT Infrastructure LLC - "+suffix
        if not frappe.db.exists("Company",company):
            self.skipTest("Currency staging company is not configured: "+company)
        doc=make_dcs(suffix="CUR"+suffix+frappe.generate_hash(length=6),company=company,
            currency=currency,deal_owner=self.md,items=[{"item_code":frappe.db.get_value("Item",{"disabled":0},"name"),
            "qty":1,"cost_rate":970.960,"selling_rate":selling}],submit=True)
        doc.reload()
        self.assertEqual(doc.currency,currency)
        self.assertAlmostEqual(doc.custom_working_total_selling,selling,6)
        self.assertEqual(doc.custom_approval_required,"Manager")
        before=frappe.copy_doc(doc)
        # Retain row identity for immutable line-delta verification.
        before.items[0].name=doc.items[0].name
        p=payload(doc);p["items"][0]["cost_rate"]=revised
        frappe.set_user(self.md)
        result=frappe.call("bsgroup.api.dcs.boq_revision.dcs_apply_boq_revision",
            dcs=doc.name,expected_modified=str(doc.modified),source="Vendor",
            reason="ZZTEST currency-preserving BOQ revision",**p)
        self.assertEqual(result["ok"],1,result)
        doc.reload()
        self.assertAlmostEqual(doc.total_cost,revised,6)
        self.assertAlmostEqual(doc.total_selling,selling,6)
        self.assertEqual(doc.items[0].currency,currency)
        self.assertEqual(doc.custom_approval_required,"None")
        history=line_history(before,doc)
        self.assertAlmostEqual(history[0]["cost_delta"],round(revised-970.960,3 if currency=="OMR" else 2),6)
        screen=frappe.call("bsgroup.api.dcs.negotiation.dcs_screen3",dcs=doc.name)
        self.assertEqual(screen["ok"],1,screen)
        self.assertAlmostEqual(screen["header"]["money"]["total_cost"],revised,6)
        default_reader=frappe.db.get_default
        if currency == "OMR":
            with patch.object(frappe.db,"get_default",side_effect=lambda key,*a,**kw: 2 if key=="currency_precision" else default_reader(key,*a,**kw)):
                with self.assertRaisesRegex(frappe.ValidationError,"three-decimal currency precision"):
                    make_quotation(doc.name)
        # Model the Oman site's three-decimal setting without changing any site defaults.
        with patch.object(frappe.db,"get_default",side_effect=lambda key,*a,**kw: (3 if currency=="OMR" else 2) if key=="currency_precision" else default_reader(key,*a,**kw)):
            quote=frappe.get_doc("Quotation",make_quotation(doc.name))
        self.assertEqual(quote.currency,currency)
        self.assertAlmostEqual(quote.items[0].rate,selling,6)
        from bsgroup.dcs.quotation_control import validate_position
        validate_position(doc, quote)
        if currency == "OMR":
            quote.items[0].rate = selling + 0.001
            with self.assertRaisesRegex(frappe.ValidationError,"scope or selling rates"):
                validate_position(doc,quote)
            quote.items[0].rate = selling
            quote.total = selling + 0.001
            with self.assertRaisesRegex(frappe.ValidationError,"selling total"):
                validate_position(doc,quote)
            quote.total = selling
            # Management and handover projections must retain the same amounts.
            # The app's existing company filter follows the selected company.
            # Model the Oman selection, retaining the real permission query hook.
            read_user_default=frappe.defaults.get_user_default
            with patch("frappe.defaults.get_user_default",side_effect=lambda key,*a,**kw: company if key.lower()=="company" else read_user_default(key,*a,**kw)):
                screen1 = frappe.call("bsgroup.api.dcs.command_center.dcs_screen1")
            displayed = next(r for r in screen1["browse"] if r["name"] == doc.name)
            self.assertEqual(displayed["currency"],currency)
            self.assertAlmostEqual(displayed["selling"],selling,6)
            self.assertAlmostEqual(displayed["cost"],revised,6)
            frappe.db.set_value("Deal Cost Sheet",doc.name,{
                "custom_award_state":"Awarded", "custom_baseline_frozen":1,
                "custom_frozen_revision_no":doc.custom_dcs_revision_no,
                "custom_frozen_total_cost":revised,"custom_frozen_total_selling":selling,
                "custom_po_value":selling})
            view=frappe.call("bsgroup.api.dcs.handover.dcs_screen5",dcs=doc.name)
            self.assertEqual(view["ok"],1,view)
            self.assertAlmostEqual(view["frozen_baseline"]["total_selling"],selling,6)
            self.assertAlmostEqual(view["frozen_baseline"]["total_cost"],revised,6)
            self.assertAlmostEqual(view["po"]["value"],selling,6)
            self.assertAlmostEqual(view["supplier_exposure"]["amount"],revised,6)
            doc.reload()
            from bsgroup.api.dcs.handover import release_drift
            doc.custom_working_total_selling=selling+0.001
            self.assertEqual(release_drift(doc),"living")
            reconciliation=frappe.call("bsgroup.api.dcs.award.dcs_po_reconcile",dcs=doc.name,
                po_reference="ZZTEST currency PO",po_value=selling+0.002,
                po_scope_revision=doc.custom_revision_reference,payment_terms_accepted=1)
            self.assertEqual(reconciliation["ok"],1,reconciliation)
            doc.reload()
            self.assertEqual(doc.custom_po_value_match,"Mismatch")


    def test_omr_boq_history_workspace_and_quotation_keep_three_decimals(self):
        self.roundtrip("OM","OMR",1138.425,900.123)

    def test_aed_roundtrip_keeps_two_decimal_rates(self):
        self.roundtrip("AE","AED",1138.42,900.12)

    def test_omr_scenarios_preserve_precision_without_changing_margin_gate(self):
        result=scenario("hold","Hold",0.801,1.001,1.001,"ZZTEST","OMR")
        self.assertEqual(result["total_cost"],0.801)
        self.assertEqual(result["total_selling"],1.001)
        self.assertEqual(result["approval_required"],"Manager")

    def test_omr_approval_snapshot_detects_one_baisa_drift(self):
        from bsgroup.dcs.commercial_authority import authorised_position
        sheet=frappe._dict(name="ZZTEST currency snapshot",currency="OMR",
            custom_working_total_selling=100.001,custom_working_total_cost=90.001,
            custom_baseline_selling=100.001,custom_approval_required="Manager",
            custom_approval_state="Approved",custom_approved_revision_no=1,
            custom_dcs_revision_no=1,custom_revision_reference="ZZTEST revision",
            custom_approved_by="manager@example.com",custom_approved_total_cost=90.000,
            custom_approved_total_selling=100.001)
        revision=frappe._dict(dcs=sheet.name,approval_state="Approved",decided_by=sheet.custom_approved_by)
        with patch("bsgroup.dcs.input_validation.position_is_valid",return_value=True), \
             patch("bsgroup.dcs.manager_approval.route_for",return_value={}), \
             patch.object(frappe.db,"get_value",return_value=revision):
            self.assertFalse(authorised_position(sheet))
            sheet.custom_approved_total_cost=90.001
            self.assertTrue(authorised_position(sheet))
