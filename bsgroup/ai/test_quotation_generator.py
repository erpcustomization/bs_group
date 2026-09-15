# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Frappe integration tests for bsgroup.ai.quotation_generator.

RUN ON A NON-PRODUCTION BENCH ONLY (e.g. dcs-test.local / the rel1 bench):

    bench --site dcs-test.local run-tests --module bsgroup.ai.test_quotation_generator

The Anthropic network call is always patched here - no API key and no outbound
request are made. Fixtures are ZZTEST-prefixed and rolled back by
FrappeTestCase. These tests cover the reviewed blockers: permission
enforcement, atomic rollback (a failed insert leaves no Quotation behind),
company-specific tax resolution, missing-cost flagging (never invention), and a
draft-only (docstatus 0) result.
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
		"enabled": True,
		"provider": "Anthropic (Claude)",
		"model": "claude-sonnet-4-5",
		"max_tokens": 2000,
		"fallback_to_rules": True,
		"api_key": "sk-ant-test-not-real",
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

	def _make_opportunity(self):
		opp = frappe.get_doc({
			"doctype": "Opportunity", "opportunity_from": "Customer", "party_name": self.customer,
			"company": self.company, "custom_subject": f"{PREFIX} opportunity",
		})
		opp.flags.ignore_mandatory = True
		opp.insert(ignore_permissions=True, ignore_mandatory=True)
		return opp.name

	def _make_dcs(self, cost_rate=100, selling_rate=150, margin_gate="Clear", approval_required="None", approval_state=""):
		dcs = frappe.get_doc({
			"doctype": "Deal Cost Sheet",
			"opportunity": self._make_opportunity(),
			"company": self.company,
			"currency": self.currency,
			"subject": f"{PREFIX} deal",
			"scope_overview": "",
			"custom_margin_gate": margin_gate,
			"custom_approval_required": approval_required,
			"custom_approval_state": approval_state,
			"items": [{
				"item_code": self.item, "item_name": "Test Access Point", "qty": 5,
				"cost_rate": cost_rate, "selling_rate": selling_rate, "description": "",
			}],
		})
		dcs.flags.ignore_mandatory = True
		dcs.insert(ignore_permissions=True, ignore_mandatory=True)
		return dcs.name


class TestReadinessGates(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters (Company/Item) unavailable in this site")

	def test_missing_cost_blocks_and_creates_nothing(self):
		dcs = self._make_dcs(cost_rate=0)
		before = frappe.db.count("Quotation")
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 0)
		self.assertEqual(res["blocked"], "missing_costs")
		self.assertIsNone(res["quotation"])
		self.assertTrue(res["missing_costs"])
		self.assertEqual(frappe.db.count("Quotation"), before, "no quotation on a missing-cost block")

	def test_blocked_margin_gate_blocks(self):
		dcs = self._make_dcs(margin_gate="Blocked")
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 0)
		self.assertEqual(res["blocked"], "approval_gate")
		self.assertIsNone(res["quotation"])

	def test_pending_endorsement_blocks(self):
		dcs = self._make_dcs(approval_state="Pending Endorsement")
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 0)
		self.assertEqual(res["blocked"], "approval_gate")

	def test_preview_is_read_only(self):
		dcs = self._make_dcs(cost_rate=0)
		before = frappe.db.count("Quotation")
		res = quotation_generator.preview_dcs_readiness(dcs)
		self.assertFalse(res["ok"])
		self.assertTrue(res["missing_costs"])
		self.assertEqual(frappe.db.count("Quotation"), before)


