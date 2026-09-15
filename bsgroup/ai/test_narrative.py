# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt
"""Framework-free unit tests for bsgroup.ai.narrative.

These import no frappe and can run with plain ``python -m unittest`` as well as
under ``bench run-tests``. They lock down the safety-critical policy: no figures
leave for the model, missing costs are flagged not filled, the approval gate
blocks, and NEEDS INPUT markers never reach a customer document.
"""

import json
import unittest

from bsgroup.ai import narrative


class TestDetectMissingCosts(unittest.TestCase):
	def test_clean_sheet_has_no_issues(self):
		items = [{"item_code": "AP-515", "item_name": "AP", "qty": 5, "cost_rate": 100, "selling_rate": 150}]
		self.assertEqual(narrative.detect_missing_costs(items), [])

	def test_zero_cost_is_flagged_not_filled(self):
		items = [{"item_code": "AP-515", "item_name": "AP", "qty": 5, "cost_rate": 0, "selling_rate": 150}]
		issues = narrative.detect_missing_costs(items)
		self.assertTrue(any("Cost rate is zero" in i["issue"] for i in issues))

	def test_zero_qty_and_selling_flagged(self):
		items = [{"item_code": "X", "item_name": "X", "qty": 0, "cost_rate": 10, "selling_rate": 0}]
		issues = narrative.detect_missing_costs(items)
		reasons = " ".join(i["issue"] for i in issues)
		self.assertIn("Quantity is zero", reasons)
		self.assertIn("Selling rate is zero", reasons)

	def test_row_without_item_or_name_flagged(self):
		items = [{"qty": 1, "cost_rate": 1, "selling_rate": 2}]
		issues = narrative.detect_missing_costs(items)
		self.assertTrue(any("no item and no description" in i["issue"] for i in issues))

	def test_additional_charges_need_configured_item(self):
		items = [{"item_code": "X", "item_name": "X", "qty": 1, "cost_rate": 1, "selling_rate": 2}]
		charges = [{"amount": 500}]
		issues = narrative.detect_missing_costs(items, charges=charges, dcs_addtional_item_configured=False)
		self.assertTrue(any(i["area"] == "additional_charges" for i in issues))
		# configured -> no such issue
		issues2 = narrative.detect_missing_costs(items, charges=charges, dcs_addtional_item_configured=True)
		self.assertFalse(any(i["area"] == "additional_charges" for i in issues2))

	def test_resource_zero_cost_flagged(self):
		items = [{"item_code": "X", "item_name": "X", "qty": 1, "cost_rate": 1, "selling_rate": 2}]
		resources = [{"role": "Engineer", "cost_rate": 0, "cost_amount": 0}]
		issues = narrative.detect_missing_costs(items, resources=resources)
		self.assertTrue(any(i["area"] == "resource" for i in issues))


class TestApprovalGate(unittest.TestCase):
	def test_clear_gate_passes(self):
		self.assertIsNone(narrative.approval_gate_block_reason({"custom_margin_gate": "Clear"}))

	def test_blocked_gate_blocks(self):
		reason = narrative.approval_gate_block_reason(
			{"custom_margin_gate": "Blocked", "custom_margin_gate_reason": "below floor"}
		)
		self.assertIsNotNone(reason)
		self.assertIn("below floor", reason)

	def test_md_approval_required_without_record_blocks(self):
		self.assertIsNotNone(
			narrative.approval_gate_block_reason({"custom_approval_required": "Managing Director", "custom_approved_on": ""})
		)

	def test_md_approval_recorded_passes(self):
		self.assertIsNone(
			narrative.approval_gate_block_reason(
				{"custom_approval_required": "Managing Director", "custom_approved_on": "2026-09-15 10:00:00"}
			)
		)

	def test_pending_endorsement_blocks(self):
		self.assertIsNotNone(
			narrative.approval_gate_block_reason({"custom_approval_state": "Pending Endorsement", "custom_approved_on": ""})
		)

	def test_in_negotiation_blocks(self):
		self.assertIsNotNone(
			narrative.approval_gate_block_reason({"custom_approval_state": "In Negotiation", "custom_approved_on": ""})
		)

	def test_approval_state_with_recorded_approval_passes(self):
		self.assertIsNone(
			narrative.approval_gate_block_reason(
				{"custom_approval_state": "Pending Endorsement", "custom_approved_on": "2026-09-15 10:00:00"}
			)
		)


