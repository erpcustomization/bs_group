# Copyright (c) 2026, Tridots Tech and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.tests.dcs_fixtures import make_dcs, make_opportunity


class IntegrationTestDealCostSheet(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()

    def make_submitted_dcs(self):
        return make_dcs(suffix=frappe.generate_hash(length=6), submit=True)

    def test_submitted_dcs_allows_only_governed_updates(self):
        allowed_fields = {
            field.fieldname
            for field in frappe.get_meta("Deal Cost Sheet").fields
            if field.allow_on_submit
        }
        # Only governed fields may be editable after submit. `workflow_state` exists
        # only when a Workflow is attached to the DocType - deployment state, not
        # release state - so assert containment: the regression this guards is an
        # UNGOVERNED field becoming editable on a submitted sheet.
        self.assertTrue(allowed_fields <= {"deal_owner", "workflow_state"}, allowed_fields)
        self.assertIn("deal_owner", allowed_fields)

        doc = self.make_submitted_dcs()
        doc.deal_owner = "Guest"
        doc.save()

        self.assertEqual(
            frappe.db.get_value("Deal Cost Sheet", doc.name, "deal_owner"),
            "Guest",
        )

        doc.subject = "ZZ-QA-Submitted DCS Must Stay Locked"
        with self.assertRaises(frappe.ValidationError):
            doc.save()

    # --- party model / D3 -------------------------------------------------------
    def test_customer_is_a_link_derived_from_the_party(self):
        df = frappe.get_meta("Deal Cost Sheet").get_field("customer")
        self.assertEqual(df.fieldtype, "Link")
        self.assertEqual(df.options, "Customer")
        self.assertFalse(df.reqd)
        dcs = make_dcs("Customer", suffix=frappe.generate_hash(length=6))
        self.assertEqual(dcs.customer, dcs.party)
        # Named by the documented rule DCS-<slug(organisation_name)>-###; slug() strips
        # non-alphanumerics, so a fixture called "ZZTEST-Customer-<suffix>" loses its
        # own hyphens (the same rule that names "Abela & Co" as DCS-Abela-Co-001).
        from bsgroup.utils.party import slug

        self.assertTrue(dcs.name.startswith(f"DCS-{slug(dcs.organisation_name)}-"), dcs.name)
        lead_dcs = make_dcs("Lead", suffix=frappe.generate_hash(length=6))
        self.assertFalse(lead_dcs.customer)
        self.assertTrue(lead_dcs.name.startswith(f"DCS-{slug(lead_dcs.organisation_name)}-"), lead_dcs.name)

    def test_project_requires_a_customer_record(self):
        lead_dcs = make_dcs("Lead", suffix=frappe.generate_hash(length=6))
        project = frappe.db.get_value("Project", {}, "name")
        if not project:
            self.skipTest("no Project on this site")
        lead_dcs.project = project
        lead_dcs.flags.ignore_links = True
        with self.assertRaises(frappe.ValidationError):
            lead_dcs.save(ignore_permissions=True)

    # --- A-3: controls are always on --------------------------------------------
    def test_settings_gates_are_gone(self):
        meta = frappe.get_meta("BS Group Settings")
        for f in ("enable_dcs_one_active_guard", "enable_dcs_governed_field_guard", "enable_dcs_record_authority_guard"):
            self.assertFalse(meta.has_field(f), f)

    def test_one_active_sheet_per_opportunity_is_enforced_without_a_flag(self):
        first = make_dcs("Customer", suffix=frappe.generate_hash(length=6))
        second = frappe.get_doc({
            "doctype": "Deal Cost Sheet", "opportunity": first.opportunity, "party_type": first.party_type,
            "party": first.party, "subject": "ZZTEST dup", "deal_owner": "Administrator",
            "items": [{"item_code": first.items[0].item_code, "qty": 1, "cost_rate": 1, "selling_rate": 2}],
        })
        second.flags.ignore_links = True
        with self.assertRaises(frappe.ValidationError):
            second.insert(ignore_permissions=True, ignore_mandatory=True)

    def test_direct_edit_of_a_governed_field_is_refused_without_a_flag(self):
        dcs = make_dcs("Customer", suffix=frappe.generate_hash(length=6))
        dcs.custom_award_state = "Awarded"
        dcs.flags.ignore_links = True
        with self.assertRaises(frappe.ValidationError):
            dcs.save(ignore_permissions=True)

    def test_record_authority_change_is_audited_through_the_single_writer(self):
        opp = make_opportunity("Customer", suffix=frappe.generate_hash(length=6))
        a = make_dcs("Customer", suffix=frappe.generate_hash(length=6), opportunity=opp.name)
        # a second sheet in the same lineage is refused by the one-active guard, so
        # supersede against a sheet on another opportunity is refused too; test the
        # audit path on a Current -> Undetermined move, which needs no target.
        a.custom_record_authority = "Undetermined"
        a.flags.ignore_links = True
        a.save(ignore_permissions=True)
        ev = frappe.get_all(
            "DCS Governance Event", {"dcs": a.name, "event_code": "RECORD_AUTHORITY_SET"},
            ["name", "actor", "correlation_id", "source_event_id", "changes"],
        )
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0].actor, frappe.session.user)
        self.assertFalse(str(ev[0].correlation_id).startswith("AUTH-"))
        self.assertIn("custom_record_authority", ev[0].changes)

    def test_presales_sync_event_has_old_and_new_values(self):
        from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import dcs_presales_sync
        pr_name = frappe.db.get_value("Presales Request", {"docstatus": ["<", 2]}, "name")
        if not pr_name:
            self.skipTest("no Presales Request on this site")
        dcs = make_dcs("Customer", suffix=frappe.generate_hash(length=6))
        frappe.db.set_value("Deal Cost Sheet", dcs.name, "presales_request", pr_name, update_modified=False)
        frappe.db.set_value("Deal Cost Sheet", dcs.name, "custom_presales_status", "ZZTEST-stale", update_modified=False)
        out = dcs_presales_sync(pr_name, source="interactive")
        self.assertIn(dcs.name, out["synced"])
        ev = frappe.get_all("DCS Governance Event", {"dcs": dcs.name, "event_code": "PRESALES_SYNC"}, ["changes"])
        self.assertEqual(len(ev), 1)
        self.assertIn("ZZTEST-stale", ev[0].changes)
