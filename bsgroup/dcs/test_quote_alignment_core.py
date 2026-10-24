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

	def test_rate_below_price_list_is_repriced(self):
		lines = generated()
		lines[0]["price_list_rate"] = 5000  # 5000 list presented at 4000, discount fields left empty
		r = core.analyse(sheet(), quote(lines))
		self.assertIn("discounted", r["lines"][0]["status"])
		self.assertFalse(r["issuable"])

	def test_markup_over_unrelated_price_list_is_not_repriced(self):
		# Staging case: 1 x 10000 bundle of both rows; ERPNext re-fetched a 1890 list price and
		# carried the rest as an 8110 margin. The mapped DCS selling is met exactly.
		lines = [line(1, 1, 10000, "L1,I1", price_list_rate=1890, margin_type="Amount", margin_rate_or_amount=8110)]
		r = core.analyse(sheet(), quote(lines))
		self.assertEqual(r["states"], ["matching", "bundled"])
		self.assertEqual(r["lines"][0]["status"], ["bundle"])
		self.assertTrue(r["issuable"])
		single = generated()
		single[0].update(price_list_rate=3500)  # 4000 over a 3500 list: markup on a single-row line
		self.assertTrue(core.analyse(sheet(), quote(single))["issuable"])

	def test_selling_reduction_behind_markup_is_still_caught(self):
		lines = [line(1, 1, 9000, "L1,I1", price_list_rate=1890, margin_type="Amount", margin_rate_or_amount=7110)]
		r = core.analyse(sheet(), quote(lines))
		self.assertIn("repriced", r["lines"][0]["status"])
		self.assertIn("total_changed", r["states"])
		self.assertEqual(r["variance"], -1000)
		self.assertFalse(r["issuable"])
		# A line discount presented on the bundle stays a discount even when the net is met.
		lines = [line(1, 1, 10000, "L1,I1", price_list_rate=12500, discount_percentage=20)]
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

	def test_legacy_evidence_follows_previous_rule(self):
		lines = [line(1, 1, 2000), line(2, 2, 4000), line(3, 1, 150, item="ADDL")]
		self.assertTrue(core.analyse(sheet(self.rows()), quote(lines, legacy_evidence=True))["issuable"])
		self.assertFalse(core.analyse(sheet(self.rows()), quote(lines))["issuable"], "no evidence, no grandfathering")
		lines = [line(1, 1, 1000), line(2, 2, 4500), line(3, 1, 150, item="ADDL")]
		r = core.analyse(sheet(self.rows()), quote(lines, legacy_evidence=True))
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


class MappingRemovalBypass(unittest.TestCase):
	"""Review finding 1: removing mappings must never relax the rules."""

	def uom_lines(self, l1="L1", i1="I1"):
		# 2 laptops quoted as qty 2 in a unit of 2 (stock 4): the reviewer's reproduction.
		return [line(1, 2, 4000, l1, stock_qty=4), line(2, 1, 2000, i1)]

	def test_reviewer_reproduction_is_refused_with_and_without_mapping(self):
		self.assertFalse(core.analyse(sheet(), quote(self.uom_lines()))["issuable"])
		r = core.analyse(sheet(), quote(self.uom_lines(None, None)))
		self.assertFalse(r["issuable"])
		self.assertIn("scope_changed", r["states"])
		self.assertTrue(all("unmapped" in l["status"] for l in r["lines"]))

	def test_partial_removal_is_refused(self):
		for lines in (self.uom_lines("L1", None), self.uom_lines(None, "I1"),
				[line(1, 2, 4000, "L1"), line(2, 1, 2000, "")]):
			self.assertFalse(core.analyse(sheet(), quote(lines))["issuable"])

	def test_exact_unmapped_copy_without_evidence_is_refused(self):
		r = core.analyse(sheet(), quote([line(1, 2, 4000), line(2, 1, 2000)]))
		self.assertFalse(r["issuable"])
		self.assertFalse(r["legacy"])

	def test_legacy_evidence_does_not_apply_to_mapped_lines_check(self):
		# Evidence is only honoured by the server for unmapped pre-migration records; with
		# evidence the legacy multiset rule still refuses a changed scope.
		r = core.analyse(sheet(), quote([line(1, 4, 2000), line(2, 1, 2000)], legacy_evidence=True))
		self.assertFalse(r["issuable"])


