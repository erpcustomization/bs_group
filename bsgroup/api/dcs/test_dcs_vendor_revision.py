"""Regression tests for the DCS vendor-revision defect report (DCS-Alamar-008-1, 28 Sep 2026).

TWO KINDS OF TEST LIVE HERE - do not read one as the other:

``IntegrationTestDCSVendorRevisionBinding`` - Python-side *binding* tests (unit coverage).
	Endpoints are invoked with ``frappe.call(dotted_path, **fields)``, i.e. through
	``frappe.get_newargs`` - the same argument binding ``frappe.handler`` applies to an HTTP
	request - but NOT through HTTP: no web server, session, CSRF, JSON transport or browser is
	involved. Fixtures take shortcuts (``ignore_links`` / ``ignore_mandatory`` on inserts, a
	direct-row fallback for the Quotation fixture, direct ``db.set_value`` on fixture fields) so
	that each control can be exercised in isolation.

``IntegrationTestDCSAmendmentFlow`` - the real amendment flow, strict.
	Quotation and Deal Cost Sheet go through the document API exactly as a saved form does:
	no ``ignore_links``, no ``ignore_mandatory``, no ``db_insert`` fallback, no direct field writes
	on the records under test. Cancel -> amend -> save -> submit as the desk does.

Neither class drives a browser. Browser/HTTP verification (form JS, ``frappe.call`` over
``/api/method``, the headline rendering) is a manual post-deploy check on a real desk session.

Run on staging / local only, sequentially (never two runs against one database):
	bench --site rel1-test.local run-tests --module bsgroup.api.dcs.test_dcs_vendor_revision
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_relationship_intact
from bsgroup.dcs import governance
from bsgroup.tests.dcs_fixtures import PREFIX, ensure, initialise_living_position, make_customer, make_dcs, make_user

COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]
APPLY_REVISION = "bsgroup.api.dcs.negotiation.dcs_apply_revision"
SCREEN5 = "bsgroup.api.dcs.handover.dcs_screen5"
RECORD_AWARD = "bsgroup.api.dcs.award.dcs_record_award"
AWARD_REVERSAL = "bsgroup.api.dcs.award.dcs_award_reversal"
DRIFT_TEXT = "frozen baseline that was awarded"
LINKBACK = "DCS_AMEND_QUOTATION_LINKBACK"
STALE_TEXT = "was not re-pointed automatically"


def events(dcs_name, code=None):
	f = {"dcs": dcs_name}
	if code:
		f["event_code"] = code
	return frappe.db.count("DCS Governance Event", f)


def stale_reports(dcs_name):
	return frappe.db.count("Comment", {"reference_doctype": "Deal Cost Sheet", "reference_name": dcs_name, "comment_type": "Info", "content": ["like", "%" + STALE_TEXT + "%"]})


def quotation_versions(qname):
	return frappe.db.count("Version", {"ref_doctype": "Quotation", "docname": qname, "data": ["like", "%custom_deal_cost_sheet%"]})


def quotation_values(dcs, total):
	"""Field set a saved Quotation form carries for this sheet's deal."""
	company = dcs.company or frappe.db.get_single_value("Global Defaults", "default_company")
	currency = frappe.db.get_value("Company", company, "default_currency")
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
	plc = frappe.db.get_value("Price List", price_list, "currency") or currency
	item = dcs.items[0].item_code
	uom = frappe.db.get_value("Item", item, "stock_uom")
	# site-mandatory on Quotation: a Sales Taxes and Charges Template (property setter) and the
	# custom Payment Terms text - filled the way the app's make_quotation / the desk form fill them
	vat_template = frappe.db.get_value("Sales Taxes and Charges Template", {"company": company, "name": ["like", "%UAE VAT 5%%"]}, "name")
	taxes = frappe.get_all(
		"Sales Taxes and Charges", filters={"parent": vat_template},
		fields=["charge_type", "account_head", "description", "rate", "included_in_print_rate"], order_by="idx",
	) if vat_template else []
	return {
		"doctype": "Quotation",
		"quotation_to": dcs.party_type,
		"party_name": dcs.party,
		"customer_name": dcs.party,
		"order_type": "Sales",
		"transaction_date": nowdate(),
		"valid_till": add_days(nowdate(), 30),
		"opportunity": dcs.opportunity,
		"company": company,
		"currency": currency,
		"conversion_rate": 1,
		"selling_price_list": price_list,
		"price_list_currency": plc,
		"plc_conversion_rate": 1,
		"ignore_pricing_rule": 1,
		"custom_deal_cost_sheet": dcs.name,
		"custom_subject": f"{PREFIX} quotation {dcs.name}",
		"custom_payment_terms": f"{PREFIX} 100% on delivery",
		"taxes_and_charges": vat_template,
		"taxes": taxes,
		"items": [{"item_code": item, "qty": 1, "uom": uom, "stock_uom": uom, "conversion_factor": 1, "rate": total, "price_list_rate": total}],
	}


