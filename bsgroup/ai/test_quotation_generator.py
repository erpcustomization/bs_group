# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Frappe integration tests for bsgroup.ai.quotation_generator.

RUN ON A NON-PRODUCTION BENCH ONLY (e.g. dcs-test.local / the rel1 bench):

    bench --site dcs-test.local run-tests --module bsgroup.ai.test_quotation_generator

The Anthropic network call is always patched - no API key and no outbound
request are made. Fixtures are ZZTEST-prefixed and every test is wrapped in a
transaction that FrappeTestCase rolls back, so role/permission changes and any
created records are undone. Covered blockers: no automatic approval bypass
(override must be explicit), real denied users, document-permission and
mandatory-field enforcement, atomic rollback after a database write,
submitted-DCS and tax validation, and preservation of every additional charge.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from bsgroup.ai import quotation_generator
from bsgroup.ai.anthropic_client import AIProviderError

PREFIX = "ZZTEST-AIQ"

FAKE_AI_TEXT = (
	'{"subject":"Wireless network upgrade",'
	'"scope_overview_html":"<p>Supply and installation of the wireless network.</p>",'
	'"customer_notes":"Prices exclude civil works.",'
	'"item_descriptions":[{"line":1,"text":"Enterprise Wi-Fi access point"}],'
	'"needs_input":[]}'
)


def _fake_generate(system_prompt, user_message, config=None, timeout=60):
	return {"text": FAKE_AI_TEXT, "model": "claude-sonnet-4-5", "usage": {}, "stop_reason": "end_turn"}


def _fake_config():
	return {
		"enabled": True, "provider": "Anthropic (Claude)", "model": "claude-sonnet-4-5",
		"max_tokens": 2000, "fallback_to_rules": True, "api_key": "sk-ant-test-not-real",
	}


class AIQuotationTestBase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.skip = False
		try:
			cls.company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
			if not cls.company:
				cls.skip = True
				return
			cls.currency = frappe.db.get_value("Company", cls.company, "default_currency") or "AED"
			cls.customer = cls._ensure_customer()
			cls.item = cls._ensure_item()
		except Exception:
			cls.skip = True

	@classmethod
	def _ensure_customer(cls):
		name = f"{PREFIX}-Customer"
		if not frappe.db.exists("Customer", name):
			frappe.get_doc({"doctype": "Customer", "customer_name": name, "customer_type": "Company"}).insert(
				ignore_permissions=True, ignore_mandatory=True
			)
		return name

	@classmethod
	def _ensure_item(cls):
		code = f"{PREFIX}-AP"
		if not frappe.db.exists("Item", code):
			frappe.get_doc({
				"doctype": "Item", "item_code": code, "item_name": "Test Access Point",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
				"stock_uom": "Nos", "is_stock_item": 0, "is_sales_item": 1,
			}).insert(ignore_permissions=True, ignore_mandatory=True)
		return code

	def _make_opportunity(self, with_party=True):
		opp = frappe.get_doc({
			"doctype": "Opportunity", "opportunity_from": "Customer",
			"party_name": self.customer if with_party else None,
			"company": self.company, "custom_subject": f"{PREFIX} opportunity",
		})
		opp.flags.ignore_mandatory = True
		opp.insert(ignore_permissions=True, ignore_mandatory=True)
		return opp.name

	def _make_dcs(self, cost_rate=100, selling_rate=150, margin_gate="Clear", approval_required="None",
				approval_state="", charges=None, submit=False, with_party=True):
		doc = {
			"doctype": "Deal Cost Sheet",
			"opportunity": self._make_opportunity(with_party=with_party),
			"company": self.company, "currency": self.currency,
			"subject": f"{PREFIX} deal", "scope_overview": "",
			"custom_margin_gate": margin_gate, "custom_approval_required": approval_required,
			"custom_approval_state": approval_state,
			"items": [{
				"item_code": self.item, "item_name": "Test Access Point", "qty": 5,
				"cost_rate": cost_rate, "selling_rate": selling_rate, "description": "",
			}],
		}
		if charges:
			doc["addtional_charges"] = charges
		dcs = frappe.get_doc(doc)
		dcs.flags.ignore_mandatory = True
		dcs.insert(ignore_permissions=True, ignore_mandatory=True)
		if submit:
			try:
				dcs.submit()
			except Exception:
				self.skipTest("this bench refuses to submit a fixture DCS (lifecycle guards)")
		return dcs.name