class PackageQuantity(unittest.TestCase):
	"""Review finding 3: a bundle is one complete package; no multiplier."""

	def test_bundle_multiplier_is_refused(self):
		r = core.analyse(sheet(), quote([line(1, 4, 2500, "L1,I1")]))
		self.assertFalse(r["issuable"])
		self.assertIn("package_qty", r["lines"][0]["status"])

	def test_bundle_quantities(self):
		for qty, rate, stock in ((1, 10000, 1), (2, 5000, 2), (0.5, 20000, 0.5), (0, 10000, 0), (-1, -10000, -1)):
			r = core.analyse(sheet(), quote([line(1, qty, rate, "L1,I1", stock_qty=stock)]))
			self.assertEqual(r["issuable"], qty == 1, (qty, r["lines"][0]["status"]))

	def test_bundle_conversion_factor_must_be_one_to_one(self):
		# qty 1 in a unit of 2, or qty 0.5 in a unit of 2: neither is one package.
		for qty, stock in ((1, 2), (0.5, 1)):
			r = core.analyse(sheet(), quote([line(1, qty, 10000 / qty, "L1,I1", stock_qty=stock)]))
			self.assertFalse(r["issuable"], (qty, stock))

	def test_charge_lines_are_single_packages(self):
		rows = sheet()["rows"] + [
			{"token": "C1", "kind": "charge", "item_code": None, "qty": 1, "selling_rate": 100, "selling_amount": 100},
			{"token": "C2", "kind": "charge", "item_code": None, "qty": 1, "selling_rate": 50, "selling_amount": 50}]
		ok = [*generated(), line(3, 1, 150, "C1,C2", item="ADDL")]
		self.assertTrue(core.analyse(sheet(rows), quote(ok))["issuable"])
		for bad in ([*generated(), line(3, 3, 50, "C1,C2", item="ADDL")],
				[*generated(), line(3, 2, 50, "C1", item="ADDL"), line(4, 1, 50, "C2", item="ADDL")]):
			self.assertFalse(core.analyse(sheet(rows), quote(bad))["issuable"])
		# A charge inside an item bundle is still one package.
		mixed = [line(1, 1, 8100, "L1,C1"), line(2, 1, 2000, "I1"), line(3, 1, 50, "C2", item="ADDL")]
		self.assertTrue(core.analyse(sheet(rows), quote(mixed))["issuable"])
		mixed[0].update(qty=3, rate=2700, stock_qty=3)
		self.assertFalse(core.analyse(sheet(rows), quote(mixed))["issuable"])

	def test_zero_quantity_single_line_is_invalid(self):
		r = core.analyse(sheet(), quote([line(1, 0, 4000, "L1"), line(2, 1, 2000, "I1")]))
		self.assertIn("invalid", r["lines"][0]["status"])


class InitialAuthority(unittest.TestCase):
	"""Review finding 2: revision-0 positions get no blanket exemption."""

	def test_rejected_returned_and_blocked_refuse(self):
		for state in ("Rejected", "Returned for Rework", "Blocked"):
			self.assertTrue(core.initial_authority(state, "None", "None", 10000), state)
		self.assertTrue(core.initial_authority("", "Blocked", "None", 10000))
		self.assertTrue(core.initial_authority("", "None", "Blocked", 10000))

	def test_pending_or_required_without_approval_refuses(self):
		self.assertTrue(core.initial_authority("Pending Manager", "Manager", "Manager", 10000))
		self.assertTrue(core.initial_authority("", None, "Manager", 10000), "below-floor margin needs approval")
		self.assertTrue(core.initial_authority("In Negotiation", "Manager", "None", 10000))

	def test_approved_must_match_current_figures(self):
		self.assertEqual(core.initial_authority("Approved", "Manager", "Manager", 10000, approval_matches=True), "")
		self.assertTrue(core.initial_authority("Approved", "Manager", "Manager", 10000, approval_matches=False))

	def test_clear_position_is_authorised(self):
		for state in (None, "", "Not Started", "In Negotiation"):
			self.assertEqual(core.initial_authority(state, None, "None", 10000), "", state)

	def test_ambiguous_state_or_no_selling_never_authorises(self):
		self.assertTrue(core.initial_authority("Pending MD", None, "None", 10000))
		self.assertTrue(core.initial_authority("", None, "None", 0))
		self.assertTrue(core.initial_authority("", None, "None", float("nan")))


class Labels(unittest.TestCase):
	"""Review finding 4: Generic rows are distinguishable."""

	def test_labels_carry_row_description_quantity_and_unit(self):
		a = core.row_label("item", 1, "Business laptop\n 14 inch", 2, "Nos")
		b = core.row_label("item", 2, "Installation and commissioning", 1, "Nos")
		self.assertEqual(a, "Row 1: Business laptop 14 inch - 2 Nos")
		self.assertNotEqual(a, b)
		self.assertEqual(core.row_label("charge", 1, "Freight", 1, ""), "Charge 1: Freight - 1")
		self.assertTrue(core.row_label("item", 3, "x" * 300, 1, "Nos").endswith("... - 1 Nos"))


class PaymentTermsWording(unittest.TestCase):
	"""Review finding 6: wording comes from the template's actual rows, never its name."""

	def test_wording_from_rows_including_discount(self):
		rows = [{"payment_term": "Advance", "description": "Advance on order", "invoice_portion": 50,
				"due_date_based_on": "Day(s) after invoice date", "credit_days": 0},
			{"payment_term": "Balance", "invoice_portion": 50, "due_date_based_on": "Day(s) after invoice date",
				"credit_days": 30, "discount": 2, "discount_type": "Percentage", "discount_validity": 10,
				"discount_validity_based_on": "Day(s) after invoice date"}]
		text = core.payment_terms_wording(rows)
		self.assertEqual(text, "50% Advance on order, due on invoice; 50% Balance, due 30 day(s) after invoice date; "
			"2% early-payment discount within 10 day(s) after invoice date.")

	def test_month_basis_and_empty(self):
		rows = [{"payment_term": "Net", "invoice_portion": 100, "due_date_based_on": "Month(s) after the end of the invoice month",
			"credit_months": 1}]
		self.assertEqual(core.payment_terms_wording(rows), "100% Net, due 1 month(s) after the end of the invoice month.")
		self.assertEqual(core.payment_terms_wording([]), "")


if __name__ == "__main__":
	unittest.main()