# ============================================================================ unit coverage
def make_quotation_for(dcs, total=None):
	"""FIXTURE SHORTCUT (unit coverage only): a Draft Quotation linked both ways, on the same
	Opportunity, quoting the sheet's selling total. Document insert with ignore_links /
	ignore_mandatory; if the site's selling validations still reject it, a direct row insert with the
	same totals. The strict flow class below does none of this."""
	total = total if total is not None else dcs.total_selling
	values = quotation_values(dcs, total)
	q = frappe.get_doc(values)
	q.flags.ignore_links = True
	frappe.db.savepoint("zz_q")
	try:
		q.insert(ignore_permissions=True, ignore_mandatory=True)
	except Exception:  # noqa: BLE001
		frappe.db.rollback(save_point="zz_q")
		q = frappe.get_doc(values)
		for f in ("total", "net_total", "grand_total", "base_total", "base_net_total", "base_grand_total"):
			q.set(f, total)
		q.flags.ignore_links = True
		q.db_insert()
		for row in q.items:
			row.parent, row.parenttype, row.parentfield = q.name, "Quotation", "items"
			row.db_insert()
	frappe.db.set_value("Deal Cost Sheet", dcs.name, {"custom_quotation": q.name, "custom_deal_status": "Quoted"}, update_modified=False)
	return q


def amend(dcs):
	"""FIXTURE SHORTCUT: cancel and amend with ignore_links (the strict class uses amend_strict)."""
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


