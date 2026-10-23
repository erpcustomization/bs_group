"""Unit coverage for the DCS quotation alignment rules. Needs no Frappe site.

Run anywhere:   python -m unittest bsgroup/dcs/test_quote_alignment_core.py   (or this file directly)
Run on bench:   bench --site <site> run-tests --module bsgroup.dcs.test_quote_alignment_core

The module under test is loaded by path so importing the ``bsgroup`` package
(which patches Frappe on import) is not required.
"""
import importlib.util
import pathlib
import unittest

_spec = importlib.util.spec_from_file_location(
	"quote_alignment_core", pathlib.Path(__file__).with_name("quote_alignment_core.py"))
core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(core)

GENERIC = "Generic"


def sheet(rows=None, **extra):
	"""Sample deal: 2 laptops at 4000 selling, installation at 2000 selling; selling 10000.
	(Cost 3000/1500, margin 25%, is internal and never part of the comparison input.)"""
	rows = rows if rows is not None else [
		{"token": "L1", "kind": "item", "item_code": GENERIC, "qty": 2, "selling_rate": 4000, "selling_amount": 8000},
		{"token": "I1", "kind": "item", "item_code": GENERIC, "qty": 1, "selling_rate": 2000, "selling_amount": 2000},
	]
	base = {"currency": "AED", "revision_reference": "REV-1", "docstatus": 1, "superseded": False,
		"selling_total": sum(r["selling_amount"] for r in rows), "additional_item": "ADDL", "rows": rows,
		"internal_tokens": []}
	base.update(extra)
	return base


def line(idx, qty, rate, sources=None, item=GENERIC, **extra):
	data = {"idx": idx, "item_code": item, "qty": qty, "stock_qty": qty, "rate": rate, "amount": qty * rate,
		"price_list_rate": rate, "discount_percentage": 0, "discount_amount": 0, "sources": sources}
	data.update(extra)
	return data


def quote(lines, **extra):
	base = {"currency": "AED", "revision_reference": "REV-1", "net_total": sum(l["amount"] for l in lines),
		"discount_amount": 0, "additional_discount_percentage": 0, "taxes": [], "lines": lines}
	base.update(extra)
	return base


def generated():
	return [line(1, 2, 4000, "L1"), line(2, 1, 2000, "I1")]


class AlignmentStates(unittest.TestCase):
	def test_generated_quotation_matches_and_is_issuable(self):
		r = core.analyse(sheet(), quote(generated()))
		self.assertEqual(r["states"], ["matching"])
		self.assertTrue(r["issuable"])
		self.assertEqual(r["variance"], 0)

	def test_descriptions_and_reordering_are_presentation(self):
		lines = list(reversed(generated()))
		lines[0]["description"] = "Professional installation and commissioning"
		r = core.analyse(sheet(), quote(lines))
		self.assertTrue(r["issuable"], r)

	def test_mapped_bundle_with_exact_coverage_is_accepted(self):
		r = core.analyse(sheet(), quote([line(1, 1, 10000, "L1,I1")]))
		self.assertEqual(r["states"], ["matching", "bundled"])
		self.assertTrue(r["issuable"])

	def test_bundle_same_total_but_unmapped_is_not_issuable(self):
		# Production case: one line, same 10000 total, no source rows.
		r = core.analyse(sheet(), quote([line(1, 1, 10000)]))
		self.assertIn("scope_changed", r["states"])
		self.assertFalse(r["issuable"])

	def test_redistribution_same_total_is_repriced(self):
		# Laptops 4500 x 2 + installation 1000 = 10000, installation margin would be -50%.
		r = core.analyse(sheet(), quote([line(1, 2, 4500, "L1"), line(2, 1, 1000, "I1")]))
		self.assertEqual(r["states"], ["repriced"])
		self.assertFalse(r["issuable"])
		self.assertEqual(r["variance"], 0)

	def test_selling_cut_is_repriced_and_total_changed(self):
		r = core.analyse(sheet(), quote([line(1, 2, 3600, "L1"), line(2, 1, 1800, "I1")]))
		self.assertEqual(r["states"], ["repriced", "total_changed"])
		self.assertEqual(r["variance"], -1000)

	def test_quantity_increase_same_total_is_scope_change(self):
		# 4 laptops x 2000 + installation 2000 = 10000.
		r = core.analyse(sheet(), quote([line(1, 4, 2000, "L1"), line(2, 1, 2000, "I1")]))
		self.assertIn("scope_changed", r["states"])
		self.assertIn("qty_changed", r["lines"][0]["status"])
		self.assertFalse(r["issuable"])

	def test_states_coexist(self):
		lines = [line(1, 1, 9000, "L1,I1"), line(2, 1, 100)]
		r = core.analyse(sheet(), quote(lines), )
		self.assertEqual(r["states"], ["bundled", "repriced", "total_changed", "scope_changed"])