class TestReadinessGates(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")

	def test_draft_dcs_is_refused(self):
		dcs = self._make_dcs(submit=False)
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 0)
		self.assertEqual(res["blocked"], "dcs_status")

	def test_missing_cost_blocks_and_creates_nothing(self):
		dcs = self._make_dcs(cost_rate=0, submit=True)
		before = frappe.db.count("Quotation")
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["blocked"], "missing_costs")
		self.assertIsNone(res["quotation"])
		self.assertEqual(frappe.db.count("Quotation"), before)

	def test_blocked_margin_gate_blocks(self):
		dcs = self._make_dcs(margin_gate="Blocked", submit=True)
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["blocked"], "approval_gate")

	def test_pending_endorsement_blocks(self):
		dcs = self._make_dcs(approval_state="Pending Endorsement", submit=True)
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["blocked"], "approval_gate")


class TestNoAutomaticOverride(AIQuotationTestBase):
	"""A privileged user is NOT auto-bypassed: without the explicit override
	flag a block still stops generation; the flag is what proceeds."""

	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")

	@patch("bsgroup.ai.quotation_generator._can_override", return_value=True)
	def test_privileged_user_without_flag_is_still_blocked(self, _ov):
		dcs = self._make_dcs(margin_gate="Blocked", submit=True)
		before = frappe.db.count("Quotation")
		res = quotation_generator.generate_quotation_from_dcs(dcs)  # no override_approval
		self.assertEqual(res["ok"], 0)
		self.assertEqual(res["blocked"], "approval_gate")
		self.assertEqual(frappe.db.count("Quotation"), before)

	@patch("bsgroup.ai.anthropic_client.generate", _fake_generate)
	@patch("bsgroup.ai.anthropic_client.get_active_config", _fake_config)
	@patch("bsgroup.ai.quotation_generator._can_override", return_value=True)
	def test_explicit_override_proceeds_and_is_audited(self, _ov):
		dcs = self._make_dcs(margin_gate="Blocked", submit=True)
		res = quotation_generator.generate_quotation_from_dcs(dcs, override_approval=1)
		self.assertEqual(res["ok"], 1)
		self.assertTrue(any("approval" in o for o in res["applied_overrides"]))
		self.assertEqual(frappe.get_doc("Quotation", res["quotation"]).docstatus, 0)


class TestRealDeniedUser(AIQuotationTestBase):
	"""Real user, real roles - no mocking of permissions."""

	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")

	def _reader_user(self):
		from frappe.permissions import add_permission, update_permission_property

		role = "ZZTEST-AIQ-Reader"
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
		# read on DCS, but no Quotation permission at all
		add_permission("Deal Cost Sheet", role, 0)
		update_permission_property("Deal Cost Sheet", role, 0, "read", 1)

		email = "zztest-aiq-reader@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User", "email": email, "first_name": "ZZ Reader",
				"send_welcome_email": 0, "roles": [{"role": role}],
			}).insert(ignore_permissions=True)
		return email

	def test_user_without_quotation_create_is_denied(self):
		try:
			email = self._reader_user()
		except Exception:
			self.skipTest("could not set up a limited role/user on this bench")
		dcs = self._make_dcs(submit=True)
		before = frappe.db.count("Quotation")
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				quotation_generator.generate_quotation_from_dcs(dcs)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Quotation"), before, "no quotation created for a denied user")


class TestAtomicRollback(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")

	@patch("bsgroup.ai.anthropic_client.get_active_config", side_effect=AIProviderError("AI off"))
	def test_real_mandatory_failure_rolls_back(self, _cfg):
		# No party on the opportunity -> quotation.party_name is empty -> with
		# mandatory enforced, insert() raises and the savepoint rolls back.
		dcs = self._make_dcs(submit=True, with_party=False)
		before = frappe.db.count("Quotation")
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 0)
		self.assertEqual(res["blocked"], "insert_failed")
		self.assertEqual(frappe.db.count("Quotation"), before, "a failed insert must leave no orphan draft")

	@patch("bsgroup.ai.anthropic_client.get_active_config", side_effect=AIProviderError("AI off"))
	def test_forced_insert_error_rolls_back(self, _cfg):
		dcs = self._make_dcs(submit=True)
		before = frappe.db.count("Quotation")
		real_build = quotation_generator._build_quotation_doc

		def build_then_explode(dcs_doc, tax_template):
			doc, warns = real_build(dcs_doc, tax_template)
			doc.insert = lambda *a, **k: (_ for _ in ()).throw(frappe.ValidationError("forced"))
			return doc, warns

		with patch("bsgroup.ai.quotation_generator._build_quotation_doc", build_then_explode):
			res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["blocked"], "insert_failed")
		self.assertEqual(frappe.db.count("Quotation"), before)


