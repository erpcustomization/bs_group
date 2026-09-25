"""Regression tests for PO_SCOPE_MATCH_OUT_OF_OPTIONS (REL-1 corrective release).

``dcs_po_reconcile`` must only ever write values that exist in the
``custom_po_scope_match`` Select options, so that a Deal Cost Sheet remains
fully saveable after a customer PO has been reconciled against it.

Run on staging / local only:
    bench --site rel1-test.local run-tests --module bsgroup.api.dcs.test_dcs_po_scope_match
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.api.dcs import award
from bsgroup.dcs import governance
from bsgroup.tests.dcs_fixtures import ensure, initialise_living_position, make_dcs, make_user

EN_DASH = "–"
MATCH = "Match"
SUPERSEDED = "Mismatch " + EN_DASH + " Superseded"
DIFFERENT = "Mismatch " + EN_DASH + " Different Scope"
LEGACY_DIFFERENT = "Mismatch - Different Scope"
LEGACY_SUPERSEDED = "Mismatch - Superseded"

COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]


def _options():
	return (frappe.get_meta("Deal Cost Sheet").get_field("custom_po_scope_match").options or "").split("\n")


class IntegrationTestDCSPoScopeMatch(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()
		for role in COMMERCIAL_ROLES + ["Technical Engineer", "Project Manager"]:
			ensure("Role", role, {"role_name": role}, insert=False)
		cls.md = make_user("zztest-md@example.com", ["System Manager", "Sales Manager", "Commercial Controller", "Managing Director"])
		cls.tech = make_user("zztest-tech@example.com", ["Technical Engineer", "Project Manager"])

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		governance.reset_correlation_id()
		self.dcs = make_dcs(suffix=frappe.generate_hash(length=6), submit=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# --- helpers -------------------------------------------------------------------
	def _awarded(self):
		"""Submit -> two small revisions (so an earlier, superseded revision exists) ->
		record award (freezes the baseline). Returns (frozen_ref, frozen_sell, earlier_rev_name)."""
		frappe.set_user(self.md)
		lp = initialise_living_position(self.dcs.name, new_total_selling=1450, reason="ZZTEST scope r1")
		self.assertEqual(lp["ok"], 1, lp.get("error"))
		lp2 = initialise_living_position(self.dcs.name, new_total_selling=1440, reason="ZZTEST scope r2")
		self.assertEqual(lp2["ok"], 1, lp2.get("error"))
		r = award.dcs_record_award(dcs=self.dcs.name, award_reference="ZZTEST-PO", evidence_type="Customer PO")
		self.assertEqual(r["ok"], 1, r.get("error"))
		row = frappe.db.get_value(
			"Deal Cost Sheet", self.dcs.name,
			["custom_baseline_frozen", "custom_revision_reference", "custom_frozen_total_selling", "custom_frozen_revision_no"],
			as_dict=True,
		)
		self.assertEqual(row.custom_baseline_frozen, 1)
		self.assertTrue(row.custom_revision_reference, "frozen revision reference must be set after award")
		earlier = frappe.get_all(
			"DCS Revision",
			filters={"dcs": self.dcs.name, "revision_no": ["<", row.custom_frozen_revision_no or 0]},
			fields=["name"], order_by="revision_no asc", limit=1,
		)
		self.assertTrue(earlier, "an earlier (superseded) DCS Revision must exist")
		return row.custom_revision_reference, row.custom_frozen_total_selling, earlier[0].name

	def _reconcile(self, scope, **over):
		frozen_ref, frozen_sell, _ = over.pop("_ctx")
		kwargs = dict(dcs=self.dcs.name, po_reference="ZZTEST-PO", po_value=frozen_sell,
			po_scope_revision=scope, po_payment_terms="30 days", payment_terms_accepted=1)
		kwargs.update(over)
		return award.dcs_po_reconcile(**kwargs), kwargs

	def _scope_value(self):
		return frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "custom_po_scope_match")

	def _resave(self):
		"""The regression: a full document save must succeed after reconciliation."""
		d = frappe.get_doc("Deal Cost Sheet", self.dcs.name)
		d.deal_owner = self.tech
		d.flags.ignore_links = True
		d.save(ignore_permissions=True)
		return frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "deal_owner")

	# --- option list is version-controlled and complete ----------------------------------
	def test_select_options_contain_every_value_the_endpoint_can_write(self):
		opts = _options()
		for v in (MATCH, SUPERSEDED, DIFFERENT, "Not Checked"):
			self.assertIn(v, opts, f"{v!r} missing from custom_po_scope_match options {opts}")
		self.assertNotIn(LEGACY_DIFFERENT, opts)
		self.assertNotIn(LEGACY_SUPERSEDED, opts)

	# --- 1. matching scope stores Match ------------------------------------------------
	def test_matching_scope_stores_match_and_sheet_saves(self):
		ctx = self._awarded()
		r, _ = self._reconcile(ctx[0], _ctx=ctx)
		self.assertEqual(r["ok"], 1, r.get("error"))
		self.assertEqual(r["checks"]["scope"]["state"], MATCH)
		self.assertEqual(self._scope_value(), MATCH)
		self.assertEqual(r["hard_blocker"], 0)
		self.assertEqual(self._resave(), self.tech)

	# --- 2. superseded scope stores the documented superseded value ---------------------------
	def test_superseded_scope_stores_canonical_superseded_value_and_sheet_saves(self):
		ctx = self._awarded()
		r, _ = self._reconcile(ctx[2], _ctx=ctx)  # cite an earlier DCS Revision of this sheet
		self.assertEqual(r["ok"], 1, r.get("error"))
		self.assertEqual(r["checks"]["scope"]["state"], SUPERSEDED)
		self.assertEqual(self._scope_value(), SUPERSEDED)
		self.assertIn(self._scope_value(), _options())
		self.assertEqual(r["hard_blocker"], 1)  # value matches, scope does not
		self.assertEqual(self._resave(), self.tech)

	# --- 3. genuinely different scope stores the canonical en-dash value ----------------------
	def test_different_scope_stores_canonical_value_and_sheet_remains_saveable(self):
		ctx = self._awarded()
		r, _ = self._reconcile("UNRELATED-SCOPE-REF-XYZ", _ctx=ctx)
		self.assertEqual(r["ok"], 1, r.get("error"))
		self.assertEqual(r["checks"]["scope"]["state"], DIFFERENT)
		stored = self._scope_value()
		self.assertEqual(stored, DIFFERENT)
		self.assertIn(EN_DASH, stored)
		self.assertNotEqual(stored, LEGACY_DIFFERENT)
		self.assertIn(stored, _options())
		self.assertEqual(r["hard_blocker"], 1)
		# 4. the regression itself: a later full save must not raise the Select validation error
		self.assertEqual(self._resave(), self.tech)

	# --- 5. exactly one app-owned Governance Event; 6. repeated reconciliation is idempotent -------
	def test_reconcile_writes_exactly_one_app_owned_event_and_replays_idempotently(self):
		ctx = self._awarded()
		before_total = frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name})
		before_recon = frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name, "event_code": "DCS_PO_RECONCILED"})
		self.assertEqual(before_recon, 0)

		first, kwargs = self._reconcile("UNRELATED-SCOPE-REF-XYZ", _ctx=ctx)
		self.assertEqual(first["ok"], 1, first.get("error"))
		self.assertTrue(first.get("governance_event"))
		self.assertTrue(first.get("request_key", "").startswith("REQ-"))

		self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name}), before_total + 1)
		evs = frappe.get_all(
			"DCS Governance Event", {"dcs": self.dcs.name, "event_code": "DCS_PO_RECONCILED"},
			["name", "source_endpoint", "correlation_id", "source_event_id", "actor", "outcome"],
		)
		self.assertEqual(len(evs), 1, evs)
		ev = evs[0]
		self.assertEqual(ev.name, first["governance_event"])
		self.assertEqual(ev.source_endpoint, "dcs_po_reconcile")  # app-owned
		self.assertEqual(ev.source_event_id, first["request_key"])
		self.assertEqual(ev.correlation_id, governance.get_correlation_id())
		self.assertFalse((ev.correlation_id or "").startswith("AUTH"))
		self.assertEqual(ev.actor, self.md)
		stored_after_first = self._scope_value()
		self.assertEqual(stored_after_first, DIFFERENT)

		second = award.dcs_po_reconcile(**kwargs)
		self.assertEqual(second.get("idempotent_replay"), 1, second)
		self.assertEqual(second["governance_event"], first["governance_event"])
		self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name}), before_total + 1)
		self.assertEqual(
			frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name, "event_code": "DCS_PO_RECONCILED"}), 1
		)
		self.assertEqual(self._scope_value(), stored_after_first)
		self.assertEqual(self._resave(), self.tech)

	# --- data patch: normalises legacy rows, idempotent, touches nothing else -------------------
	def test_normalize_patch_rewrites_legacy_values_and_is_idempotent(self):
		from bsgroup.patches.v0_1 import normalize_po_scope_match as p

		other = make_dcs(suffix=frappe.generate_hash(length=6), submit=True)
		frappe.db.set_value("Deal Cost Sheet", self.dcs.name, "custom_po_scope_match", LEGACY_DIFFERENT, update_modified=False)
		frappe.db.set_value("Deal Cost Sheet", other.name, "custom_po_scope_match", LEGACY_SUPERSEDED, update_modified=False)
		owner_before = frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "deal_owner")
		events_before = frappe.db.count("DCS Governance Event")

		p.execute()
		self.assertEqual(self._scope_value(), DIFFERENT)
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", other.name, "custom_po_scope_match"), SUPERSEDED)

		p.execute()  # second run: nothing left to change, no error
		self.assertEqual(self._scope_value(), DIFFERENT)
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", other.name, "custom_po_scope_match"), SUPERSEDED)
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "deal_owner"), owner_before)
		self.assertEqual(frappe.db.count("DCS Governance Event"), events_before)
		self.assertEqual(self._resave(), self.tech)