class TestPermissions(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")

	def _deny(self, target_doctype, target_ptype):
		real = frappe.has_permission

		def guard(*args, **kwargs):
			dt = args[0] if args else kwargs.get("doctype")
			pt = args[1] if len(args) > 1 else kwargs.get("ptype")
			if dt == target_doctype and pt == target_ptype:
				raise frappe.PermissionError(f"denied {dt}/{pt}")
			return real(*args, **kwargs)

		return guard

	def test_dcs_read_permission_enforced(self):
		dcs = self._make_dcs()
		with patch("bsgroup.ai.quotation_generator.frappe.has_permission", self._deny("Deal Cost Sheet", "read")):
			with self.assertRaises(frappe.PermissionError):
				quotation_generator.generate_quotation_from_dcs(dcs)

	def test_quotation_create_permission_enforced(self):
		dcs = self._make_dcs()
		before = frappe.db.count("Quotation")
		with patch("bsgroup.ai.quotation_generator.frappe.has_permission", self._deny("Quotation", "create")):
			with self.assertRaises(frappe.PermissionError):
				quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(frappe.db.count("Quotation"), before, "no quotation created when create is denied")


class TestAtomicRollback(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")

	@patch("bsgroup.ai.anthropic_client.get_active_config", side_effect=Exception("AI off"))
	def test_failed_insert_leaves_no_orphan_draft(self, _cfg):
		dcs = self._make_dcs()
		before = frappe.db.count("Quotation")

		real_build = quotation_generator._build_quotation_doc

		def build_with_exploding_insert(dcs_doc):
			doc, warns = real_build(dcs_doc)

			def boom(*a, **k):
				raise frappe.ValidationError("forced insert failure")

			doc.insert = boom
			return doc, warns

		with patch("bsgroup.ai.quotation_generator._build_quotation_doc", build_with_exploding_insert):
			res = quotation_generator.generate_quotation_from_dcs(dcs)

		self.assertEqual(res["ok"], 0)
		self.assertEqual(res["blocked"], "insert_failed")
		self.assertIsNone(res["quotation"])
		self.assertEqual(frappe.db.count("Quotation"), before, "a failed insert must roll back with no orphan draft")


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

	def test_no_template_warns_and_applies_none(self):
		with patch("bsgroup.ai.quotation_generator.frappe.db.get_value", return_value=None), \
			patch("bsgroup.ai.quotation_generator.frappe.get_all", return_value=[]):
			template, warning = quotation_generator._resolve_company_tax_template("AnyCo")
		self.assertIsNone(template)
		self.assertIn("No sales-tax template", warning)

	def test_ambiguous_templates_warn_and_apply_none(self):
		with patch("bsgroup.ai.quotation_generator.frappe.db.get_value", return_value=None), \
			patch("bsgroup.ai.quotation_generator.frappe.get_all", return_value=["A", "B"]):
			template, warning = quotation_generator._resolve_company_tax_template("AnyCo")
		self.assertIsNone(template)
		self.assertIn("multiple", warning)


class TestGeneration(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters unavailable")

	@patch("bsgroup.ai.anthropic_client.generate", _fake_generate)
	@patch("bsgroup.ai.anthropic_client.get_active_config", _fake_config)
	def test_happy_path_creates_draft_with_ai_narrative(self):
		dcs = self._make_dcs()
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 1)
		self.assertTrue(res["ai_used"])
		self.assertIsNotNone(res["quotation"])

		q = frappe.get_doc("Quotation", res["quotation"])
		self.assertEqual(q.docstatus, 0, "generated quotation must be a draft")
		self.assertIn("wireless network", (q.custom_scope_overview or "").lower())
		# figures come from the DCS, never the model
		self.assertTrue(any(float(r.rate or 0) == 150 for r in q.items), "selling rate must come from the DCS")
		self.assertTrue(any("access point" in (r.description or "").lower() for r in q.items))

	@patch("bsgroup.ai.anthropic_client.get_active_config", side_effect=AIProviderError("AI analysis is turned off."))
	def test_ai_off_still_produces_deterministic_draft(self, _cfg):
		dcs = self._make_dcs()
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 1)
		self.assertFalse(res["ai_used"])
		self.assertIsNotNone(res["quotation"])
		self.assertEqual(frappe.get_doc("Quotation", res["quotation"]).docstatus, 0)

	@patch("bsgroup.ai.anthropic_client.generate", _fake_generate)
	@patch("bsgroup.ai.anthropic_client.get_active_config", _fake_config)
	def test_default_does_not_overwrite_existing_scope(self):
		dcs_name = self._make_dcs()
		dcs = frappe.get_doc("Deal Cost Sheet", dcs_name)
		dcs.scope_overview = "<p>Human-written scope</p>"
		dcs.save(ignore_permissions=True)
		res = quotation_generator.generate_quotation_from_dcs(dcs_name)
		q = frappe.get_doc("Quotation", res["quotation"])
		self.assertIn("human-written scope", (q.custom_scope_overview or "").lower())
		self.assertNotIn("custom_scope_overview", res["fields_updated"])


if __name__ == "__main__":
	unittest.main()
