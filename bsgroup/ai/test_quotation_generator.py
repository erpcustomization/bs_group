# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Frappe integration tests for bsgroup.ai.quotation_generator.

Run on a bench:  bench --site <site> run-tests --module bsgroup.ai.test_quotation_generator

The Anthropic network call is always patched here - no API key and no outbound
request are needed to run these. The tests prove the orchestration: permission
and approval gates, missing-cost flagging (never invention), delegation of all
figures to the real make_quotation, narrative-only write-back, and that the
output is a draft (docstatus 0).

Fixtures are ZZTEST-prefixed and rolled back by FrappeTestCase; nothing here
touches production data.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from bsgroup.ai import quotation_generator

PREFIX = "ZZTEST-AIQ"

FAKE_AI_TEXT = (
	'{"subject":"Wireless network upgrade",'
	'"scope_overview_html":"<p>Supply and installation of the wireless network.</p>",'
	'"customer_notes":"Prices exclude civil works.",'
	'"item_descriptions":[{"line":1,"text":"Enterprise Wi-Fi access point"}],'
	'"needs_input":[]}'
)


def _fake_generate(system_prompt, user_message, config=None, timeout=60):
	return {"text": FAKE_AI_TEXT, "model": "claude-3-5-haiku-20241022", "usage": {}, "stop_reason": "end_turn"}


def _fake_config():
	return {
		"enabled": True,
		"provider": "Anthropic (Claude)",
		"model": "claude-3-5-haiku-20241022",
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
			doc = frappe.get_doc({
				"doctype": "Customer", "customer_name": name, "customer_type": "Company",
			})
			doc.insert(ignore_permissions=True, ignore_mandatory=True)
		return name

	@classmethod
	def _ensure_item(cls):
		code = f"{PREFIX}-AP"
		if not frappe.db.exists("Item", code):
			doc = frappe.get_doc({
				"doctype": "Item", "item_code": code, "item_name": "Test Access Point",
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups",
				"stock_uom": "Nos", "is_stock_item": 0, "is_sales_item": 1,
			})
			doc.insert(ignore_permissions=True, ignore_mandatory=True)
		return code

	def _make_opportunity(self):
		opp = frappe.get_doc({
			"doctype": "Opportunity", "opportunity_from": "Customer", "party_name": self.customer,
			"company": self.company, "custom_subject": f"{PREFIX} opportunity",
		})
		opp.flags.ignore_mandatory = True
		opp.insert(ignore_permissions=True, ignore_mandatory=True)
		return opp.name

	def _make_dcs(self, cost_rate=100, selling_rate=150, margin_gate="Clear", approval_required="None"):
		dcs = frappe.get_doc({
			"doctype": "Deal Cost Sheet",
			"opportunity": self._make_opportunity(),
			"company": self.company,
			"currency": self.currency,
			"subject": f"{PREFIX} deal",
			"scope_overview": "",
			"custom_margin_gate": margin_gate,
			"custom_approval_required": approval_required,
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
		self.assertEqual(frappe.db.count("Quotation"), before, "no quotation should be created on a missing-cost block")

	def test_blocked_margin_gate_blocks(self):
		dcs = self._make_dcs(margin_gate="Blocked")
		res = quotation_generator.generate_quotation_from_dcs(dcs)
		self.assertEqual(res["ok"], 0)
		self.assertEqual(res["blocked"], "approval_gate")
		self.assertIsNone(res["quotation"])

	def test_preview_is_read_only(self):
		dcs = self._make_dcs(cost_rate=0)
		before = frappe.db.count("Quotation")
		res = quotation_generator.preview_dcs_readiness(dcs)
		self.assertFalse(res["ok"])
		self.assertTrue(res["missing_costs"])
		self.assertEqual(frappe.db.count("Quotation"), before)


class TestGeneration(AIQuotationTestBase):
	def setUp(self):
		if self.skip:
			self.skipTest("required masters (Company/Item) unavailable in this site")

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
		# narrative applied to descriptive fields only
		self.assertIn("wireless network", (q.custom_scope_overview or "").lower())
		# a figure field remains the deterministic one from make_quotation
		self.assertTrue(any(float(r.rate or 0) == 150 for r in q.items), "selling rate must come from the DCS, not the model")
		# line description written where it was blank
		self.assertTrue(any("access point" in (r.description or "").lower() for r in q.items))

	@patch("bsgroup.ai.anthropic_client.get_active_config", side_effect=Exception("AI disabled"))
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