class TestCompanyTaxResolution(AIQuotationTestBase):
	def test_prefers_company_default_template(self):
		with patch("bsgroup.ai.quotation_generator.frappe.db.get_value", return_value="OM Default VAT"):
			template, warning = quotation_generator._resolve_company_tax_template("Bits Secure IT Infrastructure LLC - OM")
		self.assertEqual(template, "OM Default VAT")
		self.assertIsNone(warning)

	def test_single_template_used_when_no_default(self):
		with patch("bsgroup.ai.quotation_generator.frappe.db.get_value", return_value=None), \
			patch("bsgroup.ai.quotation_generator.frappe.get_all", return_value=["Only Template"]):
			template, warning = quotation_generator._resolve_company_tax_template("AnyCo")
		self.assertEqual(template, "Only Template")
		self.assertIsNone(warning)

	def test_no_template_warns(self):
		with patch("bsgroup.ai.quotation_generator.frappe.db.get_value", return_value=None), \
			patch("bsgroup.ai.quotation_generator.frappe.get_all", return_value=[]):
			template, warning = quotation_generator._resolve_company_tax_template("AnyCo")
		self.assertIsNone(template)
		self.assertIn("No sales-tax template", warning)

	def test_ambiguous_templates_warn(self):
		with patch("bsgroup.ai.quotation_generator.frappe.db.get_value", return_value=None), \
			patch("bsgroup.ai.quotation_generator.frappe.get_all", return_value=["A", "B"]):
			template, warning = quotation_generator._resolve_company_tax_template("AnyCo")
		self.assertIsNone(template)
		self.assertIn("multiple", warning)

	def test_unresolved_tax_blocks_generation(self):
		if self.skip:
			self.skipTest("required masters unavailable")
		dcs = self._make_dcs(submit=True)
		before = frappe.db.count("Quotation")
		with patch("bsgroup.ai.quotation_generator._resolve_company_tax_template", return_value=(None, "No sales-tax template")):
			res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["blocked"], "tax_unresolved")
		self.assertEqual(frappe.db.count("Quotation"), before)


class TestAdditionalChargesPreserved(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")
		# a configured additional-charge item
		self.charge_item = f"{PREFIX}-CHG"
		if not frappe.db.exists("Item", self.charge_item):
			frappe.get_doc({
				"doctype": "Item", "item_code": self.charge_item, "item_name": "Additional Charge",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
				"stock_uom": "Nos", "is_stock_item": 0, "is_sales_item": 1,
			}).insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.set_single_value("BS Group Settings", "dcs_addtional_item", self.charge_item)

	@patch("bsgroup.ai.anthropic_client.get_active_config", side_effect=AIProviderError("AI off"))
	def test_every_additional_charge_becomes_a_line(self, _cfg):
		charges = [
			{"description": "Mobilisation", "amount": 500},
			{"description": "Site handover", "amount": 250},
		]
		dcs = self._make_dcs(charges=charges, submit=True)
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 1)
		q = frappe.get_doc("Quotation", res["quotation"])
		charge_rows = [r for r in q.items if r.item_code == self.charge_item]
		self.assertEqual(len(charge_rows), 2, "each additional charge must be its own line")
		descs = {(r.description or "").strip() for r in charge_rows}
		self.assertIn("Mobilisation", descs)
		self.assertIn("Site handover", descs)
		amounts = sorted(float(r.amount or 0) for r in charge_rows)
		self.assertEqual(amounts, [250.0, 500.0])


class TestGeneration(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")

	@patch("bsgroup.ai.anthropic_client.generate", _fake_generate)
	@patch("bsgroup.ai.anthropic_client.get_active_config", _fake_config)
	def test_happy_path_creates_draft_with_ai_narrative(self):
		dcs = self._make_dcs(submit=True)
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 1)
		self.assertTrue(res["ai_used"])
		q = frappe.get_doc("Quotation", res["quotation"])
		self.assertEqual(q.docstatus, 0)
		self.assertIn("wireless network", (q.custom_scope_overview or "").lower())
		self.assertTrue(any(float(r.rate or 0) == 150 for r in q.items), "selling rate must come from the DCS")
		self.assertTrue(any("access point" in (r.description or "").lower() for r in q.items))

	@patch("bsgroup.ai.anthropic_client.get_active_config", side_effect=AIProviderError("AI analysis is turned off."))
	def test_ai_off_still_produces_deterministic_draft(self, _cfg):
		dcs = self._make_dcs(submit=True)
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 1)
		self.assertFalse(res["ai_used"])
		self.assertEqual(frappe.get_doc("Quotation", res["quotation"]).docstatus, 0)


if __name__ == "__main__":
	unittest.main()
