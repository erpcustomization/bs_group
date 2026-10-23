"""BOQ lifecycle/control regressions. Run on isolated staging only."""
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.api.dcs.boq_revision import ITEM_FIELDS, RESOURCE_FIELDS
from bsgroup.tests.dcs_fixtures import ensure, make_dcs, make_user

APPLY = "bsgroup.api.dcs.boq_revision.dcs_apply_boq_revision"
AWARD = "bsgroup.api.dcs.award.dcs_record_award"


def payload(doc):
    return {
        "items": [{"row_name": r.name, **{f: r.get(f) for f in ITEM_FIELDS}} for r in doc.items],
        "resources": [{"row_name": r.name, **{f: r.get(f) for f in RESOURCE_FIELDS}} for r in doc.resources],
    }


class IntegrationTestDCSBOQRevision(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()
        for role in ["Managing Director", "Sales Manager", "Presales", "Sales User", "Technical Engineer"]:
            ensure("Role", role, {"role_name": role}, insert=False)
        cls.md = make_user("zztest-boq-md@example.com", ["System Manager", "Managing Director", "Sales Manager", "Accounts User"])
        cls.sales = make_user("zztest-boq-sales@example.com", ["System Manager", "Sales User"])
        cls.vendor = make_user("zztest-boq-vendor@example.com", ["System Manager", "Presales"])
        cls.tech = make_user("zztest-boq-tech@example.com", ["Technical Engineer"])

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def sheet(self, **values):
        return make_dcs(suffix="BOQ" + frappe.generate_hash(length=8), submit=True, **values)

    def apply(self, doc, values=None, user=None, **extra):
        doc.reload()
        frappe.set_user(user or self.md)
        args = {"dcs": doc.name, "expected_modified": str(doc.modified), "source": "Vendor",
            "reason": "ZZTEST revised supplier BOQ", **(values or payload(doc)), **extra}
        return frappe.call(APPLY, **args)

    def test_items_and_labour_change_same_submitted_sheet(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 1100
        p["resources"] = [{"resource_type": "Internal", "role": "Technician", "no_of_persons": 1,
            "no_of_days": 2, "hours": 0, "cost_rate": 100, "remarks": "ZZTEST"}]
        result = self.apply(doc, p)
        self.assertEqual(result["ok"], 1, result)
        doc.reload()
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.total_cost, 1300)
        self.assertEqual(doc.custom_working_total_cost, 1300)
        self.assertEqual(doc.total_resource_cost, 200)
        self.assertEqual(doc.custom_dcs_revision_no, 2)
        rev = frappe.get_doc("DCS Revision", result["revision"])
        self.assertEqual(len(rev.boq_lines), 2)
        self.assertEqual({r.operation for r in rev.boq_lines}, {"Update", "Add"})
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": doc.name, "event_code": "DCS_REVISION_APPLIED"}), 1)
        self.assertEqual(doc.custom_margin_gate, "Blocked")

    def test_totals_only_api_is_refused_after_boq_conversion(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 900
        self.assertEqual(self.apply(doc, p)["ok"], 1)
        result = frappe.call("bsgroup.api.dcs.negotiation.dcs_apply_revision", dcs=doc.name,
            source="Vendor", reason="ZZTEST cannot split rows and totals", new_total_cost=1200)
        self.assertEqual(result["ok"], 0)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", doc.name, "custom_working_total_cost"), 900)

    def test_add_remove_item_and_repeat_revision(self):
        doc = self.sheet()
        original = doc.items[0].name
        code = doc.items[0].item_code
        p = payload(doc)
        p["items"] = [{"item_code": code, "description": "ZZTEST replacement controller", "qty": 2,
            "cost_rate": 450, "selling_rate": 750}]
        self.assertEqual(self.apply(doc, p)["ok"], 1)
        doc.reload()
        self.assertNotEqual(doc.items[0].name, original)
        rev = frappe.get_doc("DCS Revision", doc.custom_revision_reference)
        self.assertEqual({r.operation for r in rev.boq_lines}, {"Add", "Remove"})
        p = payload(doc)
        p["items"][0]["qty"] = 3
        self.assertEqual(self.apply(doc, p)["ok"], 1)
        doc.reload()
        self.assertEqual(doc.total_cost, 1350)
        self.assertEqual(doc.total_selling, 2250)
        self.assertEqual(doc.custom_dcs_revision_no, 3)

    def test_noop_creates_no_revision(self):
        doc = self.sheet()
        self.assertEqual(self.apply(doc)["no_change"], 1)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)

    def test_rate_change_below_stored_precision_is_noop(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 1000.00000001
        self.assertEqual(self.apply(doc, p)["no_change"], 1)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)

    def test_unpriced_submitted_sheet_gets_first_priced_boq(self):
        item = frappe.db.get_value("Item", {"disabled": 0}, "name")
        doc = self.sheet(items=[{"item_code": item, "qty": 1, "cost_rate": 1000, "selling_rate": 0}])
        self.assertEqual(doc.custom_dcs_revision_no or 0, 0)
        p = payload(doc)
        p["items"][0]["selling_rate"] = 1500
        result = self.apply(doc, p)
        self.assertEqual(result["ok"], 1, result)
        doc.reload()
        self.assertEqual(doc.custom_dcs_revision_no, 1)
        self.assertEqual(doc.custom_baseline_selling, 1500)
        self.assertEqual(doc.custom_concession_percent_from_baseline, 0)
        self.assertEqual(frappe.call(AWARD, dcs=doc.name, award_reference="ZZTEST priced", evidence_type="Customer PO")["ok"], 1)

    def test_identical_request_replays_without_duplicate_lines_or_events(self):
        doc = self.sheet()
        frappe.set_user(self.md)
        p = payload(doc)
        p["items"][0]["cost_rate"] = 900
        args = {"dcs": doc.name, "expected_modified": str(doc.modified), "source": "Vendor", "reason": "ZZTEST repeat", **p}
        first = frappe.call(APPLY, **args)
        second = frappe.call(APPLY, **args)
        self.assertEqual(first["ok"], 1)
        self.assertEqual(second["idempotent_replay"], 1)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 2)
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": doc.name, "event_code": "DCS_REVISION_APPLIED"}), 1)

    def test_direct_submitted_line_edit_is_refused(self):
        doc = self.sheet()
        doc.items[0].cost_rate = 900
        doc.flags.ignore_validate_update_after_submit = True
        doc.flags.bsg_boq_revision = True  # a serialisable client flag is insufficient
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
        self.assertEqual(frappe.db.get_value("Deal Cost Item", doc.items[0].name, "cost_rate"), 1000)

    def test_stale_dialog_refused(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 1100
        doc.reload()
        stale = str(doc.modified)
        frappe.db.set_value("Deal Cost Sheet", doc.name, "deal_owner", self.md)
        with self.assertRaises(frappe.ValidationError):
            self.apply(doc, p, expected_modified=stale)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)

    def test_foreign_row_refused(self):
        doc, other = self.sheet(), self.sheet()
        p = payload(doc)
        p["items"][0]["row_name"] = other.items[0].name
        with self.assertRaises(frappe.ValidationError):
            self.apply(doc, p)

    def test_derived_and_control_fields_cannot_be_supplied(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_amount"] = 1
        with self.assertRaises(frappe.ValidationError):
            self.apply(doc, p)

    def test_invalid_numbers_refused(self):
        for value in [-1, "NaN", "Infinity"]:
            doc = self.sheet()
            p = payload(doc)
            p["items"][0]["cost_rate"] = value
            with self.assertRaises(frappe.ValidationError):
                self.apply(doc, p)

    def test_labour_cannot_double_count_days_and_hours(self):
        doc = self.sheet()
        p = payload(doc)
        p["resources"] = [{"resource_type": "Internal", "role": "ZZTEST", "no_of_persons": 1,
            "no_of_days": 2, "hours": 8, "cost_rate": 100}]
        with self.assertRaises(frappe.ValidationError):
            self.apply(doc, p)

    def test_sales_user_cannot_change_buying_fields(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 900
        with self.assertRaises(frappe.PermissionError):
            self.apply(doc, p, user=self.sales)

    def test_presales_can_change_cost_but_not_scope_or_selling(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 900
        self.assertEqual(self.apply(doc, p, user=self.vendor)["ok"], 1)
        doc.reload()
        p = payload(doc)
        p["items"][0]["selling_rate"] = 1600
        with self.assertRaises(frappe.PermissionError):
            self.apply(doc, p, user=self.vendor)

    def test_technical_role_has_no_commercial_write(self):
        doc = self.sheet()
        result = self.apply(doc, user=self.tech)
        self.assertEqual(result["ok"], 0)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)

    def test_header_adjustment_requires_explicit_md_reconciliation(self):
        doc = self.sheet()
        frappe.set_user(self.md)
        frappe.call("bsgroup.api.dcs.negotiation.dcs_apply_revision", dcs=doc.name,
            source="Vendor", reason="ZZTEST totals only", new_total_cost=1200)
        doc.reload()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 1300
        with self.assertRaises(frappe.ValidationError):
            self.apply(doc, p)
        result = self.apply(doc, p, reconcile_header_adjustments=1)
        self.assertEqual(result["ok"], 1)
        doc.reload()
        self.assertEqual(doc.total_cost, 1300)  # not 1500 (no hidden +200)
        self.assertEqual(doc.custom_working_total_cost, 1300)

    def test_awarded_scope_refused(self):
        doc = self.sheet()
        frappe.set_user(self.md)
        self.assertEqual(frappe.call(AWARD, dcs=doc.name, award_reference="ZZTEST", evidence_type="Customer PO")["ok"], 1)
        doc.reload()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 1100
        with self.assertRaises(frappe.ValidationError):
            self.apply(doc, p)

    def test_discount_rechecks_md_approval_and_ceiling(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["selling_rate"] = 1250
        self.assertEqual(self.apply(doc, p)["state"]["approval_required"], "Manager")
        doc.reload()
        p = payload(doc)
        p["items"][0]["selling_rate"] = 1000
        self.assertEqual(self.apply(doc, p)["state"]["approval_required"], "Blocked")

    def test_line_history_is_immutable(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 900
        result = self.apply(doc, p)
        rev = frappe.get_doc("DCS Revision", result["revision"])
        rev.boq_lines[0].after_values = "{}"
        with self.assertRaises(frappe.ValidationError):
            rev.save(ignore_permissions=True)

    def test_standalone_history_row_cannot_be_changed_or_deleted(self):
        doc = self.sheet()
        line = frappe.get_doc("DCS Revision", doc.custom_revision_reference).boq_lines[0]
        standalone = frappe.get_doc("DCS Revision Line", line.name)
        standalone.after_values = "{}"
        with self.assertRaises(frappe.ValidationError):
            standalone.save(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("DCS Revision Line", line.name, ignore_permissions=True)
        self.assertTrue(frappe.db.exists("DCS Revision Line", line.name))

    def test_late_refusal_rolls_back_even_for_in_process_caller(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 900
        with patch("bsgroup.api.dcs.boq_revision._sync_quotation", side_effect=frappe.ValidationError("ZZTEST late refusal")):
            with self.assertRaises(frappe.ValidationError):
                self.apply(doc, p)
        self.assertEqual(frappe.db.get_value("Deal Cost Item", doc.items[0].name, "cost_rate"), 1000)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", doc.name, "custom_working_total_cost"), 1000)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)
        self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": doc.name, "event_code": "DCS_REVISION_APPLIED"}), 0)

    def test_revised_boq_quotation_award_po_and_delivery_lifecycle(self):
        from bsgroup.api.dcs.test_dcs_vendor_revision import quotation_values
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        doc = self.sheet(company=company)
        q = frappe.get_doc(quotation_values(doc, 1500))
        q.insert()  # mandatory fields, taxes and the retained link-back run normally
        doc.reload()
        self.assertEqual(doc.custom_quotation, q.name)
        code = doc.items[0].item_code
        p = payload(doc)
        p["items"] = [
            {"row_name": doc.items[0].name, "item_code": code, "description": "ZZTEST controller", "qty": 1, "cost_rate": 685, "selling_rate": 2000},
            {"item_code": code, "description": "ZZTEST readers", "qty": 2, "cost_rate": 154, "selling_rate": 350},
            {"item_code": code, "description": "ZZTEST cable accessories", "qty": 1, "cost_rate": 300, "selling_rate": 300},
        ]
        p["resources"] = [
            {"resource_type": "Internal", "role": "Technician", "no_of_persons": 1, "no_of_days": 2, "hours": 0, "cost_rate": 270},
            {"resource_type": "Outsourced", "role": "Labour", "no_of_persons": 1, "no_of_days": 2, "hours": 0, "cost_rate": 130},
        ]
        result = self.apply(doc, p, update_quotation=1)
        self.assertEqual(result["ok"], 1, result)
        doc.reload()
        q.reload()
        self.assertEqual(doc.total_cost, 2093)
        self.assertEqual(doc.total_selling, 3000)
        self.assertEqual(q.total, 3000)
        self.assertEqual(len(q.items), 3)
        self.assertEqual(q.custom_deal_cost_sheet, doc.name)
        # The synced quotation is still a draft: prepared, not issued.
        self.assertEqual(doc.custom_deal_status, "Submitted to Sales")
        self.assertEqual([r.custom_dcs_source_rows for r in q.items], [r.get("source_key") or r.name for r in doc.items])
        self.assertEqual(frappe.call(AWARD, dcs=doc.name, award_reference="ZZTEST-BOQ-PO", evidence_type="Customer PO")["ok"], 1)
        reconciliation = frappe.call("bsgroup.api.dcs.award.dcs_po_reconcile", dcs=doc.name,
            po_reference="ZZTEST-BOQ-PO", po_value=3000, po_scope_revision=result["revision"],
            po_payment_terms="Net 30", payment_terms_accepted=1)
        self.assertEqual(reconciliation["ok"], 1, reconciliation)
        self.assertEqual(frappe.call("bsgroup.api.dcs.handover.dcs_set_delivery_owner", dcs=doc.name, delivery_owner=self.tech)["ok"], 1)
        technical = frappe.db.get_value("DCS Handover Condition", {"dcs": doc.name, "source_key": "technical_readiness"}, "name")
        frappe.set_user(self.tech)
        clear = frappe.call("bsgroup.api.dcs.handover.dcs_handover_action", condition=technical,
            action="Clear", note="ZZTEST revised scope and site readiness confirmed")
        self.assertEqual(clear["ok"], 1, clear)
        frappe.set_user(self.md)
        release = frappe.call("bsgroup.api.dcs.handover.dcs_delivery_release", dcs=doc.name)
        self.assertEqual(release["ok"], 1, release)
        doc.reload()
        self.assertEqual(doc.custom_frozen_total_cost, 2093)
        self.assertEqual(doc.custom_frozen_total_selling, 3000)

    def test_saving_submitted_quotation_is_never_automatic(self):
        from bsgroup.api.dcs.test_dcs_vendor_revision import quotation_values
        doc = self.sheet(company=frappe.db.get_single_value("Global Defaults", "default_company"))
        q = frappe.get_doc(quotation_values(doc, 1500)).insert()
        q.submit()
        doc.reload()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 900
        with self.assertRaises(frappe.ValidationError):
            self.apply(doc, p, update_quotation=1)
        self.assertEqual(frappe.db.get_value("Deal Cost Item", doc.items[0].name, "cost_rate"), 1000)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": doc.name}), 1)

    def test_quoted_scope_change_needs_sync_or_explicit_review(self):
        from bsgroup.api.dcs.test_dcs_vendor_revision import quotation_values
        doc = self.sheet(company=frappe.db.get_single_value("Global Defaults", "default_company"))
        q = frappe.get_doc(quotation_values(doc, 1500)).insert()
        doc.reload()
        p = payload(doc)
        p["items"][0]["qty"] = 2
        with self.assertRaises(frappe.ValidationError):
            self.apply(doc, p)
        self.assertEqual(self.apply(doc, p, acknowledge_quote_review=1)["ok"], 1)
        q.reload()
        doc.reload()
        self.assertEqual(q.total, 1500)
        self.assertEqual(doc.total_selling, 3000)
        self.assertEqual(doc.custom_deal_status, "Submitted to Sales")

    def test_amendment_baseline_does_not_reapply_line_movement(self):
        doc = self.sheet()
        p = payload(doc)
        p["items"][0]["cost_rate"] = 1795
        revised = self.apply(doc, p)
        frappe.set_user("Administrator")
        doc.reload()
        doc.cancel()
        amendment = frappe.copy_doc(doc)
        amendment.amended_from, amendment.docstatus = doc.name, 0
        amendment.insert(ignore_permissions=True)
        amendment.submit()
        self.assertEqual(amendment.total_cost, 1795)
        self.assertEqual(amendment.custom_working_total_cost, 1795)
        self.assertEqual(amendment.custom_dcs_revision_no, 1)
        self.assertEqual(frappe.db.get_value("DCS Revision", revised["revision"], "settled_by"), amendment.name)
        self.assertEqual(json.loads(frappe.get_doc("DCS Revision", revised["revision"]).boq_lines[0].after_values)["cost_rate"], 1795)
        self.assertEqual(self.apply(amendment)["no_change"], 1)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": amendment.name}), 1)
        result = frappe.call("bsgroup.api.dcs.negotiation.dcs_apply_revision", dcs=amendment.name,
            source="Vendor", reason="ZZTEST inherited BOQ mode", new_total_cost=2590)
        self.assertEqual(result["ok"], 0)
