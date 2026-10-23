"""Staging integration coverage for DCS quotation draft / issue separation.

Real Frappe documents through the document API (validate, submit, hooks), with
the fixture shortcuts used across the DCS suite: ZZTEST records,
``ignore_mandatory`` on quotation saves that are not about mandatory fields
(site-specific mandatory fields are covered elsewhere), no browser and no HTTP.
Never run against production.

	bench --site rel1-test.local run-tests --module bsgroup.dcs.test_quote_alignment
"""
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation
from bsgroup.dcs import quote_alignment
from bsgroup.dcs.quotation_control import validate_sales_order
from bsgroup.tests.dcs_fixtures import _any_item, ensure, make_dcs, make_reporting_line, make_user

TERMS = "ZZTEST 100% on delivery"
REV = "bsgroup.api.dcs.negotiation.dcs_apply_revision"
DECIDE = "bsgroup.api.dcs.approval.dcs_approval_decision"
CONFIDENTIAL = ("cost", "margin", "gp", "resource")


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

	def lines(self, *specs):
		"""specs: (qty, rate, sources)."""
		self.q.set("items", [])
		for qty, rate, sources in specs:
			self.q.append("items", {"item_code": self.item, "qty": qty, "rate": rate, "price_list_rate": rate,
				"uom": frappe.db.get_value("Item", self.item, "stock_uom"), "conversion_factor": 1,
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

	# ------------------------------------------------------------ generation
	def test_generation_maps_rows_and_sets_existing_payment_terms(self):
		self.assertEqual([r.custom_dcs_source_rows for r in self.q.items], [self.laptop, self.install])
		self.assertEqual(self.q.custom_payment_terms, TERMS)
		self.assertEqual(self.q.custom_dcs_alignment, "Matching")
		self.assertTrue(quote_alignment.alignment_summary(self.q.name)["issuable"])

	def test_generation_refuses_without_payment_terms_or_default(self):
		self.assertFalse(frappe.db.get_value("Customer", self.doc.party, "payment_terms"))
		with self.assertRaisesRegex(frappe.ValidationError, "Payment Terms"):
			make_quotation(self.doc.name)

	def test_generation_uses_the_partys_existing_payment_terms_template(self):
		term = ensure("Payment Term", "ZZTEST 100 Net 30", {"payment_term_name": "ZZTEST 100 Net 30",
			"invoice_portion": 100, "due_date_based_on": "Day(s) after invoice date", "credit_days": 30})
		template = ensure("Payment Terms Template", "ZZTEST Net 30", {"template_name": "ZZTEST Net 30",
			"terms": [{"payment_term": term, "invoice_portion": 100, "due_date_based_on": "Day(s) after invoice date", "credit_days": 30}]})
		frappe.db.set_value("Customer", self.doc.party, "payment_terms", template)
		q = frappe.get_doc("Quotation", make_quotation(self.doc.name))
		self.assertEqual(q.payment_terms_template, template)
		self.assertEqual(q.custom_payment_terms, template)

	def test_generated_draft_carries_the_values_the_form_derives(self):
		customer = frappe.db.get_value("Customer", self.doc.party, ["customer_name"], as_dict=True)
		self.assertEqual(self.q.custom_organization_name, customer.customer_name)
		self.assertEqual(self.q.customer_name, customer.customer_name)

	# ------------------------------------------------------------ draft save vs submit
	def test_redistribution_same_total_saves_as_draft_but_cannot_submit(self):
		self.lines((2, 4500, self.laptop), (1, 1000, self.install))
		self.save()
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

	def test_mapped_bundle_with_exact_coverage_submits(self):
		self.lines((1, 10000, f"{self.laptop},{self.install}"))
		self.save()
		self.assertEqual(self.q.custom_dcs_alignment, "Matching, Bundled")
		self.submit()
		self.assertEqual(self.q.docstatus, 1)

	def test_unmapped_same_total_bundle_cannot_submit(self):
		self.lines((1, 10000, None))
		self.save()
		with self.assertRaises(frappe.ValidationError):
			self.submit()

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

	def test_descriptions_and_order_are_presentation(self):
		self.q.items[0].description = "ZZTEST Business laptops, 3-year warranty"
		self.q.items.reverse()
		for i, r in enumerate(self.q.items, 1):
			r.idx = i
		self.save()
		self.submit()

	# ------------------------------------------------------------ discount paths
	def test_document_discount_cannot_be_issued(self):
		self.q.additional_discount_percentage = 10
		self.save()
		self.assertIn("Total changed", self.q.custom_dcs_alignment)
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	def test_line_discount_cannot_be_issued(self):
		self.q.items[0].discount_percentage = 10
		self.save()
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	def test_fixed_tax_row_deduction_cannot_be_issued(self):
		account = frappe.db.get_value("Account", {"company": self.q.company, "is_group": 0, "account_type": "Tax"}, "name")
		if not account:
			self.skipTest("no Tax account on this company")
		self.q.append("taxes", {"charge_type": "Actual", "account_head": account, "description": "ZZTEST deduction", "tax_amount": -500})
		self.save()
		with self.assertRaises(frappe.ValidationError):
			self.submit()

	# ------------------------------------------------------------ revisions and authority
	def test_stale_revision_cannot_be_issued(self):
		self.revise(new_total_selling=9500)  # totals-only negotiation: living total leaves the rows
		with self.assertRaises(frappe.ValidationError):
			self.submit()
		self.q.reload()
		self.save()  # the draft still saves and reports the difference
		self.assertIn("Stale", self.q.custom_dcs_alignment)

	def test_rejected_position_requires_fresh_approval_before_issue(self):
		self.revise(new_total_cost=8500)  # margin 15%: below the floor, manager approval required
		self.save()
		with self.assertRaisesRegex(frappe.ValidationError, "approval"):
			self.submit()
		self.q.reload()
		self.decide("Reject")
		self.save()
		with self.assertRaisesRegex(frappe.ValidationError, "rejected"):
			self.submit()
		self.q.reload()
		self.revise(new_total_cost=8400)
		self.decide("Approve")
		self.save()
		self.submit()
		self.assertEqual(self.q.docstatus, 1)

	def test_sales_order_gate_still_requires_authority(self):
		self.submit()
		self.revise(new_total_cost=8500)
		order = frappe.get_doc({"doctype": "Sales Order", "items": [{"prevdoc_docname": self.q.name}]})
		with self.assertRaises(frappe.ValidationError):
			validate_sales_order(order)

	# ------------------------------------------------------------ issue paths
	def test_unaligned_draft_cannot_be_marked_sent(self):
		self.lines((2, 4500, self.laptop), (1, 1000, self.install))
		self.q.custom_pipeline_stage = "Sent"
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be marked Sent"):
			self.save()

	def test_print_and_email_guard(self):
		self.lines((2, 4500, self.laptop), (1, 1000, self.install))
		self.save()
		with patch.object(frappe, "form_dict", frappe._dict(format="Enterprise Quotation format 2")):
			quote_alignment.before_print(self.q)
		self.assertTrue(self.q.flags.dcs_issue_block)
		with patch.object(frappe, "form_dict", frappe._dict(format="ZZTEST Unknown Format")):
			with self.assertRaises(frappe.ValidationError):
				quote_alignment.before_print(self.q)
		frappe.flags.ignore_print_permissions = True  # frappe.attach_print sets this for email attachments
		with self.assertRaisesRegex(frappe.ValidationError, "email"):
			quote_alignment.before_print(self.q)
		frappe.flags.ignore_print_permissions = False
		if frappe.db.exists("Print Format", "Enterprise Quotation format 2"):
			html = frappe.get_print("Quotation", self.q.name, "Enterprise Quotation format 2")
			self.assertIn("NOT FOR CUSTOMER ISSUE", html)

	def test_aligned_draft_prints_without_block(self):
		quote_alignment.before_print(self.q)
		self.assertFalse(self.q.flags.get("dcs_issue_block"))

	# ------------------------------------------------------------ confidentiality and permissions
	def test_summary_and_source_rows_never_expose_cost_or_internal_rows(self):
		doc = make_dcs(suffix=frappe.generate_hash(length=8), submit=True,
			resources=[{"resource_type": "Internal", "role": "ZZTEST consultant", "no_of_persons": 1, "no_of_days": 2, "cost_rate": 900}],
			addtional_charges=[{"amount": 300, "description": "ZZTEST internal expense", "selling_amount": 0},
				{"amount": 100, "description": "ZZTEST freight", "selling_amount": 150}])
		q = frappe.get_doc("Quotation", make_quotation(doc.name, payment_terms=TERMS))
		internal = [quote_alignment.row_token(r) for r in doc.addtional_charges if not r.selling_amount]
		for payload in (quote_alignment.alignment_summary(q.name), quote_alignment.source_rows(q.name)):
			for key in keys(payload):
				self.assertFalse(any(word in key.lower() for word in CONFIDENTIAL), key)
			self.assertNotIn(internal[0], frappe.as_json(payload))
			self.assertNotIn("ZZTEST consultant", frappe.as_json(payload))
		self.assertTrue(quote_alignment.alignment_summary(q.name)["issuable"])
		for row in q.items:
			self.assertNotIn(internal[0], row.custom_dcs_source_rows or "")

	def test_mapping_endpoints_follow_quotation_permissions(self):
		frappe.set_user(self.presales)
		with self.assertRaises(frappe.PermissionError):
			quote_alignment.source_rows(self.q.name)

	# ------------------------------------------------------------ legacy
	def test_legacy_unmapped_quotation_keeps_previous_behaviour(self):
		for row in self.q.items:
			row.custom_dcs_source_rows = None
		self.save()
		self.assertEqual(self.q.custom_dcs_alignment, "Matching")
		self.submit()
		# An already-submitted legacy quotation is judged by the unchanged pre-mapping rule.
		order = frappe.get_doc({"doctype": "Sales Order", "items": [{"prevdoc_docname": self.q.name}]})
		validate_sales_order(order)

	# ------------------------------------------------------------ prepared vs issued
	def test_draft_save_never_marks_the_deal_quoted(self):
		# Model the After-Save link-back Server Script, which writes "Quoted" on every save.
		frappe.db.set_value("Deal Cost Sheet", self.doc.name, {"custom_deal_status": "Quoted", "custom_quotation": self.q.name})
		self.save()
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.doc.name, "custom_deal_status"), "Submitted to Sales")
		self.submit()
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.doc.name, "custom_deal_status"), "Quoted")
		self.q.cancel()
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.doc.name, "custom_deal_status"), "Submitted to Sales")

	def test_source_keys_survive_amendment(self):
		doc = make_dcs(suffix=frappe.generate_hash(length=8), submit=True)
		before = [r.source_key for r in doc.items]
		self.assertEqual(before, [r.name for r in doc.items])
		doc.cancel()
		amended = frappe.copy_doc(doc)
		amended.amended_from = doc.name
		amended.docstatus = 0
		amended.insert()
		self.assertEqual([r.source_key for r in amended.items], before)
		self.assertNotEqual([r.name for r in amended.items], before)
