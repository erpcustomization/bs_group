"""Staging-only cancel/amend tests. Fixture setup is separate from the actions.

Cancellation and amendment run through the ordinary document methods without
ignore_links; dependency refusals and caught exceptions must remain atomic.
"""
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from bsgroup.dcs import governance
from bsgroup.dcs.presales_lineage import DETACH, RESTORE
from bsgroup.tests.dcs_fixtures import make_dcs, make_user
from bsgroup.api.dcs.test_dcs_vendor_revision import quotation_values

CONTROLLER = "bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet"


class IntegrationTestPresalesLineage(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        governance.reset_correlation_id()

    def linked(self, submitted_request=True):
        dcs = make_dcs(suffix="PRLINE-" + frappe.generate_hash(length=8))
        request = frappe.get_doc({
            "doctype": "Presales Request", "opportunity": dcs.opportunity,
            "subject": "ZZTEST Presales lineage", "status": "Open",
            "request_date": nowdate(),
        })
        request.flags.ignore_links = True
        request.insert(ignore_permissions=True, ignore_mandatory=True)
        if submitted_request:
            request.submit()
        dcs.presales_request = request.name
        dcs.flags.ignore_links = False
        dcs.flags.ignore_mandatory = True
        dcs.save(ignore_permissions=True)
        dcs.submit()
        # Established bidirectional production link; fixture setup only.
        frappe.db.set_value("Presales Request", request.name,
                            "custom_deal_cost_sheet", dcs.name, update_modified=False)
        request.reload()
        dcs.reload()
        dcs.flags.ignore_links = False
        return dcs, request

    def amendment(self, predecessor):
        doc = frappe.copy_doc(predecessor)
        doc.docstatus = 0
        doc.amended_from = predecessor.name
        doc.flags.ignore_links = False
        doc.insert()
        return doc

    def pointer(self, request):
        return frappe.db.get_value("Presales Request", request.name, "custom_deal_cost_sheet") or ""

    def events(self, dcs, code):
        return frappe.get_all("DCS Governance Event",
                             filters={"dcs": dcs.name, "event_code": code},
                             fields=["name", "actor", "changes"])

    def test_submitted_presales_cancel_and_amend_without_manual_unlink(self):
        dcs, request = self.linked()
        old_modified = request.modified
        dcs.cancel()
        self.assertEqual(self.pointer(request), "")
        self.assertEqual(dcs.presales_request, request.name)
        self.assertEqual(frappe.db.get_value("Presales Request", request.name, "docstatus"), 1)
        events = self.events(dcs, DETACH)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].actor, "Administrator")
        change = json.loads(events[0].changes)[0]
        self.assertEqual(change["old_value"], dcs.name)
        self.assertEqual(change["new_value"], "")
        self.assertGreater(frappe.db.get_value("Presales Request", request.name, "modified"), old_modified)
        amended = self.amendment(dcs)
        self.assertEqual(self.pointer(request), "")  # a draft never claims the request
        amended.submit()
        self.assertEqual(self.pointer(request), amended.name)
        self.assertEqual(len(self.events(amended, RESTORE)), 1)
        self.assertEqual(amended.presales_request, request.name)
        self.assertEqual(amended.custom_working_total_cost, amended.total_cost)
        versions = frappe.get_all("Version", filters={"ref_doctype": "Presales Request", "docname": request.name},
                                  fields=["data"])
        moves = [row for row in versions if "custom_deal_cost_sheet" in row.data]
        self.assertEqual(len(moves), 2)
        # A repeated projection callback is a no-op.
        from bsgroup.dcs.presales_lineage import on_submit
        on_submit(amended)
        self.assertEqual(len(self.events(amended, RESTORE)), 1)

    def test_draft_presales_pointer_is_also_detached_and_restored(self):
        dcs, request = self.linked(submitted_request=False)
        dcs.cancel()
        amended = self.amendment(dcs)
        amended.submit()
        self.assertEqual(self.pointer(request), amended.name)
        self.assertEqual(frappe.db.get_value("Presales Request", request.name, "docstatus"), 0)

    def test_two_amendments_keep_the_same_presales_lineage(self):
        dcs, request = self.linked()
        dcs.cancel()
        first = self.amendment(dcs)
        first.submit()
        first.cancel()
        second = self.amendment(first)
        second.submit()
        self.assertEqual(self.pointer(request), second.name)
        self.assertEqual(len(self.events(first, DETACH)), 1)
        self.assertEqual(len(self.events(second, RESTORE)), 1)

    def test_unrelated_submitted_request_still_blocks_and_rolls_back_own_link(self):
        dcs, request = self.linked()
        other = make_dcs(suffix="OTHER-" + frappe.generate_hash(length=8))
        unrelated = frappe.get_doc({
            "doctype": "Presales Request", "opportunity": other.opportunity,
            "subject": "ZZTEST unrelated", "status": "Open", "request_date": nowdate(),
        }).insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
        unrelated.submit()
        frappe.db.set_value("Presales Request", unrelated.name, "custom_deal_cost_sheet", dcs.name)
        with self.assertRaises(frappe.LinkExistsError):
            dcs.cancel()
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", dcs.name, "docstatus"), 1)
        self.assertEqual(self.pointer(request), dcs.name)
        self.assertEqual(self.pointer(unrelated), dcs.name)
        self.assertEqual(self.events(dcs, DETACH), [])

    def test_submitted_quotation_still_blocks_and_detach_is_atomic(self):
        dcs, request = self.linked()
        quote = frappe.get_doc(quotation_values(dcs, dcs.total_selling)).insert()
        quote.submit()
        dcs.reload()
        dcs.flags.ignore_links = False
        with self.assertRaises(frappe.LinkExistsError):
            dcs.cancel()
        self.assertEqual(self.pointer(request), dcs.name)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", dcs.name, "docstatus"), 1)
        self.assertEqual(self.events(dcs, DETACH), [])

    def test_wrong_party_request_is_not_unlinked(self):
        dcs, request = self.linked()
        frappe.db.set_value("Presales Request", request.name, "party", "ZZTEST-other-party")
        with self.assertRaises(frappe.ValidationError):
            dcs.cancel()
        self.assertEqual(self.pointer(request), dcs.name)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", dcs.name, "docstatus"), 1)

    def test_awarded_or_released_dcs_cannot_use_cancel_to_bypass_reversal(self):
        for field, value in [("custom_award_state", "Awarded"),
                             ("custom_delivery_release_state", "Released"),
                             ("custom_delivery_release_state", "Released with MD Override")]:
            dcs, request = self.linked()
            frappe.db.set_value("Deal Cost Sheet", dcs.name, field, value)
            dcs.reload()
            with self.assertRaises(frappe.ValidationError):
                dcs.cancel()
            self.assertEqual(self.pointer(request), dcs.name)
            self.assertEqual(frappe.db.get_value("Deal Cost Sheet", dcs.name, "docstatus"), 1)

    def test_guest_cannot_cancel_or_detach(self):
        dcs, request = self.linked()
        dcs.flags.ignore_permissions = False
        frappe.set_user("Guest")
        try:
            with self.assertRaises(frappe.PermissionError):
                dcs.cancel()
        finally:
            frappe.set_user("Administrator")
        self.assertEqual(self.pointer(request), dcs.name)
        self.assertEqual(self.events(dcs, DETACH), [])

    def test_amendment_cannot_overwrite_a_new_presales_pointer(self):
        dcs, request = self.linked()
        dcs.cancel()
        amended = self.amendment(dcs)
        other = make_dcs(suffix="POINTER-" + frappe.generate_hash(length=8))
        frappe.db.set_value("Presales Request", request.name, "custom_deal_cost_sheet", other.name)
        with self.assertRaises(frappe.ValidationError):
            amended.submit()
        self.assertEqual(self.pointer(request), other.name)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", amended.name, "docstatus"), 0)
        self.assertEqual(self.events(amended, RESTORE), [])

    def test_late_submit_failure_rolls_back_link_baseline_and_events(self):
        dcs, request = self.linked()
        dcs.cancel()
        amended = self.amendment(dcs)
        with patch(CONTROLLER + ".dcs_amend_quotation_linkback", side_effect=frappe.ValidationError("late failure")):
            with self.assertRaises(frappe.ValidationError):
                amended.submit()
        self.assertEqual(self.pointer(request), "")
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", amended.name, "docstatus"), 0)
        self.assertEqual(frappe.db.count("DCS Revision", {"dcs": amended.name}), 0)
        self.assertEqual(self.events(amended, RESTORE), [])

    def test_amendment_cannot_drop_the_detached_presales_source(self):
        dcs, request = self.linked()
        dcs.cancel()
        amended = self.amendment(dcs)
        amended.presales_request = None
        amended.save()
        with self.assertRaises(frappe.ValidationError):
            amended.submit()
        self.assertEqual(self.pointer(request), "")
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", amended.name, "docstatus"), 0)

    def test_cancelled_presales_request_is_never_restored(self):
        dcs, request = self.linked()
        dcs.cancel()
        amended = self.amendment(dcs)
        frappe.db.set_value("Presales Request", request.name, "docstatus", 2)
        with self.assertRaises(frappe.ValidationError):
            amended.submit()
        self.assertEqual(self.pointer(request), "")
        self.assertEqual(self.events(amended, RESTORE), [])

    def test_cancel_does_not_accept_a_link_check_bypass_flag(self):
        dcs, request = self.linked()
        quote = frappe.get_doc(quotation_values(dcs, dcs.total_selling)).insert()
        quote.submit()
        dcs.reload()
        dcs.flags.ignore_links = True
        with self.assertRaises(frappe.LinkExistsError):
            dcs.cancel()
        self.assertEqual(self.pointer(request), dcs.name)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", dcs.name, "docstatus"), 1)

    def test_technical_user_cannot_cancel_even_with_in_process_permission_flag(self):
        dcs, request = self.linked()
        user = make_user("zztest-presales-lineage-tech@example.com", ["Technical Engineer"])
        dcs.flags.ignore_permissions = True
        frappe.set_user(user)
        try:
            with self.assertRaises(frappe.PermissionError):
                dcs.cancel()
        finally:
            frappe.set_user("Administrator")
        self.assertEqual(self.pointer(request), dcs.name)
        self.assertEqual(frappe.db.get_value("Deal Cost Sheet", dcs.name, "docstatus"), 1)
