"""Staging integration coverage for DCS quotation draft / issue separation.

Real Frappe documents through the document API (validate, submit, hooks) and the real
print pipeline (``frappe.get_print`` / ``frappe.attach_print`` -> printview ->
``before_print`` -> ``pdf_body_html``), with the fixture shortcuts used across the DCS
suite: ZZTEST records, ``ignore_mandatory`` on quotation saves that are not about
mandatory fields, and direct ``db.set_value`` only where a test models a historical
(pre-migration or revision-0) record. No browser and no HTTP. Never run against production.

	bench --site rel1-test.local run-tests --module bsgroup.dcs.test_quote_alignment
"""
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import describe_payment_terms, make_quotation
from bsgroup.dcs import linkback_script, quote_alignment
from bsgroup.dcs.quotation_control import validate_sales_order
from bsgroup.patches.v0_1.dcs_quote_alignment import mark_legacy_evidence
from bsgroup.tests.dcs_fixtures import _any_item, ensure, make_dcs, make_reporting_line, make_user

TERMS = "ZZTEST 100% on delivery"
REV = "bsgroup.api.dcs.negotiation.dcs_apply_revision"
DECIDE = "bsgroup.api.dcs.approval.dcs_approval_decision"
BOQ = "bsgroup.api.dcs.boq_revision.dcs_apply_boq_revision"
CONFIDENTIAL = ("cost", "margin", "gp", "resource")
MARK_TEXT = "NOT FOR CUSTOMER ISSUE"


def keys(value):
	if isinstance(value, dict):
		for k, v in value.items():
			yield str(k)
			yield from keys(v)
	elif isinstance(value, list):
		for v in value:
			yield from keys(v)


