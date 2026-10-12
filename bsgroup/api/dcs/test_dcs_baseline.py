"""Baseline lifecycle tests; run on isolated staging only."""
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.dcs.baseline import ensure_baseline
from bsgroup.tests.dcs_fixtures import ensure, make_dcs, make_user

AWARD = "bsgroup.api.dcs.award.dcs_record_award"
REVISE = "bsgroup.api.dcs.negotiation.dcs_apply_revision"


class IntegrationTestDCSBaseline(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()
        for role in ["Sales Manager", "Commercial Controller", "Managing Director", "Technical Engineer"]:
            ensure("Role", role, {"role_name": role}, insert=False)
        cls.md = make_user("zztest-baseline-md@example.com", ["System Manager", "Managing Director", "Sales Manager"])
        cls.tech = make_user("zztest-baseline-tech@example.com", ["Technical Engineer"])

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def sheet(self, legacy=False, **extra):
        if legacy:
            with patch("bsgroup.dcs.baseline.ensure_baseline", return_value={"initialised": 0}):
                return make_dcs(suffix=frappe.generate_hash(length=8), submit=True, **extra)
        return make_dcs(suffix=frappe.generate_hash(length=8), submit=True, **extra)

    def award(self, doc):
        frappe.set_user(self.md)
        return frappe.call(AWARD, dcs=doc.name, award_reference="ZZTEST-BASELINE-PO", evidence_type="Customer PO")

    def test_submit_initialises_baseline_without_negotiation(self):
        doc = self.sheet()
        self.assertEqual(doc.custom_dcs_revision_no, 1)
        self.assertEqual(doc.custom_working_total_cost, 1000)
        self.assertEqual(doc.custom_working_total_selling, 1500)
        rev = frappe.get_doc("DCS Revision", doc.custom_revision_reference)
        self.assertEqual(rev.source, "Internal")
        self.assertEqual(rev.gp_movement, 0)
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": doc.name, "event_code": "DCS_BASELINE_INITIALISED"}), 1)
        self.assertEqual(self.award(doc)["ok"], 1)

    def test_existing_revision_zero_awards_without_dummy_revision(self):
        doc = self.sheet(legacy=True)
        self.assertEqual(doc.custom_dcs_revision_no or 0, 0)
        result = self.award(doc)
        self.assertEqual(result["ok"], 1, result)
        doc.reload()
        self.assertEqual(doc.custom_frozen_total_cost, 1000)
        self.assertEqual(doc.custom_frozen_total_selling, 1500)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": doc.name, "event_code": "DCS_BASELINE_INITIALISED"}), 1)
        again = self.award(doc)
        self.assertEqual(again.get("idempotent_replay"), 1)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)

    def test_baseline_is_idempotent_and_preserves_negotiated_position(self):
        doc = self.sheet()
        frappe.set_user(self.md)
        result = frappe.call(REVISE, dcs=doc.name, source="Vendor", reason="ZZTEST cost update", new_total_cost=1100)
        self.assertEqual(result["ok"], 1, result)
        before = frappe.db.get_value("Deal Cost Sheet", doc.name, ["custom_dcs_revision_no", "custom_working_total_cost"], as_dict=True)
        self.assertEqual(ensure_baseline(doc.name, "test")["initialised"], 0)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", doc.name, list(before), as_dict=True), before)

    def test_unauthorised_award_cannot_initialise(self):
        doc = self.sheet(legacy=True)
        frappe.set_user(self.tech)
        result = frappe.call(AWARD, dcs=doc.name, award_reference="ZZTEST", evidence_type="Customer PO")
        self.assertEqual(result["ok"], 0)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 0)

    def test_baseline_does_not_clear_existing_approval_block(self):
        doc = self.sheet(legacy=True)
        frappe.db.set_value("Deal Cost Sheet", doc.name, "custom_approval_required", "Blocked")
        with self.assertRaises(frappe.ValidationError):
            self.award(doc)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 0)

    def test_invalid_selling_cannot_be_awarded(self):
        doc = self.sheet(items=[{"item_code": frappe.db.get_value("Item", {"disabled": 0}, "name"), "qty": 1, "cost_rate": 1000, "selling_rate": 0}])
        self.assertEqual(doc.custom_dcs_revision_no or 0, 0)
        with self.assertRaises(frappe.ValidationError):
            self.award(doc)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 0)

    def test_low_margin_remains_delivery_blocker(self):
        doc = self.sheet(items=[{"item_code": frappe.db.get_value("Item", {"disabled": 0}, "name"), "qty": 1, "cost_rate": 2093, "selling_rate": 2500}])
        self.assertEqual(doc.custom_margin_gate, "Blocked")
        result = self.award(doc)
        self.assertEqual(result["ok"], 1, result)
        self.assertEqual(result["state"]["delivery_release_state"], "Blocked")
        self.assertTrue(frappe.db.exists("DCS Handover Condition", {"dcs": doc.name, "source_key": "margin_gate", "state": "Open"}))

    def test_conflicting_unrecorded_totals_are_not_overwritten(self):
        doc = self.sheet(legacy=True)
        frappe.db.set_value("Deal Cost Sheet", doc.name, "custom_working_total_cost", 1200)
        with self.assertRaises(frappe.ValidationError):
            self.award(doc)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", doc.name, "custom_working_total_cost"), 1200)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 0)

    def test_amendment_starts_its_own_baseline(self):
        doc = self.sheet()
        frappe.set_user(self.md)
        result = frappe.call(REVISE, dcs=doc.name, source="Vendor", reason="ZZTEST before amendment", new_total_cost=1100)
        self.assertEqual(result["ok"], 1, result)
        frappe.set_user("Administrator")
        doc.reload()
        doc.cancel()
        amendment = frappe.copy_doc(doc)
        amendment.amended_from = doc.name
        amendment.docstatus = 0
        amendment.items[0].cost_rate = 1150
        amendment.insert(ignore_permissions=True)
        self.assertEqual(amendment.custom_dcs_revision_no or 0, 0)
        amendment.submit()
        self.assertEqual(amendment.custom_working_total_cost, 1150)
        self.assertEqual(amendment.custom_dcs_revision_no, 1)
        self.assertEqual(amendment.custom_revision_reference, amendment.name + "-R1")
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", doc.name, "custom_working_total_cost"), 1100)

    def test_initialisation_only_request_does_not_manufacture_revisions(self):
        doc = self.sheet(legacy=True)
        frappe.set_user(self.md)
        args = {"dcs": doc.name, "source": "Customer", "reason": "ZZTEST baseline only", "new_total_selling": 1500}
        first = frappe.call(REVISE, **args)
        self.assertEqual(first["initialised"], 1)
        second = frappe.call(REVISE, **args)
        self.assertEqual(second.get("no_change"), 1)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": doc.name}), 1)

    def test_competing_award_rolls_back_and_returns_structured_refusal(self):
        doc = self.sheet(legacy=True)
        with patch("bsgroup.dcs.baseline.ensure_baseline", side_effect=frappe.QueryDeadlockError("competing write")), patch.object(frappe.db, "rollback") as rollback:
            result = self.award(doc)
        self.assertEqual(result["ok"], 0)
        self.assertEqual(result["retry_required"], 1)
        rollback.assert_called_once()
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 0)
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": doc.name}), 0)
