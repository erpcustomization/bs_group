"""Regression tests for the DCS vendor-revision defect report (DCS-Alamar-008-1, 28 Sep 2026).

Every governed action is driven through Frappe's real RPC binding
(``frappe.call(dotted_path, **fields)`` - the seam ``frappe.handler`` uses for the
form's ``frappe.call``), exactly as the Deal Cost Sheet form does. Document actions
(cancel / amend / submit) go through the document API the form uses.

Guarded:
1. an un-awarded sheet never shows the award-drift text; a neutral pre-award note is
   returned instead; a genuinely awarded, frozen sheet still shows drift; after an award
   reversal the drift text is gone again;
2. a cost-only amendment of a Quoted sheet whose Quotation relationship is intact stays
   Quoted; a selling change, or another sheet's quotation, still advances to
   "Submitted to Sales"; Won / Lost are never reset; a sheet without a quotation still
   advances exactly as before;
3. the amendment re-points its OWN Quotation's back-link and records exactly one
   governance event; a quotation of another sheet is never touched;
4. vendor revision before and after award, award reversal, idempotent replay,
   exactly one event per state change, unchanged selling on a vendor revision,
   unchanged approval routing on a customer revision, no second award.

Run on staging / local only:
	bench --site rel1-test.local run-tests --module bsgroup.api.dcs.test_dcs_vendor_revision
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_relationship_intact
from bsgroup.dcs import governance
from bsgroup.tests.dcs_fixtures import PREFIX, ensure, initialise_living_position, make_dcs, make_user

COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]
APPLY_REVISION = "bsgroup.api.dcs.negotiation.dcs_apply_revision"
SCREEN5 = "bsgroup.api.dcs.handover.dcs_screen5"
RECORD_AWARD = "bsgroup.api.dcs.award.dcs_record_award"
AWARD_REVERSAL = "bsgroup.api.dcs.award.dcs_award_reversal"
DRIFT_TEXT = "frozen baseline that was awarded"
LINKBACK = "DCS_AMEND_QUOTATION_LINKBACK"


def events(dcs_name, code=None):
	f = {"dcs": dcs_name}
	if code:
		f["event_code"] = code
	return frappe.db.count("DCS Governance Event", f)


def make_quotation_for(dcs, total=None):
	"""A Draft Quotation linked both ways, on the same Opportunity, quoting the sheet's
	selling total - the state make_quotation + the retained link-back script leave behind.
	Inserted through the document API; if ERPNext's selling validations reject the bare
	fixture on this site, fall back to a direct row insert with the same totals."""
	total = total if total is not None else dcs.total_selling
	item = dcs.items[0].item_code
	values = {
		"doctype": "Quotation",
		"quotation_to": "Customer",
		"party_name": dcs.party,
		"customer_name": dcs.party,
		"opportunity": dcs.opportunity,
		"company": dcs.company,
		"custom_deal_cost_sheet": dcs.name,
		"custom_subject": f"{PREFIX} quotation {dcs.name}",
		"items": [{"item_code": item, "qty": 1, "rate": total, "amount": total}],
	}
	q = frappe.get_doc(values)
	q.flags.ignore_links = True
	frappe.db.savepoint("zz_q")
	try:
		q.insert(ignore_permissions=True, ignore_mandatory=True)
	except Exception:  # noqa: BLE001 - site-specific selling validation; totals are what matter here
		frappe.db.rollback(save_point="zz_q")
		q = frappe.get_doc(values)
		q.total = total
		q.net_total = total
		q.grand_total = total
		q.base_total = total
		q.base_net_total = total
		q.base_grand_total = total
		q.flags.ignore_links = True
		q.db_insert()
		for row in q.items:
			row.parent = q.name
			row.parenttype = "Quotation"
			row.parentfield = "items"
			row.db_insert()
	frappe.db.set_value("Deal Cost Sheet", dcs.name, {"custom_quotation": q.name, "custom_deal_status": "Quoted"}, update_modified=False)
	return q


def amend(dcs):
	"""Cancel and amend through the document API (what the form's Cancel -> Amend does).
	The form always works from the stored record, so reload first: the fixture's direct
	writes (quotation link, Quoted status) must be what the amendment copies."""
	dcs.reload()
	dcs.flags.ignore_links = True
	dcs.cancel()
	new = frappe.copy_doc(dcs)
	new.amended_from = dcs.name
	new.docstatus = 0
	new.flags.ignore_links = True
	new.insert(ignore_permissions=True, ignore_mandatory=True)
	return new


def submit(doc):
	doc.flags.ignore_links = True
	doc.submit()
	doc.reload()
	return doc


class IntegrationTestDCSVendorRevision(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()
		for role in COMMERCIAL_ROLES + ["Technical Engineer", "Project Manager", "Sales User", "Presales"]:
			ensure("Role", role, {"role_name": role}, insert=False)
		cls.md = make_user("zztest-md@example.com", ["System Manager", "Sales Manager", "Commercial Controller", "Managing Director"])

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		governance.reset_correlation_id()
		self.dcs = make_dcs(suffix=frappe.generate_hash(length=6), submit=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# ------------------------------------------------------------------ finding 1
	def test_unawarded_sheet_never_shows_award_drift_but_a_neutral_note(self):
		frappe.set_user(self.md)
		self.assertEqual(initialise_living_position(self.dcs.name).get("ok"), 1)
		n0 = events(self.dcs.name)
		r = frappe.call(APPLY_REVISION, dcs=self.dcs.name, source="Vendor", reason="ZZTEST vendor cost +100", new_total_cost=1100)
		self.assertEqual(r.get("ok"), 1, r.get("error"))
		self.assertEqual(events(self.dcs.name), n0 + 1)
		s5 = frappe.call(SCREEN5, dcs=self.dcs.name)
		self.assertEqual(s5.get("ok"), 1, s5.get("error"))
		rr = s5["release_readiness"]
		self.assertEqual(s5["states"]["customer_award"], "Not Awarded")
		self.assertEqual(int(s5["states"]["commercial_baseline_frozen"] or 0), 0)
		self.assertNotIn(DRIFT_TEXT, rr["note"])
		self.assertEqual(rr["awarded_and_frozen"], 0)
		self.assertIn("No award is recorded", rr["pre_award_note"])
		self.assertIn("differs from the submitted baseline", rr["pre_award_note"])

	def test_awarded_frozen_sheet_still_shows_drift_and_reversal_clears_it(self):
		frappe.set_user(self.md)
		self.assertEqual(initialise_living_position(self.dcs.name).get("ok"), 1)
		a = frappe.call(RECORD_AWARD, dcs=self.dcs.name, award_reference="PO-ZZ-1", evidence_type="Customer PO", notes="ZZTEST award")
		self.assertEqual(a.get("ok"), 1, a.get("error"))
		s5 = frappe.call(SCREEN5, dcs=self.dcs.name)
		self.assertEqual(s5["release_readiness"]["awarded_and_frozen"], 1)
		self.assertNotIn(DRIFT_TEXT, s5["release_readiness"]["note"])  # aligned at the moment of award
		self.assertEqual(s5["release_readiness"]["pre_award_note"], "")
		# a vendor revision after award: genuine drift against the frozen baseline
		n0 = events(self.dcs.name)
		r = frappe.call(APPLY_REVISION, dcs=self.dcs.name, source="Vendor", reason="ZZTEST post-award vendor cost", new_total_cost=1200)
		self.assertEqual(r.get("ok"), 1, r.get("error"))
		self.assertEqual(events(self.dcs.name), n0 + 1)
		s5 = frappe.call(SCREEN5, dcs=self.dcs.name)
		self.assertIn(DRIFT_TEXT, s5["release_readiness"]["note"])
		self.assertEqual(s5["release_readiness"]["pre_award_note"], "")
		# award reversal (MD): no active award -> the award-drift instruction is gone
		n1 = events(self.dcs.name)
		rv = frappe.call(AWARD_REVERSAL, dcs=self.dcs.name, reason="ZZTEST reversal", acknowledge="YES", mode="reverse")
		self.assertEqual(rv.get("ok"), 1, rv.get("error"))
		self.assertEqual(events(self.dcs.name), n1 + 1)
		s5 = frappe.call(SCREEN5, dcs=self.dcs.name)
		self.assertEqual(s5["states"]["customer_award"], "Not Awarded")
		self.assertNotIn(DRIFT_TEXT, s5["release_readiness"]["note"])
		self.assertEqual(s5["release_readiness"]["awarded_and_frozen"], 0)

	# ------------------------------------------------------------------ findings 2 + 3
	def test_cost_only_amendment_keeps_quoted_and_repoints_own_quotation_once(self):
		q = make_quotation_for(self.dcs)
		self.assertTrue(quotation_relationship_intact(frappe.get_doc("Deal Cost Sheet", self.dcs.name)))
		new = amend(self.dcs)
		new.items[0].cost_rate = 1200  # cost only; selling stays 1500 = quotation total
		new.save(ignore_permissions=True)
		self.assertEqual(new.custom_deal_status, "Quoted")
		self.assertEqual(new.custom_quotation, q.name)
		submit(new)
		self.assertEqual(new.docstatus, 1)
		self.assertEqual(new.custom_deal_status, "Quoted")
		self.assertEqual(new.custom_quotation, q.name)
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), new.name)
		self.assertEqual(events(new.name, LINKBACK), 1)
		ev = frappe.get_all("DCS Governance Event", filters={"dcs": new.name, "event_code": LINKBACK}, fields=["name", "actor", "source_endpoint", "source_event_id"])[0]
		self.assertEqual(ev["source_endpoint"], "deal_cost_sheet.on_submit")
		self.assertTrue(ev["source_event_id"])
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "docstatus"), 2)
		# submitted baseline of the amendment reflects the new cost; selling unchanged
		self.assertEqual(float(new.total_cost), 1200.0)
		self.assertEqual(float(new.total_selling), 1500.0)

	def test_selling_change_on_amendment_still_advances_to_submitted_to_sales(self):
		q = make_quotation_for(self.dcs)
		new = amend(self.dcs)
		new.items[0].selling_rate = 1600  # selling moved: the quotation no longer stands for this position
		new.save(ignore_permissions=True)
		submit(new)
		self.assertEqual(new.custom_deal_status, "Submitted to Sales")
		# the quotation is still the sheet's own quotation, so its back-link follows the amendment
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), new.name)
		self.assertEqual(events(new.name, LINKBACK), 1)

	def test_another_sheets_quotation_is_not_intact_and_never_repointed(self):
		q = make_quotation_for(self.dcs)
		other = make_dcs(suffix=frappe.generate_hash(length=6), submit=True)
		frappe.db.set_value("Quotation", q.name, "custom_deal_cost_sheet", other.name, update_modified=False)
		self.assertFalse(quotation_relationship_intact(frappe.get_doc("Deal Cost Sheet", self.dcs.name)))
		new = amend(self.dcs)
		submit(new)
		self.assertEqual(new.custom_deal_status, "Submitted to Sales")
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), other.name)
		self.assertEqual(events(new.name, LINKBACK), 0)

	def test_cancelled_quotation_is_not_intact(self):
		q = make_quotation_for(self.dcs)
		frappe.db.set_value("Quotation", q.name, "docstatus", 2, update_modified=False)
		self.assertFalse(quotation_relationship_intact(frappe.get_doc("Deal Cost Sheet", self.dcs.name)))

	def test_quoted_without_matching_selling_is_not_intact(self):
		make_quotation_for(self.dcs, total=1400)  # quotation total != sheet selling 1500
		self.assertFalse(quotation_relationship_intact(frappe.get_doc("Deal Cost Sheet", self.dcs.name)))

	def test_won_and_lost_are_never_reset_on_submit(self):
		for status in ("Won", "Lost"):
			d = make_dcs(suffix=frappe.generate_hash(length=6), submit=False, custom_deal_status=status)
			submit(d)
			self.assertEqual(d.custom_deal_status, status)

	def test_plain_submit_without_quotation_still_advances(self):
		d = make_dcs(suffix=frappe.generate_hash(length=6), submit=False)
		submit(d)
		self.assertEqual(d.custom_deal_status, "Submitted to Sales")
		self.assertEqual(events(d.name, LINKBACK), 0)

	def test_quoted_sheet_without_quotation_link_still_advances(self):
		d = make_dcs(suffix=frappe.generate_hash(length=6), submit=False, custom_deal_status="Quoted")
		submit(d)  # "Quoted" with no quotation relationship is not preserved
		self.assertEqual(d.custom_deal_status, "Submitted to Sales")

	# ------------------------------------------------------------------ revision behaviour
	def test_vendor_revision_leaves_selling_and_deal_status_unchanged_and_is_idempotent(self):
		make_quotation_for(self.dcs)
		frappe.set_user(self.md)
		self.assertEqual(initialise_living_position(self.dcs.name, new_total_selling=1500).get("ok"), 1)
		before = frappe.db.get_value("Deal Cost Sheet", self.dcs.name, ["custom_working_total_selling", "custom_deal_status", "total_cost", "total_selling", "custom_quotation"], as_dict=True)
		self.assertEqual(before.custom_deal_status, "Quoted")
		n0 = events(self.dcs.name)
		args = dict(dcs=self.dcs.name, source="Vendor", reason="ZZTEST vendor +50", new_total_cost=1050)
		r1 = frappe.call(APPLY_REVISION, **args)
		self.assertEqual(r1.get("ok"), 1, r1.get("error"))
		self.assertEqual(float(r1["state"]["working_total_selling"]), float(before.custom_working_total_selling))
		self.assertEqual(float(r1["state"]["working_total_cost"]), 1050.0)
		after = frappe.db.get_value("Deal Cost Sheet", self.dcs.name, ["custom_working_total_selling", "custom_deal_status", "total_cost", "total_selling", "custom_working_total_cost", "custom_quotation", "docstatus"], as_dict=True)
		self.assertEqual(after.custom_working_total_selling, before.custom_working_total_selling)
		self.assertEqual(after.custom_deal_status, "Quoted")  # a revision never touches the deal status
		self.assertEqual(after.custom_quotation, before.custom_quotation)
		self.assertEqual(after.total_cost, before.total_cost)  # submitted baseline untouched
		self.assertEqual(after.total_selling, before.total_selling)
		self.assertEqual(float(after.custom_working_total_cost), 1050.0)
		self.assertEqual(after.docstatus, 1)
		self.assertEqual(events(self.dcs.name), n0 + 1)
		revisions = frappe.db.count("DCS Revision", {"dcs": self.dcs.name})
		r2 = frappe.call(APPLY_REVISION, **args)  # identical request -> replay, no second event, no second revision
		self.assertEqual(r2.get("idempotent_replay"), 1)
		self.assertEqual(r2.get("governance_event"), r1.get("governance_event"))
		self.assertEqual(events(self.dcs.name), n0 + 1)
		self.assertEqual(frappe.db.count("DCS Revision", {"dcs": self.dcs.name}), revisions)

	def test_customer_revision_before_award_keeps_approval_routing(self):
		frappe.set_user(self.md)
		self.assertEqual(initialise_living_position(self.dcs.name, new_total_selling=1500).get("ok"), 1)
		r = frappe.call(APPLY_REVISION, dcs=self.dcs.name, source="Customer", reason="ZZTEST concession 20%", new_total_selling=1200)
		self.assertEqual(r.get("ok"), 1, r.get("error"))
		self.assertEqual(r["state"]["approval_required"], "Managing Director")
		self.assertEqual(r["state"]["approval_state"], "Pending Endorsement")
		a = frappe.call(RECORD_AWARD, dcs=self.dcs.name, award_reference="PO-ZZ-2", evidence_type="Customer PO", notes="ZZTEST")
		self.assertEqual(a.get("ok"), 0)  # unapproved concession cannot be awarded - control intact
		self.assertIn("Managing Director approval", a.get("error"))

	def test_award_cannot_be_recorded_twice(self):
		frappe.set_user(self.md)
		self.assertEqual(initialise_living_position(self.dcs.name).get("ok"), 1)
		a1 = frappe.call(RECORD_AWARD, dcs=self.dcs.name, award_reference="PO-ZZ-3", evidence_type="Customer PO", notes="ZZTEST")
		self.assertEqual(a1.get("ok"), 1, a1.get("error"))
		n = events(self.dcs.name)
		a2 = frappe.call(RECORD_AWARD, dcs=self.dcs.name, award_reference="PO-ZZ-3b", evidence_type="Customer PO", notes="ZZTEST again")
		self.assertEqual(a2.get("ok"), 0)
		self.assertIn("already recorded", a2.get("error"))
		self.assertEqual(events(self.dcs.name), n)
