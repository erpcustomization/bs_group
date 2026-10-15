"""A-15: governed DCS endpoints (A-14) - permission boundary, idempotency,
lifecycle validation and governance-event linkage.

Run on staging / local only:
    bench --site dcs-test.local run-tests --module bsgroup.api.dcs.test_dcs_api
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.api.dcs import ENDPOINTS, approval, award, handover, negotiation
from bsgroup.dcs import governance
from bsgroup.tests.dcs_fixtures import ensure, initialise_living_position, make_dcs, make_user

COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]


class IntegrationTestDCSApi(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()
		for role in COMMERCIAL_ROLES + ["Technical Engineer", "Project Manager", "Sales User", "Presales"]:
			ensure("Role", role, {"role_name": role}, insert=False)
		cls.md = make_user("zztest-md@example.com", ["System Manager", "Sales Manager", "Commercial Controller", "Managing Director"])
		cls.tech = make_user("zztest-tech@example.com", ["Technical Engineer", "Project Manager"])
		cls.nobody = make_user("zztest-nobody@example.com", ["Employee"])

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		governance.reset_correlation_id()
		self.dcs = make_dcs(suffix=frappe.generate_hash(length=6), submit=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# --- registry -------------------------------------------------------------
	def test_every_endpoint_in_the_registry_is_importable_and_whitelisted(self):
		for bare, dotted in ENDPOINTS.items():
			fn = frappe.get_attr(dotted)
			self.assertTrue(callable(fn), dotted)
			self.assertIn(fn, frappe.whitelisted, f"{dotted} is not whitelisted")
			self.assertTrue(dotted.endswith("." + bare))

	# --- permission boundary ----------------------------------------------------
	def test_user_without_dcs_permission_is_refused_before_business_code(self):
		frappe.set_user(self.nobody)
		with self.assertRaises(frappe.PermissionError):
			negotiation.dcs_screen3(dcs=self.dcs.name)
		with self.assertRaises(frappe.PermissionError):
			negotiation.dcs_apply_revision(dcs=self.dcs.name, source="Customer", reason="x", new_total_selling=1400)

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			handover.dcs_screen5(dcs=self.dcs.name)

	def test_technical_role_cannot_revise_or_record_award(self):
		frappe.set_user(self.tech)
		r = negotiation.dcs_apply_revision(dcs=self.dcs.name, source="Technical", reason="tech", new_total_cost=900)
		self.assertEqual(r["ok"], 0)
		self.assertIn("commercial-edit role", r["error"])
		r = award.dcs_record_award(dcs=self.dcs.name, award_reference="PO-1", evidence_type="Customer PO")
		self.assertEqual(r["ok"], 0)
		self.assertIn("commercial action", r["error"])

	# --- R1: the permission response contract, both directions ----------------------
	def test_readonly_role_is_refused_structurally_and_never_raises(self):
		"""A role that may read the sheet but not write it must get the documented
		{ok: 0, ...} refusal - not a leaked PermissionError - and must change nothing."""
		frappe.set_user(self.md)
		initialise_living_position(self.dcs.name)
		before = frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name})
		rev_before = frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "custom_dcs_revision_no")

		frappe.set_user(self.tech)
		self.assertTrue(frappe.has_permission("Deal Cost Sheet", "read"))
		self.assertFalse(frappe.has_permission("Deal Cost Sheet", "write"))
		r = negotiation.dcs_apply_revision(dcs=self.dcs.name, source="Technical", reason="tech", new_total_cost=900)
		self.assertIsInstance(r, dict)
		self.assertEqual(r["ok"], 0)
		self.assertIn("commercial-edit role", r["error"])
		self.assertEqual(r.get("permission_denied"), 1)
		a = award.dcs_record_award(dcs=self.dcs.name, award_reference="PO-X", evidence_type="Customer PO")
		self.assertEqual(a["ok"], 0)
		self.assertIn("commercial action", a["error"])

		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name}), before)
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "custom_dcs_revision_no"), rev_before)

	def test_authorised_commercial_role_passes_the_same_gate(self):
		"""The same endpoint, for a role that does hold write authority, still works."""
		frappe.set_user(self.md)
		self.assertTrue(frappe.has_permission("Deal Cost Sheet", "write"))
		r = negotiation.dcs_apply_revision(
			dcs=self.dcs.name, source="Customer", reason="ZZTEST authorised", new_total_selling=1450
		)
		self.assertEqual(r["ok"], 1, r.get("error"))
		self.assertNotIn("permission_denied", r)
		self.assertGreaterEqual(frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "custom_dcs_revision_no") or 0, 1)

	def test_no_dcs_permission_still_raises_permission_error(self):
		"""The access-control boundary is unchanged: no read access still raises."""
		frappe.set_user(self.nobody)
		with self.assertRaises(frappe.PermissionError):
			negotiation.dcs_apply_revision(dcs=self.dcs.name, source="Customer", reason="x", new_total_selling=1400)

	# --- lifecycle validation -----------------------------------------------------
	def test_release_is_refused_before_award_and_without_owner(self):
		frappe.set_user(self.md)
		r = handover.dcs_delivery_release(dcs=self.dcs.name)
		self.assertEqual(r["ok"], 0)
		self.assertIn("No customer award", r["error"])
		r = handover.dcs_set_delivery_owner(dcs=self.dcs.name, delivery_owner=self.tech)
		self.assertEqual(r["ok"], 0)
		self.assertIn("No award has been recorded", r["error"])

	def test_cancelled_sheet_is_refused_everywhere(self):
		frappe.set_user(self.md)
		frappe.db.set_value("Deal Cost Sheet", self.dcs.name, "docstatus", 2, update_modified=False)
		for fn, kwargs in (
			(negotiation.dcs_apply_revision, {"source": "Customer", "reason": "r", "new_total_selling": 1400}),
			(award.dcs_record_award, {"award_reference": "PO-2", "evidence_type": "Customer PO"}),
			(handover.dcs_set_delivery_owner, {"delivery_owner": self.tech}),
			(handover.dcs_delivery_release, {}),
		):
			r = fn(dcs=self.dcs.name, **kwargs)
			self.assertEqual(r["ok"], 0, fn.__name__)
			self.assertIn("cancelled", r["error"], fn.__name__)

	# --- happy path + governance linkage ---------------------------------------------
	def test_revision_writes_one_event_with_request_key_and_server_correlation(self):
		frappe.set_user(self.md)
		r = negotiation.dcs_apply_revision(dcs=self.dcs.name, source="Customer", reason="ZZTEST discount", new_total_selling=1400)
		self.assertEqual(r["ok"], 1, r.get("error"))
		self.assertTrue(r.get("governance_event"))
		self.assertTrue(r.get("request_key", "").startswith("REQ-"))
		ev = frappe.get_doc("DCS Governance Event", r["governance_event"])
		self.assertEqual(ev.actor, self.md)
		self.assertEqual(ev.source_event_id, r["request_key"])
		self.assertEqual(ev.correlation_id, governance.get_correlation_id())
		self.assertEqual(ev.source_endpoint, "dcs_apply_revision")
		self.assertGreater(ev.change_count, 0)
		self.assertEqual(frappe.db.count("DCS Revision", {"dcs": self.dcs.name}), 2)  # R1 baseline + R2

	def test_identical_request_is_replayed_not_reapplied(self):
		frappe.set_user(self.md)
		kwargs = dict(dcs=self.dcs.name, source="Customer", reason="ZZTEST replay", new_total_selling=1450)
		first = negotiation.dcs_apply_revision(**kwargs)
		self.assertEqual(first["ok"], 1, first.get("error"))
		revisions = frappe.db.count("DCS Revision", {"dcs": self.dcs.name})
		events = frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name})
		second = negotiation.dcs_apply_revision(**kwargs)
		self.assertEqual(second.get("idempotent_replay"), 1)
		self.assertEqual(second["governance_event"], first["governance_event"])
		self.assertEqual(frappe.db.count("DCS Revision", {"dcs": self.dcs.name}), revisions)
		self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name}), events)

	def test_read_screens_are_not_idempotency_keyed(self):
		frappe.set_user(self.md)
		for fn in (negotiation.dcs_screen3, approval.dcs_screen4, handover.dcs_screen5):
			r = fn(dcs=self.dcs.name)
			self.assertEqual(r["ok"], 1, (fn.__name__, r.get("error")))
			self.assertNotIn("request_key", r)

	def test_technical_projection_never_carries_exposure(self):
		frappe.set_user(self.tech)
		r = handover.dcs_screen5(dcs=self.dcs.name)
		self.assertEqual(r["ok"], 1, r.get("error"))
		self.assertEqual(r["projection"], "technical")
		self.assertNotIn("frozen_baseline", r)
		self.assertNotIn("supplier_exposure", r)
		for c in r["technical_conditions"]:
			self.assertNotIn("exposure_amount", c)
			self.assertNotIn("exposure_note", c)

	def test_award_then_owner_then_release_records_three_events(self):
		frappe.set_user(self.md)
		# R2: award freezes the LIVING commercial position, so one must exist first. This is
		# the production control working as designed, not a test shortcut - the fixture now
		# performs the same lifecycle step a commercial user would.
		lp = initialise_living_position(self.dcs.name)
		self.assertEqual(lp["ok"], 1, lp.get("error"))
		self.assertGreaterEqual(lp["revision_no"] or 0, 1)
		r1 = award.dcs_record_award(dcs=self.dcs.name, award_reference="ZZTEST-PO", evidence_type="Customer PO")
		self.assertEqual(r1["ok"], 1, r1.get("error"))
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "custom_award_state"), "Awarded")
		r2 = handover.dcs_set_delivery_owner(dcs=self.dcs.name, delivery_owner=self.tech)
		self.assertEqual(r2["ok"], 1, r2.get("error"))
		blockers = handover.open_blockers(self.dcs.name)
		r3 = handover.dcs_delivery_release(dcs=self.dcs.name)
		if blockers:
			self.assertEqual(r3["ok"], 0)
			self.assertIn("blocker", r3["error"])
			r3 = handover.dcs_delivery_release(dcs=self.dcs.name, override=1, reason="ZZTEST override", acknowledged=1)
		self.assertEqual(r3["ok"], 1, r3.get("error"))
		codes = {e.event_code for e in frappe.get_all("DCS Governance Event", {"dcs": self.dcs.name}, ["event_code"])}
		self.assertTrue(any(c.startswith("DCS_AWARD") for c in codes), codes)
		self.assertIn("DCS_DELIVERY_OWNER_ASSIGNED", codes)
		self.assertTrue(any(c.startswith("DCS_DELIVERY_RELEASED") for c in codes))

	# --- DCS Revision guards (ported into the controller) -------------------------------
	def test_revision_cannot_be_created_directly_or_deleted(self):
		frappe.set_user(self.md)
		r = negotiation.dcs_apply_revision(dcs=self.dcs.name, source="Customer", reason="ZZTEST", new_total_selling=1400)
		self.assertEqual(r["ok"], 1, r.get("error"))
		rev_name = frappe.db.get_value("DCS Revision", {"dcs": self.dcs.name, "revision_no": 2}, "name")
		self.assertTrue(rev_name)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "DCS Revision", "dcs": self.dcs.name, "revision_no": 99, "source": "Internal", "reason": "forged"}).insert(ignore_permissions=True)
		rev = frappe.get_doc("DCS Revision", rev_name)
		rev.approval_state = "Approved"
		with self.assertRaises(frappe.ValidationError):
			rev.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("DCS Revision", rev_name, ignore_permissions=True)