class MappingIntegrity(unittest.TestCase):
	def test_duplicate_mapping_is_rejected(self):
		r = core.analyse(sheet(), quote([line(1, 2, 4000, "L1"), line(2, 1, 2000, "L1")]))
		self.assertIn("scope_changed", r["states"])
		self.assertEqual(r["duplicates"], ["L1"])
		self.assertEqual(r["uncovered"], ["I1"])
		self.assertFalse(r["issuable"])

	def test_repeat_within_one_line_is_duplicate(self):
		r = core.analyse(sheet(), quote([line(1, 1, 10000, "L1,L1,I1")]))
		self.assertFalse(r["issuable"])
		self.assertEqual(r["duplicates"], ["L1"])

	def test_alias_and_token_for_same_row_is_duplicate(self):
		rows = sheet()["rows"]
		rows[0]["aliases"] = ["rowname-L"]
		r = core.analyse(sheet(rows), quote([line(1, 2, 4000, "L1"), line(2, 1, 2000, "I1,rowname-L")]))
		self.assertFalse(r["issuable"])

	def test_unknown_source_is_rejected(self):
		r = core.analyse(sheet(), quote([line(1, 2, 4000, "L1"), line(2, 1, 2000, "I1,FOREIGN")]))
		self.assertEqual(r["unknown"], ["FOREIGN"])
		self.assertFalse(r["issuable"])

	def test_internal_expense_cannot_be_presented(self):
		r = core.analyse(sheet(internal_tokens=["EXP"]), quote([line(1, 2, 4000, "L1"), line(2, 1, 2000, "I1,EXP")]))
		self.assertIn("internal_source", r["lines"][1]["status"])
		self.assertFalse(r["issuable"])

	def test_partially_mapped_quote_flags_unmapped_lines(self):
		r = core.analyse(sheet(), quote([line(1, 2, 4000, "L1"), line(2, 1, 2000)]))
		self.assertIn("unmapped", r["lines"][1]["status"])
		self.assertFalse(r["issuable"])

	def test_item_swap_on_single_source_is_scope_change(self):
		r = core.analyse(sheet(), quote([line(1, 2, 4000, "L1", item="Laptop-X"), line(2, 1, 2000, "I1")]))
		self.assertIn("item_changed", r["lines"][0]["status"])
		self.assertFalse(r["issuable"])

	def test_bundle_item_must_come_from_its_sources(self):
		r = core.analyse(sheet(), quote([line(1, 1, 10000, "L1,I1", item="Other")]))
		self.assertIn("item_changed", r["lines"][0]["status"])

	def test_generic_rows_swapped_are_caught_by_figures(self):
		# Both rows are Generic: identity comes from the source row, not the item code.
		r = core.analyse(sheet(), quote([line(1, 2, 4000, "I1"), line(2, 1, 2000, "L1")]))
		self.assertFalse(r["issuable"])
		self.assertIn("qty_changed", r["lines"][0]["status"])

	def test_uom_conversion_is_compared_in_stock_quantity(self):
		lines = [line(1, 1, 8000, "L1", stock_qty=2), line(2, 1, 2000, "I1")]
		self.assertTrue(core.analyse(sheet(), quote(lines))["issuable"])
		lines[0]["stock_qty"] = 1
		self.assertFalse(core.analyse(sheet(), quote(lines))["issuable"])


class DiscountPaths(unittest.TestCase):
	def test_line_discount_presentation_is_repriced(self):
		lines = generated()
		lines[0].update(price_list_rate=5000, discount_percentage=20)
		r = core.analyse(sheet(), quote(lines))
		self.assertIn("repriced", r["states"])
		self.assertFalse(r["issuable"])

	def test_price_list_margin_is_repriced(self):
		lines = generated()
		lines[0]["price_list_rate"] = 3500
		self.assertFalse(core.analyse(sheet(), quote(lines))["issuable"])

	def test_document_discount_is_total_changed(self):
		r = core.analyse(sheet(), quote(generated(), discount_amount=500, net_total=9500))
		self.assertIn("total_changed", r["states"])
		self.assertFalse(r["issuable"])

	def test_document_discount_with_inflated_lines_is_caught(self):
		lines = [line(1, 2, 4250, "L1"), line(2, 1, 1500, "I1")]
		r = core.analyse(sheet(), quote(lines, discount_amount=0, additional_discount_percentage=0))
		self.assertFalse(r["issuable"])
		r = core.analyse(sheet(), quote(generated(), additional_discount_percentage=5, net_total=10000))
		self.assertFalse(r["issuable"])

	def test_negative_or_fixed_tax_rows_are_total_changed(self):
		for tax in ({"charge_type": "Actual", "rate": 0, "tax_amount": -300},
				{"charge_type": "On Net Total", "rate": -5, "tax_amount": -500}):
			r = core.analyse(sheet(), quote(generated(), taxes=[tax]))
			self.assertIn("total_changed", r["states"], tax)
		r = core.analyse(sheet(), quote(generated(), taxes=[{"charge_type": "On Net Total", "rate": 5, "tax_amount": 500}]))
		self.assertTrue(r["issuable"])

	def test_negative_or_non_finite_figures_are_invalid(self):
		lines = generated()
		lines[1].update(rate=float("nan"), amount=float("nan"))
		self.assertFalse(core.analyse(sheet(), quote(lines, net_total=8000))["issuable"])
		lines = [*generated(), line(3, 1, -100, None)]
		self.assertFalse(core.analyse(sheet(), quote(lines))["issuable"])


