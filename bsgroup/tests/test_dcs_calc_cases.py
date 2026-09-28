"""Staging probe: the seven Deal Cost Sheet calculation cases, saved through the real
Frappe event sequence (validate -> before_save -> on_update) and read back from the
database, then re-saved to prove the stored figures are stable.

Every record is ZZTEST-prefixed via bsgroup.tests.dcs_fixtures. Never run on production.

	bench --site <staging-site> run-tests --module bsgroup.tests.test_dcs_calc_cases

Expected values are the ones the isolated harness produced for the server path
(calculate_deal_financials followed by dcs_margin_canonicalisation). They also equal the
new client preview (recalc_parent) for every case, which is the parity being claimed.
"""

import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch

from bsgroup.tests.dcs_fixtures import PREFIX, ensure, make_dcs

TOTALS = [
	"products_cost_total", "products_selling_total", "services_cost_total", "services_selling_total",
	"total_resource_cost", "total_cost", "total_selling", "margin_value", "margin_percent",
]


def stock_item(name, is_stock_item):
	return ensure(
		"Item", name,
		{
			"item_code": name, "item_name": name, "is_stock_item": is_stock_item,
			"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
			"stock_uom": frappe.db.get_value("UOM", {}, "name"),
		},
	)


def P():
	return stock_item(f"{PREFIX}-Calc-Product", 1)


def S():
	return stock_item(f"{PREFIX}-Calc-Service", 0)


CASES = [
	{
		"name": "1 baseline products + service + charges + resources",
		"items": [
			{"item_code": P, "qty": 1, "cost_rate": 2821, "selling_rate": 3425},
			{"item_code": P, "qty": 1, "cost_rate": 500, "selling_rate": 650},
			{"item_code": S, "qty": 2, "cost_rate": 800, "selling_rate": 2000},
		],
		"charges": [150],
		"resources": [{"no_of_persons": 1, "no_of_days": 2, "cost_rate": 600}, {"no_of_persons": 1, "no_of_days": 2, "cost_rate": 250}],
		"expect": {"products_cost_total": 3321, "products_selling_total": 4075, "services_cost_total": 1600,
			"services_selling_total": 4000, "total_resource_cost": 1700, "total_cost": 6771, "total_selling": 8075,
			"margin_value": 1304, "margin_percent": 16.149},
		"row_gp_percent": [17.64, 23.08, 60.0],
		"row_item_category": ["Products", "Products", "Professional Services"],
	},
	{
		"name": "2 zero selling on every row",
		"items": [{"item_code": P, "qty": 1, "cost_rate": 1000, "selling_rate": 0}, {"item_code": S, "qty": 1, "cost_rate": 400, "selling_rate": 0}],
		"charges": [50],
		"resources": [{"no_of_persons": 1, "no_of_days": 1, "cost_rate": 300}],
		"expect": {"products_cost_total": 1000, "products_selling_total": 0, "services_cost_total": 400, "services_selling_total": 0,
			"total_resource_cost": 300, "total_cost": 1750, "total_selling": 0, "margin_value": -1750, "margin_percent": 0},
		"row_gp_percent": [0, 0],
		"row_item_category": ["Products", "Professional Services"],
	},
	{
		"name": "3 rounding: fractional qty and rates",
		"items": [{"item_code": P, "qty": 3, "cost_rate": 33.333, "selling_rate": 49.999}, {"item_code": P, "qty": 0.5, "cost_rate": 199.99, "selling_rate": 266.66}],
		"charges": [],
		"resources": [],
		"expect": {"products_cost_total": 199.994, "products_selling_total": 283.327, "services_cost_total": 0, "services_selling_total": 0,
			"total_resource_cost": 0, "total_cost": 199.994, "total_selling": 283.327, "margin_value": 83.333, "margin_percent": 29.412},
		"row_gp_percent": [33.33, 25.0],
		"row_item_category": ["Products", "Products"],
	},
	{
		"name": "4 exclusions: exclude_item_name_and_brand on every row, same figures as case 1",
		"items": [
			{"item_code": P, "qty": 1, "cost_rate": 2821, "selling_rate": 3425, "exclude_item_name_and_brand": 1},
			{"item_code": P, "qty": 1, "cost_rate": 500, "selling_rate": 650, "exclude_item_name_and_brand": 1},
			{"item_code": S, "qty": 2, "cost_rate": 800, "selling_rate": 2000, "exclude_item_name_and_brand": 1},
		],
		"charges": [150],
		"resources": [{"no_of_persons": 1, "no_of_days": 2, "cost_rate": 600}, {"no_of_persons": 1, "no_of_days": 2, "cost_rate": 250}],
		"apply_exclude_to_all_items": 1,
		"expect": {"products_cost_total": 3321, "products_selling_total": 4075, "services_cost_total": 1600,
			"services_selling_total": 4000, "total_resource_cost": 1700, "total_cost": 6771, "total_selling": 8075,
			"margin_value": 1304, "margin_percent": 16.149},
		"row_gp_percent": [17.64, 23.08, 60.0],
		"row_item_category": ["Products", "Products", "Professional Services"],
	},
	{
		"name": "5 resources by hours only, no persons or days",
		"items": [{"item_code": P, "qty": 1, "cost_rate": 100, "selling_rate": 200}],
		"charges": [],
		"resources": [{"no_of_persons": 0, "no_of_days": 0, "hours": 5, "cost_rate": 100}],
		"expect": {"products_cost_total": 100, "products_selling_total": 200, "services_cost_total": 0, "services_selling_total": 0,
			"total_resource_cost": 500, "total_cost": 600, "total_selling": 200, "margin_value": -400, "margin_percent": -200},
		"row_gp_percent": [50.0],
		"row_item_category": ["Products"],
	},
	{
		"name": "6 header disagrees with item category: service item under a Products header",
		"items": [
			{"item_code": P, "qty": 1, "cost_rate": 100, "selling_rate": 200, "header": "Products"},
			{"item_code": S, "qty": 1, "cost_rate": 400, "selling_rate": 900, "header": "Products"},
		],
		"charges": [],
		"resources": [],
		"expect": {"products_cost_total": 100, "products_selling_total": 200, "services_cost_total": 400, "services_selling_total": 900,
			"total_resource_cost": 0, "total_cost": 500, "total_selling": 1100, "margin_value": 600, "margin_percent": 54.545},
		"row_gp_percent": [50.0, 55.56],
		"row_item_category": ["Products", "Professional Services"],
	},
	{
		"name": "7 currency OMR: formatting only, arithmetic unchanged",
		"currency": "OMR",
		"items": [{"item_code": P, "qty": 2, "cost_rate": 10.5, "selling_rate": 14.25}],
		"charges": [1.5],
		"resources": [],
		"expect": {"products_cost_total": 21, "products_selling_total": 28.5, "services_cost_total": 0, "services_selling_total": 0,
			"total_resource_cost": 0, "total_cost": 22.5, "total_selling": 28.5, "margin_value": 6, "margin_percent": 21.053},
		"row_gp_percent": [26.32],
		"row_item_category": ["Products"],
	},
]


