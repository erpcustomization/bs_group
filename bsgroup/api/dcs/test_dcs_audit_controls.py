"""Staging-only integration regression for the 13 October audit."""
from unittest.mock import patch
import json
import frappe
from frappe.tests import IntegrationTestCase
from bsgroup.tests.dcs_fixtures import ensure, make_dcs, make_user, make_reporting_line
from bsgroup.api.dcs.test_dcs_vendor_revision import make_quotation_for
from bsgroup.dcs.quotation_control import validate_sales_order, validate_position
from bsgroup.dcs.commercial_authority import authorised_position

REV = "bsgroup.api.dcs.negotiation.dcs_apply_revision"
DECIDE = "bsgroup.api.dcs.approval.dcs_approval_decision"
AWARD = "bsgroup.api.dcs.award.dcs_record_award"

class IntegrationTestDCSAuditControls(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()
        for role in ["Presales", "Sales User", "Sales Manager", "Managing Director", "Technical Engineer"]:
            ensure("Role", role, {"role_name": role}, insert=False)
        cls.md = make_user("zztest-audit-md@example.com", ["Sales Manager", "Managing Director"])
        cls.presales = make_user("zztest-audit-presales@example.com", ["Presales"])
        cls.sales = make_user("zztest-audit-sales@example.com", ["Sales User"])
        cls.tech = make_user("zztest-audit-tech@example.com", ["Technical Engineer"])

        cls.manager = make_user("zztest-audit-manager@example.com", ["Employee"])

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        make_reporting_line(self.md, self.manager)
        make_reporting_line(self.presales, self.manager)
        self.doc = make_dcs(suffix=frappe.generate_hash(length=8), submit=True)

    def decide(self, **args):
        actor = frappe.session.user
        frappe.set_user(self.manager)
        try:
            return frappe.call("bsgroup.api.dcs.approval.dcs_approval_decision", dcs=self.doc.name, **args)
        finally:
            frappe.set_user(actor)

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def revise(self, **args):
        frappe.set_user(self.md)
        r = frappe.call(REV, dcs=self.doc.name, source="Vendor", reason="ZZTEST audit revision", **args)
        self.assertEqual(r["ok"], 1, r)
        self.doc.reload()
        return r

    def award(self):
        frappe.set_user(self.md)
        return frappe.call(AWARD, dcs=self.doc.name, award_reference="ZZTEST audit PO", evidence_type="Customer PO")

    def reject(self):
        frappe.set_user(self.md)
        result = self.decide( action="Reject", reason="ZZTEST rejected margin")
        self.assertEqual(result["ok"], 1, result)
        self.doc.reload()
        return self.doc.custom_revision_reference

    def test_initial_below_floor_requires_manager_even_without_concession(self):
        frappe.set_user(self.md)
        d = make_dcs(suffix=frappe.generate_hash(length=8), submit=False)
        d.items[0].cost_rate = 1250
        d.save(ignore_permissions=True)
        d.submit()
        d.reload()
        self.assertEqual(d.custom_approval_required, "Manager")
        self.assertEqual(d.custom_concession_percent_from_baseline, 0)
        self.assertEqual(d.custom_approval_state, "Pending Manager")
        self.doc = d
        self.assertEqual(self.award()["ok"], 0)
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": d.name, "event_code": "DCS_AWARD_RECORDED"}), 0)

    def test_revised_below_floor_requires_manager_and_old_approval_cannot_authorise(self):
        self.revise(new_total_cost=1250)
        self.assertEqual(self.doc.custom_approval_required, "Manager")
        self.assertEqual(self.award()["ok"], 0)
        approved = self.decide( action="Approve", reason="ZZTEST margin exception")
        self.assertEqual(approved["ok"], 1, approved)
        self.doc.reload()
        self.assertTrue(authorised_position(self.doc))
        self.revise(new_total_cost=1300)
        self.assertFalse(authorised_position(self.doc))
        self.assertEqual(self.award()["ok"], 0)

    def test_reject_revise_exact_floor_proceeds_and_retains_rejection(self):
        self.revise(new_total_cost=1250)
        old = self.reject()
        self.revise(new_total_cost=1200)
        self.assertEqual(self.doc.custom_working_margin_percent, 20)
        self.assertEqual(self.doc.custom_approval_required, "None")
        self.assertTrue(authorised_position(self.doc))
        rejected = frappe.get_doc("DCS Revision", old)
        self.assertEqual(rejected.approval_state, "Rejected")
        self.assertEqual(rejected.decided_by, self.manager)
        self.assertEqual(rejected.decision_reason, "ZZTEST rejected margin")
        self.assertEqual(self.doc.docstatus, 1)
        self.assertEqual(self.award()["ok"], 1)
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": self.doc.name, "event_code": "DCS_APPROVAL_APPROVED"}), 0)

    def test_reject_revise_below_floor_still_requires_manager(self):
        self.revise(new_total_cost=1300)
        old = self.reject()
        self.revise(new_total_cost=1250)
        self.assertEqual(self.doc.custom_approval_required, "Manager")
        self.assertEqual(self.doc.custom_approval_state, "Pending Manager")
        self.assertEqual(self.award()["ok"], 0)
        self.assertEqual(frappe.db.get_value("DCS Revision", old, "approval_state"), "Rejected")

    def test_reject_revise_above_floor_with_concession_trigger_requires_manager(self):
        self.revise(new_total_cost=1250)
        self.reject()
        frappe.set_user(self.md)
        r = frappe.call(REV, dcs=self.doc.name, source="Customer", reason="ZZTEST discount",
                        new_total_cost=900, new_total_selling=1200)
        self.assertEqual(r["ok"], 1, r)
        self.doc.reload()
        self.assertEqual(self.doc.custom_working_margin_percent, 25)
        self.assertEqual(self.doc.custom_approval_required, "Manager")
        self.assertEqual(self.award()["ok"], 0)

    def test_presales_actual_docperm_allows_buying_only(self):
        frappe.set_user(self.presales)
        self.assertTrue(frappe.has_permission("Deal Cost Sheet", "read"))
        self.assertTrue(frappe.has_permission("Deal Cost Sheet", "write"))
        r = frappe.call(REV, dcs=self.doc.name, source="Vendor", reason="ZZTEST buying", new_total_cost=1100)
        self.assertEqual(r["ok"], 1, r)
        r = frappe.call(REV, dcs=self.doc.name, source="Customer", reason="ZZTEST forbidden selling", new_total_selling=1400)
        self.assertEqual(r["ok"], 0, r)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.doc.name, "custom_working_total_selling"), 1500)
        self.assertEqual(frappe.call(AWARD, dcs=self.doc.name, award_reference="ZZTEST", evidence_type="Customer PO")["ok"], 0)

    def test_stale_submitted_quotation_is_audited_and_blocks_sales_order(self):
        q = make_quotation_for(self.doc)
        frappe.db.set_value("Quotation", q.name, {"docstatus": 1, "custom_dcs_revision_reference": self.doc.custom_revision_reference})
        self.revise(new_total_cost=1100)
        q.reload()
        self.assertEqual(q.custom_dcs_superseded_revision, self.doc.custom_revision_reference)
        self.assertEqual(q.total, 1500)
        order = frappe.get_doc({"doctype":"Sales Order", "items":[{"prevdoc_docname": q.name}]})
        with self.assertRaises(frappe.ValidationError):
            validate_sales_order(order)
        event = frappe.get_doc("DCS Governance Event", frappe.db.get_value("DCS Governance Event",
            {"dcs":self.doc.name,"event_code":"DCS_REVISION_APPLIED"}, "name"))
        self.assertTrue(any(c["fieldname"] == "custom_dcs_superseded_revision" for c in json.loads(event.changes)))

    def test_legacy_unstamped_quotation_selling_and_scope_are_checked(self):
        q = make_quotation_for(self.doc)
        validate_position(self.doc, q)
        q.items[0].qty = 2
        with self.assertRaises(frappe.ValidationError):
            validate_position(self.doc, q)
        q.reload()
        self.revise(new_total_selling=1400)
        with self.assertRaises(frappe.ValidationError):
            validate_position(self.doc, q)

    def test_sales_order_blocks_unapproved_current_margin(self):
        self.revise(new_total_cost=1250)
        q = make_quotation_for(self.doc)
        order = frappe.get_doc({"doctype":"Sales Order", "items":[{"prevdoc_docname":q.name}]})
        with self.assertRaises(frappe.ValidationError):
            validate_sales_order(order)
        approved = self.decide( action="Approve", reason="ZZTEST exception")
        self.assertEqual(approved["ok"], 1, approved)
        validate_sales_order(order)

    def test_additional_buying_and_selling_reconcile(self):
        from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import calculate_deal_financials
        d = make_dcs(suffix=frappe.generate_hash(length=8), addtional_charges=[{"amount":100,"selling_amount":150}])
        calculate_deal_financials(d)
        self.assertEqual(d.total_cost,1100)
        self.assertEqual(d.total_selling,1650)
        self.assertAlmostEqual(d.margin_percent,100/3)
        d.addtional_charges[0].selling_amount = 0
        calculate_deal_financials(d)
        self.assertEqual(d.total_selling,1500)

    def test_award_maps_won_and_opportunity_without_releasing_delivery(self):
        r = self.award()
        self.assertEqual(r["ok"],1,r)
        self.doc.reload()
        self.assertEqual(self.doc.custom_deal_status,"Won")
        self.assertEqual(frappe.db.get_value("Opportunity",self.doc.opportunity,"status"),"Converted")
        self.assertEqual(frappe.db.get_value("Opportunity",self.doc.opportunity,"custom_quotation_outcome"),"Won")
        self.assertEqual(self.doc.custom_delivery_release_state,"Blocked")

    def test_command_center_legacy_mapping_and_technical_projection(self):
        self.assertEqual(frappe.get_hooks("override_whitelisted_methods")["dcs_screen1"][-1],
                         "bsgroup.api.dcs.command_center.dcs_screen1")
        frappe.set_user(self.md)
        r = frappe.call("bsgroup.api.dcs.command_center.dcs_screen1")
        self.assertEqual(r["projection"],"commercial",r)
        frappe.set_user(self.tech)
        r = frappe.call("bsgroup.api.dcs.command_center.dcs_screen1")
        self.assertEqual(r["projection"],"technical",r)
        self.assertNotIn("portfolio",r)
        self.assertNotIn("browse",r)

    def test_mapper_refuses_stale_source_before_core_mapping(self):
        from bsgroup.dcs.quotation_control import make_sales_order
        q = make_quotation_for(self.doc)
        self.revise(new_total_selling=1400)
        with patch("erpnext.selling.doctype.quotation.quotation.make_sales_order") as mapper:
            with self.assertRaises(frappe.ValidationError):
                make_sales_order(q.name)
            mapper.assert_not_called()

    def test_margin_bridge_reconciles_original_current_and_rejected_history(self):
        self.revise(new_total_cost=1250)
        self.reject()
        self.revise(new_total_cost=1200)
        p = frappe.call("bsgroup.api.dcs.living.dcs_screen2", dcs=self.doc.name)
        self.assertEqual(p["ok"],1,p)
        bridge = p["margin_bridge"]
        self.assertEqual(bridge["original"]["gp"],500)
        self.assertEqual(bridge["current"]["gp"],300)
        self.assertEqual(bridge["gp_impacts"]["vendor"],-200)
        self.assertEqual(bridge["unreconciled_gp"],0)
        self.assertEqual(bridge["approval_required"],"None")

    def test_boq_below_floor_then_rejected_revision_recovers_without_manager(self):
        from bsgroup.api.dcs.test_dcs_boq_revision import payload
        def apply(cost):
            self.doc.reload()
            values = payload(self.doc)
            values["items"][0]["cost_rate"] = cost
            frappe.set_user(self.presales)
            result = frappe.call("bsgroup.api.dcs.boq_revision.dcs_apply_boq_revision", dcs=self.doc.name,
                expected_modified=str(self.doc.modified), source="Vendor", reason="ZZTEST BOQ margin", **values)
            self.assertEqual(result["ok"],1,result)
            self.doc.reload()
        apply(1250)
        self.assertEqual(self.doc.custom_approval_required,"Manager")
        old = self.reject()
        apply(1200)
        self.assertEqual(self.doc.custom_approval_required,"None")
        self.assertEqual(frappe.db.get_value("DCS Revision",old,"approval_state"),"Rejected")
        self.assertEqual(self.award()["ok"],1)

    def test_quotation_from_charges_matches_dcs_selling_total(self):
        from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation
        d = make_dcs(suffix=frappe.generate_hash(length=8), submit=True,
                     addtional_charges=[{"amount":100,"selling_amount":150}])
        frappe.db.set_single_value("BS Group Settings", "dcs_addtional_item",d.items[0].item_code)
        # This test isolates selling reconciliation; site Account permission is separate.
        frappe.set_user("Administrator")
        name = make_quotation(d.name, payment_terms="ZZTEST 100% on delivery")
        q = frappe.get_doc("Quotation",name)
        self.assertEqual(q.total,d.total_selling)
        self.assertEqual(q.total,1650)
        self.assertEqual(q.custom_dcs_revision_reference,d.custom_revision_reference)
        validate_position(d,q)

    def test_submitted_quotation_lineage_cannot_be_cleared_by_form_save(self):
        from bsgroup.dcs.quotation_control import guard_lineage
        q = make_quotation_for(self.doc)
        previous = frappe.get_doc(q.as_dict())
        q.custom_dcs_superseded_revision = "ZZTEST-forged-lineage"
        with patch.object(q, "get_doc_before_save", return_value=previous):
            with self.assertRaises(frappe.ValidationError):
                guard_lineage(q)

    def test_award_reversal_reopens_outcome_and_retains_frozen_history(self):
        self.assertEqual(self.award()["ok"],1)
        r = frappe.call("bsgroup.api.dcs.award.dcs_award_reversal", dcs=self.doc.name,
            reason="ZZTEST customer withdrew award", acknowledge="YES", mode="reverse")
        self.assertEqual(r["ok"],1,r)
        self.doc.reload()
        self.assertEqual(self.doc.custom_deal_status,"Submitted to Sales")
        self.assertEqual(self.doc.custom_baseline_frozen,1)
        self.assertEqual(self.doc.custom_award_state,"Not Awarded")
        self.assertEqual(frappe.db.get_value("Opportunity",self.doc.opportunity,"status"),"Open")
        self.assertFalse(frappe.db.get_value("Opportunity",self.doc.opportunity,"custom_quotation_outcome"))

    def test_award_maps_linked_presales_and_canonical_projection(self):
        from frappe.utils import nowdate
        d = make_dcs(suffix=frappe.generate_hash(length=8))
        request = frappe.get_doc({"doctype":"Presales Request", "opportunity":d.opportunity,
            "subject":"ZZTEST award projection", "status":"Open", "request_date":nowdate()})
        request.flags.ignore_links = True
        request.insert(ignore_permissions=True,ignore_mandatory=True)
        request.submit()
        d.presales_request = request.name
        d.flags.ignore_mandatory = True
        d.save(ignore_permissions=True)
        d.submit()
        self.doc = d
        r = self.award()
        self.assertEqual(r["ok"],1,r)
        request.reload()
        self.doc.reload()
        self.assertEqual(request.status,"Won")
        self.assertEqual(request.custom_deal_status,"Won")
        self.assertEqual(self.doc.custom_presales_status,"Won")

    def test_below_floor_is_not_authorised_by_percentage_rounding(self):
        d = make_dcs(suffix=frappe.generate_hash(length=8))
        d.items[0].cost_rate = 800000.01
        d.items[0].selling_rate = 1000000
        d.save(ignore_permissions=True)
        d.submit()
        d.reload()
        self.assertEqual(d.custom_approval_required,"Manager")
        self.doc = d
        self.assertEqual(self.award()["ok"],0)
        self.assertFalse(authorised_position(d))