class IntegrationTestDCSVendorRevisionBinding(IntegrationTestCase):
	"""Python-side frappe.call binding tests + fixture shortcuts. NOT an HTTP / browser test."""

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
		self.assertIn("differs from the submitted baseline", rr["pre_award_note"])
		self.assertIn("No award is recorded and no baseline is frozen", rr["pre_award_note"])
		self.assertNotIn("retained as history", rr["pre_award_note"])

	def test_awarded_frozen_sheet_still_shows_drift_and_reversal_clears_it_with_an_accurate_note(self):
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
		# award reversal (MD): no active award -> no award-drift instruction; the frozen baseline stays as history
		n1 = events(self.dcs.name)
		rv = frappe.call(AWARD_REVERSAL, dcs=self.dcs.name, reason="ZZTEST reversal", acknowledge="YES", mode="reverse")
		self.assertEqual(rv.get("ok"), 1, rv.get("error"))
		self.assertEqual(events(self.dcs.name), n1 + 1)
		s5 = frappe.call(SCREEN5, dcs=self.dcs.name)
		self.assertEqual(s5["states"]["customer_award"], "Not Awarded")
		self.assertEqual(int(s5["states"]["commercial_baseline_frozen"] or 0), 1)  # history retained
		self.assertNotIn(DRIFT_TEXT, s5["release_readiness"]["note"])
		self.assertEqual(s5["release_readiness"]["awarded_and_frozen"], 0)
		note = s5["release_readiness"]["pre_award_note"]
		self.assertIn("No award is currently recorded", note)
		self.assertIn("frozen baseline of the reversed award", note)
		self.assertIn("retained as history", note)
		self.assertNotIn("no baseline is frozen", note)

	# ------------------------------------------------------------------ findings 2 + 3
	def test_cost_only_amendment_keeps_quoted_and_repoints_own_draft_quotation_once(self):
		q = make_quotation_for(self.dcs)
		self.assertTrue(quotation_relationship_intact(frappe.get_doc("Deal Cost Sheet", self.dcs.name)))
		m0 = frappe.db.get_value("Quotation", q.name, "modified")
		new = amend(self.dcs)
		new.items[0].cost_rate = 1200  # cost only; selling stays 1500 = quotation total
		new.save(ignore_permissions=True)
		self.assertEqual(new.custom_deal_status, "Quoted")
		submit(new)
		self.assertEqual(new.docstatus, 1)
		self.assertEqual(new.custom_deal_status, "Quoted")
		self.assertEqual(new.custom_quotation, q.name)
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), new.name)
		self.assertGreater(frappe.db.get_value("Quotation", q.name, "modified"), m0)  # stale form saves are refused
		self.assertEqual(events(new.name, LINKBACK), 1)
		self.assertEqual(quotation_versions(q.name), 1)
		self.assertEqual(stale_reports(new.name), 0)
		ev = frappe.get_all("DCS Governance Event", filters={"dcs": new.name, "event_code": LINKBACK}, fields=["source_endpoint", "source_event_id"])[0]
		self.assertEqual(ev["source_endpoint"], "deal_cost_sheet.on_submit")
		self.assertTrue(ev["source_event_id"])
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.dcs.name, "docstatus"), 2)
		self.assertEqual(float(new.total_cost), 1200.0)
		self.assertEqual(float(new.total_selling), 1500.0)

	def test_selling_change_on_amendment_still_advances_to_submitted_to_sales(self):
		q = make_quotation_for(self.dcs)
		new = amend(self.dcs)
		new.items[0].selling_rate = 1600  # selling moved: the quotation no longer stands for this position
		new.save(ignore_permissions=True)
		submit(new)
		self.assertEqual(new.custom_deal_status, "Submitted to Sales")
		# still the sheet's own Draft Quotation with verified identity, so the back-link follows the amendment
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), new.name)
		self.assertEqual(events(new.name, LINKBACK), 1)

	def test_submitted_quotation_is_reported_not_repointed(self):
		q = make_quotation_for(self.dcs)
		frappe.db.set_value("Quotation", q.name, "docstatus", 1, update_modified=False)  # fixture shortcut
		new = amend(self.dcs)
		submit(new)
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), self.dcs.name)  # unchanged
		self.assertEqual(events(new.name, LINKBACK), 0)
		self.assertEqual(quotation_versions(q.name), 0)
		self.assertEqual(stale_reports(new.name), 1)
		c = frappe.get_all("Comment", filters={"reference_name": new.name, "comment_type": "Info"}, fields=["content"])[0]["content"]
		self.assertIn("submitted and is never changed automatically", c)

	def test_quotation_on_another_opportunity_is_reported_not_repointed(self):
		q = make_quotation_for(self.dcs)
		other = make_dcs(suffix=frappe.generate_hash(length=6), submit=False)
		frappe.db.set_value("Quotation", q.name, "opportunity", other.opportunity, update_modified=False)  # fixture shortcut
		self.assertFalse(quotation_relationship_intact(frappe.get_doc("Deal Cost Sheet", self.dcs.name)))
		new = amend(self.dcs)
		submit(new)
		self.assertEqual(new.custom_deal_status, "Submitted to Sales")
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), self.dcs.name)
		self.assertEqual(events(new.name, LINKBACK), 0)
		self.assertEqual(stale_reports(new.name), 1)
		c = frappe.get_all("Comment", filters={"reference_name": new.name, "comment_type": "Info"}, fields=["content"])[0]["content"]
		self.assertIn("not on this sheet's Opportunity", c)

	def test_quotation_on_the_opportunity_party_is_compatible_when_sheet_party_moved(self):
		q = make_quotation_for(self.dcs)
		moved = make_customer("MOVED")
		frappe.db.set_value("Deal Cost Sheet", self.dcs.name, {"party": moved, "customer": moved}, update_modified=False)  # fixture shortcut
		new = amend(self.dcs)
		submit(new)
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), new.name)
		self.assertEqual(events(new.name, LINKBACK), 1)
		self.assertEqual(stale_reports(new.name), 0)

	def test_another_sheets_quotation_is_neither_repointed_nor_reported(self):
		q = make_quotation_for(self.dcs)
		other = make_dcs(suffix=frappe.generate_hash(length=6), submit=True)
		frappe.db.set_value("Quotation", q.name, "custom_deal_cost_sheet", other.name, update_modified=False)
		self.assertFalse(quotation_relationship_intact(frappe.get_doc("Deal Cost Sheet", self.dcs.name)))
		new = amend(self.dcs)
		submit(new)
		self.assertEqual(new.custom_deal_status, "Submitted to Sales")
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), other.name)
		self.assertEqual(events(new.name, LINKBACK), 0)
		self.assertEqual(stale_reports(new.name), 0)

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