class IntegrationTestDealCostSheetCalcCases(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()

	def build(self, case):
		extra = {
			"items": [{**row, "item_code": row["item_code"]()} for row in case["items"]],
			"resources": [{"resource_type": "Internal", "role": "ZZTEST", **r} for r in case["resources"]],
			"addtional_charges": [{"description": "ZZTEST charge", "amount": a} for a in case["charges"]],
		}
		if case.get("currency"):
			extra["currency"] = case["currency"]
		if case.get("apply_exclude_to_all_items"):
			extra["apply_exclude_to_all_items"] = 1
		return make_dcs("Customer", suffix=frappe.generate_hash(length=6), **extra)

	def assert_totals(self, case, doc, label):
		for field, expected in case["expect"].items():
			self.assertAlmostEqual(
				frappe.utils.flt(doc.get(field)), expected, places=3,
				msg=f"{case['name']} :: {label} :: {field}",
			)
		self.assertEqual([r.item_category for r in doc.items], case["row_item_category"], f"{case['name']} :: {label} :: item_category")
		for r, expected in zip(doc.items, case["row_gp_percent"]):
			self.assertAlmostEqual(frappe.utils.flt(r.gp_percent), expected, places=2, msg=f"{case['name']} :: {label} :: row gp_percent")

	def test_cases_persist_and_survive_reload_and_resave(self):
		for case in CASES:
			with self.subTest(case=case["name"]):
				doc = self.build(case)

				# 1. In-memory document straight after insert (before_save + on_update have run).
				self.assert_totals(case, doc, "in-memory after insert")

				# 2. Database truth, read back fresh.
				stored = frappe.get_doc("Deal Cost Sheet", doc.name)
				self.assert_totals(case, stored, "reloaded from database")
				db_row = frappe.db.get_value("Deal Cost Sheet", doc.name, TOTALS, as_dict=True)
				for field in TOTALS:
					self.assertAlmostEqual(frappe.utils.flt(db_row[field]), case["expect"][field], places=3, msg=f"{case['name']} :: db_row :: {field}")

				# 3. A second save with no edits must not move any figure (rounding stability).
				stored.flags.ignore_links = True
				stored.save(ignore_permissions=True)
				resaved = frappe.get_doc("Deal Cost Sheet", doc.name)
				self.assert_totals(case, resaved, "after unchanged re-save")

	def test_exclusion_flag_never_touches_figures(self):
		base = next(c for c in CASES if c["name"].startswith("1 "))
		excl = next(c for c in CASES if c["name"].startswith("4 "))
		self.assertEqual(base["expect"], excl["expect"])
		doc = self.build(excl)
		self.assertTrue(all(r.exclude_item_name_and_brand for r in doc.items))
		self.assert_totals(base, frappe.get_doc("Deal Cost Sheet", doc.name), "exclusions on, figures of case 1")