class Staleness(unittest.TestCase):
	def test_revision_change_is_stale_even_when_figures_match(self):
		r = core.analyse(sheet(revision_reference="REV-2"), quote(generated()))
		self.assertEqual(r["states"], ["matching", "stale"])
		self.assertFalse(r["issuable"])

	def test_superseded_or_unsubmitted_sheet_is_stale(self):
		self.assertFalse(core.analyse(sheet(superseded=True), quote(generated()))["issuable"])
		self.assertFalse(core.analyse(sheet(docstatus=2), quote(generated()))["issuable"])

	def test_living_total_away_from_rows_is_stale(self):
		r = core.analyse(sheet(selling_total=9500), quote(generated()))
		self.assertIn("stale", r["states"])
		self.assertFalse(r["issuable"])


class ChargesAndPrecision(unittest.TestCase):
	def rows(self):
		return sheet()["rows"] + [
			{"token": "C1", "kind": "charge", "item_code": None, "qty": 1, "selling_rate": 100, "selling_amount": 100},
			{"token": "C2", "kind": "charge", "item_code": None, "qty": 1, "selling_rate": 50, "selling_amount": 50}]

	def test_generated_charge_line_matches_and_is_not_a_bundle(self):
		lines = [*generated(), line(3, 1, 150, "C1,C2", item="ADDL")]
		r = core.analyse(sheet(self.rows(), internal_tokens=["EXP"]), quote(lines))
		self.assertEqual(r["states"], ["matching"])

	def test_charge_line_with_wrong_item_or_amount(self):
		lines = [*generated(), line(3, 1, 150, "C1,C2", item=GENERIC)]
		self.assertFalse(core.analyse(sheet(self.rows()), quote(lines))["issuable"])
		lines = [*generated(), line(3, 1, 120, "C1,C2", item="ADDL")]
		self.assertFalse(core.analyse(sheet(self.rows()), quote(lines))["issuable"])

	def test_legacy_unmapped_quotation_follows_previous_rule(self):
		lines = [line(1, 1, 2000), line(2, 2, 4000), line(3, 1, 150, item="ADDL")]
		self.assertTrue(core.analyse(sheet(self.rows()), quote(lines))["issuable"])
		lines = [line(1, 1, 1000), line(2, 2, 4500), line(3, 1, 150, item="ADDL")]
		r = core.analyse(sheet(self.rows()), quote(lines))
		self.assertFalse(r["issuable"])
		self.assertIn("scope_changed", r["states"])

	def test_omr_three_decimal_tolerance(self):
		rows = [{"token": "A", "kind": "item", "item_code": "X", "qty": 3, "selling_rate": 1.333, "selling_amount": 3.999}]
		ok = core.analyse(sheet(rows, currency="OMR"), quote([line(1, 3, 1.333, "A", item="X")], currency="OMR"))
		self.assertTrue(ok["issuable"], ok)
		off = core.analyse(sheet(rows, currency="OMR"), quote([line(1, 3, 1.332, "A", item="X")], currency="OMR"))
		self.assertFalse(off["issuable"])


class Suggestions(unittest.TestCase):
	def test_unique_candidates_are_suggested(self):
		s = core.suggest(sheet(), quote([line(1, 2, 4000), line(2, 1, 2000)]))
		self.assertEqual(s, {1: "L1", 2: "I1"})

	def test_ambiguous_generic_rows_are_never_suggested(self):
		rows = [{"token": "A", "kind": "item", "item_code": GENERIC, "qty": 1, "selling_rate": 2000, "selling_amount": 2000},
			{"token": "B", "kind": "item", "item_code": GENERIC, "qty": 1, "selling_rate": 2000, "selling_amount": 2000}]
		self.assertEqual(core.suggest(sheet(rows), quote([line(1, 1, 2000), line(2, 1, 2000)])), {})

	def test_changed_lines_get_no_suggestion(self):
		self.assertEqual(core.suggest(sheet(), quote([line(1, 2, 4500), line(2, 1, 1000)])), {})

	def test_suggestions_are_not_applied_by_analysis(self):
		r = core.analyse(sheet(), quote([line(1, 2, 4000), line(2, 1, 2000)]))
		self.assertFalse(r["mapped"])


if __name__ == "__main__":
	unittest.main()