class IntegrationTestDCSQuoteAlignment(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()
		for role in ("Presales", "Sales User", "Sales Manager", "Managing Director"):
			ensure("Role", role, {"role_name": role}, insert=False)
		cls.md = make_user("zztest-qa-md@example.com", ["Sales Manager", "Managing Director"])
		cls.manager = make_user("zztest-qa-manager@example.com", ["Employee"])
		cls.presales = make_user("zztest-qa-presales@example.com", ["Presales"])

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		make_reporting_line(self.md, self.manager)
		self.item = _any_item()
		self.uom = frappe.db.get_value("Item", self.item, "stock_uom")
		frappe.db.set_single_value("BS Group Settings", "dcs_addtional_item", self.item)
		# Sample deal: 2 laptops 3000/4000, installation 1500/2000: cost 7500, selling 10000, margin 25%.
		self.doc = make_dcs(suffix=frappe.generate_hash(length=8), submit=True, items=[
			{"item_code": self.item, "qty": 2, "cost_rate": 3000, "selling_rate": 4000, "description": "ZZTEST laptops"},
			{"item_code": self.item, "qty": 1, "cost_rate": 1500, "selling_rate": 2000, "description": "ZZTEST installation"},
		])
		self.laptop, self.install = (quote_alignment.row_token(r) for r in self.doc.items)
		self.q = frappe.get_doc("Quotation", make_quotation(self.doc.name, payment_terms=TERMS))

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.flags.ignore_print_permissions = False
		super().tearDown()

	# ------------------------------------------------------------ helpers
	def save(self, q=None):
		q = q or self.q
		q.flags.ignore_mandatory = True
		q.save()
		return q

	def submit(self, q=None):
		q = q or self.q
		q.flags.ignore_mandatory = True
		q.submit()
		return q

	def pack_uom(self):
		"""A real 'pack of 2' unit on the item; ERPNext resets the factor of the stock unit to 1."""
		uom = ensure("UOM", "ZZTEST Pack of 2", {"uom_name": "ZZTEST Pack of 2", "must_be_whole_number": 0})
		item = frappe.get_doc("Item", self.item)
		if not any(r.uom == uom for r in item.uoms):
			item.append("uoms", {"uom": uom, "conversion_factor": 2})
			item.flags.ignore_mandatory = True
			item.save(ignore_permissions=True)
		return uom

	def lines(self, *specs, q=None):
		"""specs: (qty, rate, sources[, 2 for one pack of 2])."""
		q = q or self.q
		q.set("items", [])
		for spec in specs:
			qty, rate, sources = spec[:3]
			pack = len(spec) > 3 and spec[3] == 2
			q.append("items", {"item_code": self.item, "qty": qty, "rate": rate, "price_list_rate": rate,
				"uom": self.pack_uom() if pack else self.uom, "conversion_factor": 2 if pack else 1,
				"custom_dcs_source_rows": sources})

	def revise(self, **args):
		frappe.set_user(self.md)
		r = frappe.call(REV, dcs=self.doc.name, source="Vendor", reason="ZZTEST quote alignment", **args)
		self.assertEqual(r["ok"], 1, r)
		frappe.set_user("Administrator")
		self.doc.reload()

	def decide(self, action):
		frappe.set_user(self.manager)
		try:
			r = frappe.call(DECIDE, dcs=self.doc.name, action=action, reason="ZZTEST " + action)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(r["ok"], 1, r)
		self.doc.reload()

	def redistribute(self):
		self.lines((2, 4500, self.laptop), (1, 1000, self.install))
		self.save()

	def historical_submitted(self):
		"""A quotation submitted before row mapping: modelled by removing mapping in the DB after submit."""
		self.submit()
		for row in self.q.items:
			frappe.db.set_value("Quotation Item", row.name, "custom_dcs_source_rows", None, update_modified=False)
		self.q.reload()
		return self.q

	def status(self):
		return frappe.db.get_value("Deal Cost Sheet", self.doc.name, "custom_deal_status")

	# ------------------------------------------------------------ generation
	def test_generation_maps_rows_and_takes_confirmed_wording(self):
		self.assertEqual([r.custom_dcs_source_rows for r in self.q.items], [self.laptop, self.install])
		self.assertEqual(self.q.custom_payment_terms, TERMS)
		self.assertEqual(self.q.custom_dcs_alignment, "Matching")
		self.assertTrue(quote_alignment.alignment_summary(self.q.name)["issuable"])

	def test_generated_draft_carries_the_values_the_form_derives(self):
		customer = frappe.db.get_value("Customer", self.doc.party, ["customer_name"], as_dict=True)
		self.assertEqual(self.q.custom_organization_name, customer.customer_name)
		self.assertEqual(self.q.customer_name, customer.customer_name)

	# ------------------------------------------------------------ finding 6: payment terms
	def template(self, name, days):
		term = ensure("Payment Term", f"{name} term", {"payment_term_name": f"{name} term", "invoice_portion": 100,
			"due_date_based_on": "Day(s) after invoice date", "credit_days": days})
		return ensure("Payment Terms Template", name, {"template_name": name, "terms": [{"payment_term": term,
			"invoice_portion": 100, "due_date_based_on": "Day(s) after invoice date", "credit_days": days}]})

	def test_payment_wording_is_never_substituted(self):
		default = self.template("ZZTEST Net 30", 30)
		frappe.db.set_value("Customer", self.doc.party, "payment_terms", default)
		with self.assertRaisesRegex(frappe.ValidationError, "Payment Terms"):
			make_quotation(self.doc.name)  # a default template exists, but no confirmed wording
		with self.assertRaisesRegex(frappe.ValidationError, "Payment Terms"):
			make_quotation(self.doc.name, payment_terms="   ")
		suggestion = describe_payment_terms(default)
		self.assertEqual(suggestion, "100% ZZTEST Net 30 term, due 30 day(s) after invoice date.")
		self.assertNotEqual(suggestion, default)

	def test_selected_template_differing_from_customer_default(self):
		default, chosen = self.template("ZZTEST Net 30", 30), self.template("ZZTEST Net 60", 60)
		frappe.db.set_value("Customer", self.doc.party, "payment_terms", default)
		q = frappe.get_doc("Quotation", make_quotation(self.doc.name, payment_terms="100% within 60 days of invoice",
			payment_terms_template=chosen))
		self.assertEqual(q.payment_terms_template, chosen)
		self.assertEqual(q.custom_payment_terms, "100% within 60 days of invoice")
		q = frappe.get_doc("Quotation", make_quotation(self.doc.name, payment_terms="As agreed: 100% net 30"))
		self.assertEqual(q.payment_terms_template, default)  # the default drives only the schedule
		self.assertEqual(q.custom_payment_terms, "As agreed: 100% net 30")

	# ------------------------------------------------------------ draft save vs submit (sample cases)
	def test_redistribution_same_total_saves_as_draft_but_cannot_submit(self):
		self.redistribute()
		self.assertEqual(self.q.total, 10000)
		self.assertIn("Repriced", self.q.custom_dcs_alignment)
		with self.assertRaisesRegex(frappe.ValidationError, "scope or selling rates"):
			self.submit()

	def test_selling_cut_saves_as_draft_but_cannot_submit(self):
		self.lines((2, 3600, self.laptop), (1, 1800, self.install))
		self.save()
		summary = quote_alignment.alignment_summary(self.q.name)
		self.assertEqual(summary["variance"], -1000)
		self.assertIn("request_revision", summary["actions"])
		with self.assertRaisesRegex(frappe.ValidationError, "selling total"):
			self.submit()

	def test_quantity_increase_same_total_cannot_submit(self):
		self.lines((4, 2000, self.laptop), (1, 2000, self.install))
		self.save()
		self.assertIn("Scope changed", self.q.custom_dcs_alignment)
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	def test_descriptions_and_order_are_presentation(self):
		self.q.items[0].description = "ZZTEST Business laptops, 3-year warranty"
		self.q.items.reverse()
		for i, r in enumerate(self.q.items, 1):
			r.idx = i
		self.save()
		self.submit()

	# ------------------------------------------------------------ finding 1: no grandfathering by removal
	def test_removing_all_mappings_with_uom_change_cannot_submit(self):
		self.lines((2, 4000, None, 2), (1, 2000, None))  # 2 x unit-of-2 = 4 laptops, same total
		self.save()
		self.assertEqual(self.q.items[0].stock_qty, 4)
		self.assertIn("Scope changed", self.q.custom_dcs_alignment)
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	def test_removing_mappings_from_an_exact_copy_cannot_submit(self):
		self.lines((2, 4000, None), (1, 2000, None))
		self.save()
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	def test_partial_mapping_removal_cannot_submit(self):
		self.lines((2, 4000, self.laptop, 2), (1, 2000, None))
		self.save()
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	def test_uom_conversion_with_mapping_is_checked_in_stock_quantity(self):
		self.lines((1, 8000, self.laptop, 2), (1, 2000, self.install))  # 1 x pack of 2 = 2 laptops
		self.save()
		self.assertEqual(self.q.items[0].stock_qty, 2)
		self.submit()
		self.assertEqual(self.q.docstatus, 1)

	def test_legacy_basis_cannot_be_forged_through_api(self):
		self.lines((2, 4000, None), (1, 2000, None))
		self.q.custom_dcs_legacy_basis = "forged"
		self.save()
		self.assertFalse(frappe.db.get_value("Quotation", self.q.name, "custom_dcs_legacy_basis"))
		with self.assertRaises(frappe.ValidationError):
			self.submit()
		# A REST PUT is the same document save: a fresh copy with the forged field is also cleared.
		copy = frappe.get_doc("Quotation", self.q.name)
		copy.update({"custom_dcs_legacy_basis": "forged"})
		self.save(copy)
		self.assertFalse(frappe.db.get_value("Quotation", self.q.name, "custom_dcs_legacy_basis"))

	def test_legacy_sales_order_rule_needs_migration_evidence(self):
		q = self.historical_submitted()
		order = frappe.get_doc({"doctype": "Sales Order", "items": [{"prevdoc_docname": q.name}]})
		with self.assertRaises(frappe.ValidationError):
			validate_sales_order(order)  # unmapped and no evidence
		self.assertIn(q.name, mark_legacy_evidence())
		self.assertNotIn(q.name, mark_legacy_evidence(), "idempotent")
		validate_sales_order(order)  # the unchanged pre-mapping rule for the recorded historical record
		basis = frappe.db.get_value("Quotation", q.name, "custom_dcs_legacy_basis")
		with self.assertRaises(frappe.ValidationError):
			frappe.client.set_value("Quotation", q.name, "custom_dcs_legacy_basis", "")
		self.assertEqual(frappe.db.get_value("Quotation", q.name, "custom_dcs_legacy_basis"), basis)

	def test_resubmission_of_a_legacy_record_needs_mapping(self):
		q = self.historical_submitted()
		mark_legacy_evidence()
		q.reload()
		self.assertTrue(q.custom_dcs_legacy_basis)
		# A replacement copy of the historical offer (copy_doc keeps no_copy fields, like an amendment).
		amended = frappe.copy_doc(q)
		amended.docstatus = 0
		self.save(amended)
		self.assertFalse(amended.custom_dcs_legacy_basis)
		with self.assertRaises(frappe.ValidationError):
			self.submit(amended)
		amended.reload()
		for row, token in zip(amended.items, (self.laptop, self.install), strict=True):
			row.custom_dcs_source_rows = token
		amended.custom_dcs_revision_reference = None
		self.save(amended)
		self.submit(amended)

	# ------------------------------------------------------------ finding 3: one package per bundle
	def test_mapped_bundle_with_exact_coverage_submits(self):
		self.lines((1, 10000, f"{self.laptop},{self.install}"))
		self.save()
		self.assertEqual(self.q.custom_dcs_alignment, "Matching, Bundled")
		self.submit()

	def test_bundle_multiplier_and_conversion_cannot_submit(self):
		for spec in ((4, 2500, f"{self.laptop},{self.install}"), (1, 10000, f"{self.laptop},{self.install}", 2)):
			self.q.reload()
			self.lines(spec)
			self.save()
			self.assertIn("Scope changed", self.q.custom_dcs_alignment, spec)
			with self.assertRaises(frappe.ValidationError):
				self.submit()

	def test_zero_and_negative_quantities_are_refused_at_draft_save(self):
		for qty in (0, -1):
			self.q.reload()
			self.lines((qty, 10000, f"{self.laptop},{self.install}"))
			with self.assertRaises(frappe.ValidationError):
				self.save()

	def test_charge_bundle_is_one_package(self):
		doc = make_dcs(suffix=frappe.generate_hash(length=8), submit=True,
			addtional_charges=[{"amount": 100, "selling_amount": 150}, {"amount": 50, "selling_amount": 60}])
		q = frappe.get_doc("Quotation", make_quotation(doc.name, payment_terms=TERMS))
		self.assertEqual(q.custom_dcs_alignment, "Matching")
		q.items[-1].qty = 3
		q.items[-1].rate = 70
		self.save(q)
		with self.assertRaises(frappe.ValidationError):
			self.submit(q)

	def test_duplicate_unknown_and_malformed_mapping(self):
		self.lines((2, 4000, self.laptop), (1, 2000, self.laptop))
		self.save()
		with self.assertRaises(frappe.ValidationError):
			self.submit()
		self.q.reload()
		self.lines((2, 4000, self.laptop), (1, 2000, "ZZFOREIGN1"))
		self.save()
		with self.assertRaises(frappe.ValidationError):
			self.submit()
		self.q.reload()
		self.lines((2, 4000, self.laptop), (1, 2000, "<script>"))
		with self.assertRaisesRegex(frappe.ValidationError, "malformed"):
			self.save()

	# ------------------------------------------------------------ discount paths
	def test_document_discount_cannot_be_issued(self):
		self.q.additional_discount_percentage = 10
		self.save()
		self.assertIn("Total changed", self.q.custom_dcs_alignment)
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	def test_line_discount_cannot_be_issued(self):
		# Same 4000 net rate, presented as 5000 less 20%: a fictitious discount on the offer.
		self.q.items[0].update({"price_list_rate": 5000, "discount_percentage": 20, "rate": 4000})
		self.save()
		self.assertEqual(self.q.items[0].amount, 8000)
		self.assertIn("Repriced", self.q.custom_dcs_alignment)
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	# ------------------------------------------------------------ finding 2: authority incl. revision 0
	def as_revision_zero(self, **state):
		"""Models a legacy sheet submitted before living positions existed."""
		frappe.db.set_value("Deal Cost Sheet", self.doc.name, {"custom_dcs_revision_no": 0, **state}, update_modified=False)
		self.doc.reload()

	def test_revision_zero_states_follow_existing_policy(self):
		cases = (
			({"custom_approval_state": "Rejected", "custom_approval_required": "Manager"}, "rejected"),
			({"custom_approval_state": "Returned for Rework", "custom_approval_required": "Manager"}, "returned"),
			({"custom_approval_state": "Pending Manager", "custom_approval_required": "Manager"}, "approval"),
			({"custom_approval_state": "Blocked", "custom_approval_required": "Blocked"}, "blocked"),
			({"custom_approval_state": "Mystery", "custom_approval_required": "None"}, "not a clear state"),
		)
		for state, text in cases:
			self.as_revision_zero(**state)
			self.assertIn(text, quote_alignment.authority_problem(self.doc), state)
		self.as_revision_zero(custom_approval_state="Not Started", custom_approval_required="None")
		self.assertEqual(quote_alignment.authority_problem(self.doc), "")
		self.as_revision_zero(custom_approval_state="Approved", custom_approval_required="Manager",
			custom_approved_by=self.manager, custom_approved_total_selling=10000, custom_approved_total_cost=7500)
		self.assertEqual(quote_alignment.authority_problem(self.doc), "")
		self.as_revision_zero(custom_approved_total_cost=7000)
		self.assertIn("does not match", quote_alignment.authority_problem(self.doc))

	def test_revision_zero_rejected_cannot_submit_a_matching_quotation(self):
		self.as_revision_zero(custom_approval_state="Rejected", custom_approval_required="Manager")
		with self.assertRaisesRegex(frappe.ValidationError, "rejected"):
			self.submit()

	def test_revision_zero_below_floor_needs_recorded_approval(self):
		frappe.db.set_value("Deal Cost Sheet", self.doc.name, "total_cost", 9000, update_modified=False)  # margin 10%
		self.as_revision_zero(custom_approval_state="", custom_approval_required="")
		self.assertIn("approval", quote_alignment.authority_problem(self.doc))

	def test_rejected_position_requires_fresh_approval_before_issue(self):
		self.revise(new_total_cost=8500)  # margin 15%: manager approval required
		quote_alignment.review_revision(self.q.name)
		self.q.reload()
		with self.assertRaisesRegex(frappe.ValidationError, "approval"):
			self.submit()
		self.q.reload()
		self.decide("Reject")
		with self.assertRaisesRegex(frappe.ValidationError, "rejected"):
			self.submit()
		self.q.reload()
		self.revise(new_total_cost=8400)
		self.decide("Approve")
		quote_alignment.review_revision(self.q.name)
		self.q.reload()
		self.submit()

	# ------------------------------------------------------------ finding 8: revisions are reviewed explicitly
	def test_cost_only_revision_stays_stale_until_reviewed(self):
		before = self.q.custom_dcs_revision_reference
		self.revise(new_total_cost=7600)
		self.save()  # an unrelated save does not acknowledge the revision
		self.assertEqual(self.q.custom_dcs_revision_reference, before)
		self.assertIn("Stale", self.q.custom_dcs_alignment)
		self.assertIn("review_revision", quote_alignment.alignment_summary(self.q.name)["actions"])
		with self.assertRaisesRegex(frappe.ValidationError, "stale"):
			self.submit()
		self.q.reload()
		r = quote_alignment.review_revision(self.q.name)
		self.assertEqual(r["changed"], 1)
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": self.q.name, "content": ["like", "%DCS revision reviewed%"]}))
		self.q.reload()
		self.assertEqual(self.q.custom_dcs_revision_reference, self.doc.custom_revision_reference)
		self.submit()

	def test_same_total_scope_revision_still_blocks_after_review(self):
		from bsgroup.api.dcs.test_dcs_boq_revision import payload
		values = payload(self.doc)
		values["items"][0].update(qty=4, selling_rate=2000)  # laptops 4 x 2000: same 10000 total
		frappe.set_user(self.md)
		r = frappe.call(BOQ, dcs=self.doc.name, expected_modified=str(self.doc.modified), source="Customer",
			reason="ZZTEST same-total scope change", acknowledge_quote_review=1, **values)
		frappe.set_user("Administrator")
		self.assertEqual(r["ok"], 1, r)
		self.save()
		self.assertIn("Stale", self.q.custom_dcs_alignment)
		quote_alignment.review_revision(self.q.name)
		self.q.reload()
		self.assertIn("Scope changed", self.q.custom_dcs_alignment)
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	# ------------------------------------------------------------ finding 5: customer output
	def test_unapproved_draft_is_marked_in_standard_and_custom_formats(self):
		self.redistribute()
		html = frappe.get_print("Quotation", self.q.name, "Standard")
		self.assertIn(MARK_TEXT, html)
		fmt = ensure("Print Format", "ZZTEST Quotation Plain", {"doc_type": "Quotation", "custom_format": 1,
			"print_format_type": "Jinja", "standard": "No", "html": "<h1>Offer {{ doc.name }}</h1>{{ doc.grand_total }}"})
		self.assertIn(MARK_TEXT, frappe.get_print("Quotation", self.q.name, fmt))
		if frappe.db.exists("Print Format", "Enterprise Quotation format 2"):
			self.assertIn(MARK_TEXT, frappe.get_print("Quotation", self.q.name, "Enterprise Quotation format 2"))

	def test_aligned_submitted_offer_prints_unmarked(self):
		self.submit()
		self.assertNotIn(MARK_TEXT, frappe.get_print("Quotation", self.q.name, "Standard"))

	def test_attachment_and_email_paths_refuse_unapproved(self):
		self.redistribute()
		with self.assertRaises(frappe.ValidationError):
			frappe.attach_print("Quotation", self.q.name, print_format="Standard")
		count = frappe.db.count("Communication", {"reference_name": self.q.name})
		for args in ({"print_format": "Standard"}, {"print_html": "<p>forged</p>"}):
			with self.assertRaises(frappe.ValidationError):
				quote_alignment.make_communication(doctype="Quotation", name=self.q.name, recipients="zztest@example.com",
					subject="ZZTEST", content="x", send_email=1, **args)
		self.assertEqual(frappe.db.count("Communication", {"reference_name": self.q.name}), count)
		self.assertEqual(frappe.get_hooks("override_whitelisted_methods")["frappe.core.doctype.communication.email.make"][-1],
			"bsgroup.dcs.quote_alignment.make_communication")

	def test_beta_builder_formats_are_refused_for_unapproved(self):
		beta = frappe.db.get_value("Print Format", {"doc_type": "Quotation", "print_format_builder_beta": 1, "disabled": 0}, "name") \
			or ensure("Print Format", "ZZTEST Quotation Beta", {"doc_type": "Quotation", "standard": "No",
				"print_format_builder_beta": 1, "format_data": "{}", "print_format_type": "Jinja"})
		self.redistribute()
		frappe.set_user(self.md)  # Administrator bypasses controller permissions
		with patch.object(frappe.local, "form_dict", frappe._dict(format=beta)):
			self.assertFalse(self.q.has_permission("print"))
		with patch.object(frappe.local, "form_dict", frappe._dict(format="Standard")):
			self.assertTrue(self.q.has_permission("print"), "markable formats stay printable, with the mark")
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			quote_alignment.on_print_pdf(doctype="Quotation", name=self.q.name, print_format=beta)
		self.submit_aligned_copy_and_check_beta(beta)

	def submit_aligned_copy_and_check_beta(self, beta):
		q = frappe.get_doc("Quotation", make_quotation(self.doc.name, payment_terms=TERMS))
		self.submit(q)
		frappe.set_user(self.md)
		try:
			with patch.object(frappe.local, "form_dict", frappe._dict(format=beta)):
				self.assertTrue(q.has_permission("print"))
		finally:
			frappe.set_user("Administrator")

	def test_superseded_and_subsequently_unapproved_offers_are_marked(self):
		self.submit()
		self.revise(new_total_cost=8500)  # supersedes the offer and needs approval
		self.q.reload()
		self.assertTrue(self.q.custom_dcs_superseded_revision)
		self.assertIn(MARK_TEXT, frappe.get_print("Quotation", self.q.name, "Standard"))
		with self.assertRaises(frappe.ValidationError):
			frappe.attach_print("Quotation", self.q.name, print_format="Standard")
		self.q.custom_pipeline_stage = "Sent"
		with self.assertRaises(frappe.ValidationError):
			self.q.save()

	def test_confidential_fields_never_print(self):
		self.submit()
		html = frappe.get_print("Quotation", self.q.name, "Standard")
		self.assertNotIn("1,500.00", html)  # installation cost rate
		self.assertNotIn("3,000.00", html)  # laptop cost rate
		leaky = ensure("Print Format", "ZZTEST Quotation Leaky", {"doc_type": "Quotation", "custom_format": 1,
			"print_format_type": "Jinja", "standard": "No", "html": "{% for i in doc.items %}{{ i.custom_cost_rate }}{% endfor %}"})
		with self.assertRaisesRegex(frappe.ValidationError, "internal commercial data"):
			frappe.get_print("Quotation", self.q.name, leaky)

	# ------------------------------------------------------------ finding 4 and confidentiality
	def test_mapping_labels_distinguish_generic_rows(self):
		rows = quote_alignment.source_rows(self.q.name)["rows"]
		labels = [r["label"] for r in rows]
		self.assertEqual(labels[0], f"Row 1: ZZTEST laptops - 2 {self.uom}")
		self.assertEqual(labels[1], f"Row 2: ZZTEST installation - 1 {self.uom}")

	def test_summary_and_source_rows_never_expose_cost_or_internal_rows(self):
		doc = make_dcs(suffix=frappe.generate_hash(length=8), submit=True,
			resources=[{"resource_type": "Internal", "role": "ZZTEST consultant", "no_of_persons": 1, "no_of_days": 2, "cost_rate": 10}],
			addtional_charges=[{"amount": 30, "description": "ZZTEST internal expense", "selling_amount": 0},
				{"amount": 100, "description": "ZZTEST freight note", "selling_amount": 150}])
		q = frappe.get_doc("Quotation", make_quotation(doc.name, payment_terms=TERMS))
		internal = [quote_alignment.row_token(r) for r in doc.addtional_charges if not r.selling_amount]
		for payload in (quote_alignment.alignment_summary(q.name), quote_alignment.source_rows(q.name)):
			for key in keys(payload):
				self.assertFalse(any(word in key.lower() for word in CONFIDENTIAL), key)
			text = frappe.as_json(payload)
			for secret in (internal[0], "ZZTEST consultant", "ZZTEST internal expense", "ZZTEST freight note"):
				self.assertNotIn(secret, text)
		self.assertTrue(quote_alignment.alignment_summary(q.name)["issuable"])

	def test_mapping_endpoints_follow_quotation_permissions(self):
		frappe.set_user(self.presales)
		with self.assertRaises(frappe.PermissionError):
			quote_alignment.source_rows(self.q.name)
		with self.assertRaises(frappe.PermissionError):
			quote_alignment.review_revision(self.q.name)

	# ------------------------------------------------------------ finding 7: prepared, ready, issued
	def test_status_prepared_ready_issued(self):
		self.save()
		self.assertEqual(self.status(), "Submitted to Sales")  # prepared
		self.submit()
		self.assertEqual(self.status(), "Submitted to Sales")  # approved / ready, not sent
		self.q.custom_pipeline_stage = "Sent"
		self.q.save()
		self.assertEqual(self.status(), "Quoted")  # documented issue
		self.q.reload()
		self.q.add_comment("Info", "ZZTEST follow-up")
		self.q.custom_pipeline_stage = "Follow-up"
		self.q.save()
		self.assertEqual(self.status(), "Quoted")
		# Superseding the only issued offer returns the deal to Submitted to Sales on the next event.
		frappe.db.set_value("Quotation", self.q.name, "custom_dcs_superseded_revision", "ZZTEST-REV", update_modified=False)
		quote_alignment.sync_quote_status(self.q)
		self.assertEqual(self.status(), "Submitted to Sales")

	def test_drafts_cannot_be_marked_sent(self):
		self.q.custom_pipeline_stage = "Sent"
		with self.assertRaisesRegex(frappe.ValidationError, "Submit the quotation"):
			self.save()

	def test_won_lost_and_historical_status_are_preserved(self):
		frappe.db.set_value("Deal Cost Sheet", self.doc.name, "custom_deal_status", "Won", update_modified=False)
		self.save()
		self.assertEqual(self.status(), "Won")
		frappe.db.set_value("Deal Cost Sheet", self.doc.name, "custom_deal_status", "Quoted", update_modified=False)
		q = self.historical_submitted()
		mark_legacy_evidence()
		q.reload()
		quote_alignment.sync_quote_status(q)
		self.assertEqual(self.status(), "Quoted", "a pre-mapping submitted offer still counts as issued")

	def test_linkback_script_migration_is_hash_checked_and_reversible(self):
		from bsgroup.patches.v0_1 import dcs_quote_status_owner as patch_module
		current = frappe.db.get_value("Server Script", linkback_script.NAME, "script")
		decision = linkback_script.plan(current)
		if decision == "absent":
			self.skipTest("link-back Server Script not present on this site")
		if decision == "customised":
			self.assertEqual(patch_module.execute(), "customised")
			self.assertEqual(frappe.db.get_value("Server Script", linkback_script.NAME, "script"), current)
			return
		if decision == "convert":
			self.assertEqual(patch_module.execute(), "convert")
		self.assertEqual(linkback_script.sha256(frappe.db.get_value("Server Script", linkback_script.NAME, "script")),
			linkback_script.converted_sha256())
		self.assertEqual(patch_module.execute(), "already")
		self.assertTrue(patch_module.revert())
		self.assertEqual(linkback_script.sha256(frappe.db.get_value("Server Script", linkback_script.NAME, "script")),
			linkback_script.ORIGINAL_SHA256)
		if decision == "already":
			patch_module.execute()