# ============================================================================ strict flow
class IntegrationTestDCSAmendmentFlow(IntegrationTestCase):
	"""The real amendment flow through the document API: no ignore_links, no ignore_mandatory, no
	db_insert fallback, no direct field writes on the records under test. Still not a browser test."""

	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		governance.reset_correlation_id()

	def test_cost_only_amendment_flow_keeps_quoted_and_repoints_the_draft_quotation(self):
		# base sheet: fixture scaffolding (Customer / Opportunity rows), then a real, flag-free submit
		dcs = make_dcs(suffix="FLOW-" + frappe.generate_hash(length=5), submit=False)
		dcs.submit()
		dcs.reload()
		self.assertEqual(dcs.docstatus, 1)
		self.assertEqual(dcs.custom_deal_status, "Submitted to Sales")

		# the Quotation exactly as a saved form leaves it - strict document insert
		q = frappe.get_doc(quotation_values(dcs, dcs.total_selling))
		q.insert()
		q.reload()
		self.assertEqual(q.docstatus, 0)
		self.assertEqual(float(q.total), float(dcs.total_selling))
		self.assertEqual(q.custom_deal_cost_sheet, dcs.name)
		# the two-way link and the Quoted status come from the retained "Quotation - Link Back to DCS"
		# Server Script (After Save on Quotation) exactly as in production; no direct write here
		dcs.reload()
		if dcs.custom_quotation != q.name or dcs.custom_deal_status != "Quoted":
			self.skipTest("this site did not run the Quotation After-Save link-back script (server scripts disabled or script absent); the production flow cannot be reproduced without it")
		self.assertTrue(quotation_relationship_intact(dcs))
		m0 = frappe.db.get_value("Quotation", q.name, "modified")

		# cancel -> amend -> save -> submit, exactly as the desk does, no flags
		dcs.cancel()
		new = frappe.copy_doc(dcs)
		new.amended_from = dcs.name
		new.docstatus = 0
		new.items[0].cost_rate = float(dcs.items[0].cost_rate) + 795  # the report's cost-only change
		new.insert()
		self.assertEqual(new.name, dcs.name + "-1")
		self.assertEqual(new.custom_deal_status, "Quoted")
		self.assertEqual(new.custom_quotation, q.name)
		new.submit()
		new.reload()

		self.assertEqual(new.docstatus, 1)
		self.assertEqual(float(new.total_cost), float(dcs.total_cost) + 795)
		self.assertEqual(float(new.total_selling), float(dcs.total_selling))
		self.assertEqual(new.custom_deal_status, "Quoted")
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), new.name)
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "docstatus"), 0)
		self.assertGreater(frappe.db.get_value("Quotation", q.name, "modified"), m0)
		self.assertEqual(events(new.name, LINKBACK), 1)
		self.assertEqual(quotation_versions(q.name), 1)
		self.assertEqual(stale_reports(new.name), 0)
		# the Quotation still saves normally afterwards (no dangling link to a cancelled sheet)
		q.reload()
		q.save()
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_deal_cost_sheet"), new.name)