class TestContextRedaction(unittest.TestCase):
	def test_no_figures_reach_the_model(self):
		header = {"subject": "Wi-Fi upgrade", "scope_overview": "<p>Scope</p>", "company": "BSG"}
		items = [{
			"item_code": "AP-515", "item_name": "Access Point", "brand": "Aruba", "header": "Hardware",
			"qty": 5, "uom": "Nos", "cost_rate": 100, "selling_rate": 150, "description": "",
		}]
		context = narrative.build_ai_context(header, items)
		blob = json.dumps(context).lower()
		for banned in ("cost", "selling", "margin", "gp", "rate", "qty", "150", "100"):
			self.assertNotIn(banned, blob, f"figure/quantity leaked into model context: {banned}")
		# descriptive fields survive
		self.assertEqual(context["items"][0]["item_name"], "Access Point")
		self.assertEqual(context["items"][0]["uom"], "Nos")


class TestParseAIResponse(unittest.TestCase):
	def test_plain_json(self):
		text = '{"subject":"S","scope_overview_html":"<p>x</p>","customer_notes":"","item_descriptions":[],"needs_input":[]}'
		parsed = narrative.parse_ai_response(text)
		self.assertEqual(parsed["subject"], "S")

	def test_fenced_json_with_prose(self):
		text = "Sure!\n```json\n{\"subject\":\"S\",\"item_descriptions\":[{\"line\":1,\"text\":\"desc\"}]}\n```\nthanks"
		parsed = narrative.parse_ai_response(text)
		self.assertEqual(parsed["item_descriptions"][0]["text"], "desc")

	def test_garbage_raises(self):
		with self.assertRaises(ValueError):
			narrative.parse_ai_response("no json here")


class TestSelectNarrativeUpdates(unittest.TestCase):
	def test_fills_blank_fields_only_by_default(self):
		parsed = {"subject": "New", "scope_overview_html": "<p>New scope</p>", "customer_notes": "n", "item_descriptions": [], "needs_input": []}
		existing = {"custom_subject": "Existing", "custom_scope_overview": "", "custom_customer_notes": ""}
		fields, items, needs = narrative.select_narrative_updates(parsed, existing, items=[])
		self.assertNotIn("custom_subject", fields)  # existing kept
		self.assertIn("custom_scope_overview", fields)  # blank filled
		self.assertEqual(needs, [])

	def test_overwrite_replaces_existing(self):
		parsed = {"subject": "New", "item_descriptions": [], "needs_input": []}
		existing = {"custom_subject": "Existing"}
		fields, items, needs = narrative.select_narrative_updates(parsed, existing, items=[], overwrite=True)
		self.assertEqual(fields["custom_subject"], "New")

	def test_needs_input_marker_never_written(self):
		parsed = {
			"subject": "Supply of [NEEDS INPUT: model number]",
			"item_descriptions": [{"line": 1, "text": "ok desc"}, {"line": 2, "text": "[NEEDS INPUT: spec]"}],
			"needs_input": ["scope unclear"],
		}
		existing = {"custom_subject": ""}
		items = [{"description": ""}, {"description": ""}]
		fields, item_updates, needs = narrative.select_narrative_updates(parsed, existing, items=items)
		self.assertNotIn("custom_subject", fields)  # marker field dropped
		self.assertEqual([u["line"] for u in item_updates], [1])  # only clean line kept
		self.assertTrue(any("scope unclear" in n for n in needs))
		self.assertTrue(any("custom_subject" in n for n in needs))
		self.assertTrue(any("line 2" in n for n in needs))

	def test_item_line_out_of_range_ignored(self):
		parsed = {"item_descriptions": [{"line": 9, "text": "x"}], "needs_input": []}
		fields, item_updates, needs = narrative.select_narrative_updates(parsed, {}, items=[{"description": ""}])
		self.assertEqual(item_updates, [])


if __name__ == "__main__":
	unittest.main()
