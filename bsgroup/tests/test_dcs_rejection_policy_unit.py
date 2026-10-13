"""Standalone policy tests with a mocked Frappe boundary, not bench integration.

Run: python -m unittest discover -s bsgroup/tests -p test_dcs_rejection_policy_unit.py -v
"""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


class Row(dict):
    def __getattr__(self, key):
        return self.get(key)


class RejectionPolicyUnitTest(unittest.TestCase):
    def setUp(self):
        self.frappe = types.ModuleType("frappe")
        self.frappe.db = Mock()
        self.frappe.get_all = Mock(side_effect=self.decisions)
        self.frappe.whitelist = lambda **kw: lambda f: f
        self.frappe.throw = Mock(side_effect=lambda message, **kw: (_ for _ in ()).throw(ValueError(message)))
        utils = types.ModuleType("frappe.utils")
        utils.flt = lambda value, precision=None: round(float(value or 0), precision) if precision is not None else float(value or 0)
        utils.now_datetime = Mock()
        common = types.ModuleType("bsgroup.api.dcs._common")
        for key in ("CUSTOMER_SIDE", "VENDOR_SIDE", "TECHNICAL_ROLES"):
            setattr(common, key, [])
        common.CEILING, common.MD_THRESHOLD, common.MARGIN_FLOOR = 26, 16, 20
        common.COMMERCIAL_ROLES, common.MD = [], "Managing Director"
        common.governed_endpoint = lambda *a, **kw: lambda f: f
        for key in ("audit_event", "dcs_exists_and_open", "diff_changes", "emit_timeline", "get_user_roles", "has_any", "matched", "snapshot", "absf", "clear_auto", "next_condition_no", "nrc_entry_check", "open_blockers", "raise_condition"):
            setattr(common, key, Mock())
        manager = types.ModuleType("bsgroup.dcs.manager_approval")
        manager.route_for = Mock(return_value=Row(approval_policy="Immediate Manager", approval_manager="manager", changed_by="sales"))
        self.manager = manager
        self.common = common
        self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.utils": utils,
            "bsgroup.api.dcs._common": common, "bsgroup.dcs.manager_approval": manager})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.history = []
        self.review = self.load("bsgroup.dcs.rejection_review", "bsgroup/dcs/rejection_review.py")
        self.negotiation = self.load("bsgroup.api.dcs.negotiation", "bsgroup/api/dcs/negotiation.py")
        self.authority = self.load("bsgroup.dcs.commercial_authority", "bsgroup/dcs/commercial_authority.py")
        self.quotes = self.load("bsgroup.dcs.quotation_control", "bsgroup/dcs/quotation_control.py")
        self.award = self.load("bsgroup.api.dcs.award", "bsgroup/api/dcs/award.py")
        self.sheet = Row(name="DCS", custom_dcs_revision_no=4,
            custom_working_total_cost=1000, custom_working_total_selling=1500,
            custom_baseline_selling=1500, custom_approval_required="None",
            custom_approval_state="In Negotiation", custom_revision_reference="R4")

    def load(self, name, path):
        spec = importlib.util.spec_from_file_location(name, ROOT / path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def decisions(self, doctype, filters, **kwargs):
        self.assertEqual(doctype, "DCS Revision")
        self.assertEqual(filters["dcs"], "DCS")
        cutoff = filters["revision_no"][1]
        rows = [r for r in self.history if r.revision_no < cutoff and r.approval_state in filters["approval_state"][1]]
        return sorted(rows, key=lambda r: r.revision_no, reverse=True)[:1]

    def test_recovered_margin_and_price_still_require_manager(self):
        for margin in (20, 25, 40):
            with self.subTest(margin=margin):
                self.assertEqual(self.negotiation.requirement(0, margin, True), "Manager")
                self.assertIn("rejected", self.negotiation.why_approval(0, margin, True))

    def test_ceiling_stays_blocked_even_after_rejection(self):
        self.assertEqual(self.negotiation.requirement(27, 40, True), "Blocked")

    def test_no_rejection_preserves_normal_thresholds(self):
        self.assertEqual(self.negotiation.requirement(0, 20), "None")
        self.assertEqual(self.negotiation.requirement(16, 30), "Manager")
        self.assertEqual(self.negotiation.requirement(0, 19.999), "Manager")
        self.assertFalse(self.review.requires_fresh_approval(self.sheet))

    def test_pending_revisions_cannot_wash_away_rejection(self):
        self.history = [Row(revision_no=2, approval_state="Rejected"),
                        Row(revision_no=3, approval_state="Not Required"),
                        Row(revision_no=4, approval_state="Pending Manager")]
        self.assertTrue(self.review.requires_fresh_approval(self.sheet))
        self.assertFalse(self.authority.authorised_position(self.sheet))

    def test_earlier_approval_cannot_clear_later_rejection(self):
        self.history = [Row(revision_no=1, approval_state="Approved"), Row(revision_no=2, approval_state="Rejected")]
        self.sheet.update(custom_approval_state="Approved", custom_approved_revision_no=1)
        self.assertFalse(self.authority.authorised_position(self.sheet))

    def approve_current(self):
        self.history = [Row(revision_no=2, approval_state="Rejected"), Row(revision_no=4, approval_state="Approved")]
        self.sheet.update(custom_approval_state="Approved", custom_approved_revision_no=4,
            custom_approved_by="manager", custom_approved_total_cost=1000, custom_approved_total_selling=1500)
        self.frappe.db.get_value.side_effect = lambda dt, *a, **kw: (1 if dt == "User" else Row(dcs="DCS", approval_state="Approved", decided_by="manager"))

    def test_current_approval_must_pass_manager_and_amount_checks(self):
        self.approve_current()
        self.assertTrue(self.authority.authorised_position(self.sheet))
        self.sheet.custom_approved_total_selling = 1499
        self.assertFalse(self.authority.authorised_position(self.sheet))

    def test_missing_or_unrelated_manager_cannot_authorise_recovery(self):
        self.approve_current()
        for route in (Row(), Row(approval_policy="Immediate Manager", approval_manager="other", changed_by="sales"),
                      Row(approval_policy="Immediate Manager", approval_manager="manager", changed_by="manager")):
            with self.subTest(route=route):
                self.manager.route_for.return_value = route
                self.assertFalse(self.authority.authorised_position(self.sheet))

    def test_disabled_manager_cannot_authorise_recovery(self):
        self.approve_current()
        self.frappe.db.get_value.side_effect = lambda dt, *a, **kw: (0 if dt == "User" else Row(dcs="DCS", approval_state="Approved", decided_by="manager"))
        self.assertFalse(self.authority.authorised_position(self.sheet))

    def test_later_approval_closes_cycle_for_subsequent_revision(self):
        self.history = [Row(revision_no=2, approval_state="Rejected"), Row(revision_no=3, approval_state="Approved")]
        self.assertFalse(self.review.requires_fresh_approval(self.sheet))
        self.assertTrue(self.authority.authorised_position(self.sheet))

    def test_quotation_submission_blocks_recovery_with_cleared_header(self):
        identity = types.ModuleType("bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet")
        identity.quotation_deal_identity = Mock(return_value=False)
        sys.modules[identity.__name__] = identity
        self.history = [Row(revision_no=2, approval_state="Rejected")]
        self.sheet.docstatus = 1
        with self.assertRaisesRegex(ValueError, "fresh assigned manager"):
            self.quotes.validate_position(self.sheet, Row(docstatus=1))

    def test_sales_order_conversion_and_validation_block_recovery(self):
        self.history = [Row(revision_no=2, approval_state="Rejected")]
        quote = Row(name="Q", custom_deal_cost_sheet="DCS", check_permission=Mock())
        self.frappe.get_doc = Mock(side_effect=[quote, self.sheet, quote, self.sheet])
        with patch.object(self.quotes, "validate_position"):
            with self.assertRaisesRegex(ValueError, "assigned manager"):
                self.quotes.make_sales_order("Q")
            with self.assertRaisesRegex(ValueError, "assigned manager"):
                self.quotes.validate_sales_order(types.SimpleNamespace(docstatus=0, items=[Row(prevdoc_docname="Q")], get_doc_before_save=lambda: None))

    def test_quotation_cannot_drop_dcs_link_to_skip_validation(self):
        doc = Row(docstatus=0, custom_deal_cost_sheet="", get_doc_before_save=lambda: Row(custom_deal_cost_sheet="DCS"))
        with self.assertRaisesRegex(ValueError, "lineage cannot be removed"):
            self.quotes.validate_quotation(doc)

    def test_sales_order_cannot_drop_linked_quotation_to_skip_validation(self):
        previous = types.SimpleNamespace(items=[Row(prevdoc_docname="Q")])
        doc = types.SimpleNamespace(docstatus=0, items=[], get_doc_before_save=lambda: previous)
        self.frappe.db.get_value.return_value = "DCS"
        with self.assertRaisesRegex(ValueError, "lineage cannot be removed"):
            self.quotes.validate_sales_order(doc)

    def test_award_endpoint_blocks_recovery_with_cleared_header(self):
        self.history = [Row(revision_no=2, approval_state="Rejected")]
        self.common.nrc_entry_check.return_value = {"block":"", "warn":"", "delegated":0}
        self.common.dcs_exists_and_open.return_value = True
        self.common.has_any.return_value = 1
        self.sheet.check_permission = Mock()
        self.frappe.get_doc = Mock(return_value=self.sheet)
        baseline = types.ModuleType("bsgroup.dcs.baseline")
        baseline.ensure_baseline = Mock()
        sys.modules[baseline.__name__] = baseline
        result = self.award.dcs_record_award({"dcs":"DCS", "evidence_type":"Customer PO"})
        self.assertEqual(result["ok"], 0)
        self.assertIn("manager approval", result["error"])
        self.frappe.db.set_value.assert_not_called()
        self.common.audit_event.assert_not_called()


if __name__ == "__main__":
    unittest.main()
