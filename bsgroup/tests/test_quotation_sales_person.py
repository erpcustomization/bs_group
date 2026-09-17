"""R9 regression tests: the Quotation sales-person hook must populate from a
valid Customer mapping and must never clear an existing value (the defect that
blanked custom_sales_person on production quotation saves)."""

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.tests.dcs_fixtures import make_customer
from bsgroup.utils.quotation import set_sales_person_from_customer


def any_sales_person():
	return frappe.db.get_value("Sales Person", {"enabled": 1}, "name") or frappe.db.get_value(
		"Sales Person", {}, "name"
	)


def quotation_stub(customer, current):
	q = frappe.new_doc("Quotation")
	q.quotation_to = "Customer"
	q.party_name = customer
	q.custom_sales_person = current
	return q


def map_sales_person(customer, sales_person):
	cust = frappe.get_doc("Customer", customer)
	cust.append("sales_team", {"sales_person": sales_person, "allocated_percentage": 100})
	cust.flags.ignore_permissions = True
	cust.flags.ignore_mandatory = True
	cust.save()


class TestQuotationSalesPersonHook(IntegrationTestCase):
	def test_empty_field_with_valid_mapping_is_populated(self):
		cust = make_customer("R9A")
		sp = any_sales_person()
		self.assertTrue(sp, "restored site has no Sales Person to map")
		map_sales_person(cust, sp)
		q = quotation_stub(cust, "")
		set_sales_person_from_customer(q)
		self.assertEqual(q.custom_sales_person, sp)

	def test_existing_value_without_mapping_is_preserved(self):
		cust = make_customer("R9B")  # fixture creates no sales_team rows
		q = quotation_stub(cust, "Paul")
		set_sales_person_from_customer(q)
		self.assertEqual(q.custom_sales_person, "Paul", "existing value must never be cleared")

	def test_existing_value_with_valid_mapping_follows_precedence(self):
		# Documented precedence: a valid Customer mapping always wins.
		cust = make_customer("R9C")
		sp = any_sales_person()
		map_sales_person(cust, sp)
		q = quotation_stub(cust, "Paul")
		set_sales_person_from_customer(q)
		self.assertEqual(q.custom_sales_person, sp)

	def test_empty_field_without_mapping_stays_empty(self):
		cust = make_customer("R9D")
		q = quotation_stub(cust, "")
		set_sales_person_from_customer(q)
		self.assertIn(q.custom_sales_person or "", ("",))

	def test_full_save_preserves_value_and_linkback_still_advances_presales(self):
		"""Production shape end to end: SAL-QTN-2026-01196's customer has no
		mapping and the field holds 'Paul'. A full save must keep 'Paul' AND the
		Quotation -> DCS -> Presales link-back must still run."""
		QTN, PR, DCS = "SAL-QTN-2026-01196", "PR-ZZTESTQADoNotUse-002", "DCS-2026-0008"
		if not frappe.db.exists("Quotation", QTN):
			self.skipTest("restored dataset does not carry the ZZTEST quotation")
		self.assertFalse(
			frappe.db.get_value("Sales Team", {"parenttype": "Customer", "parent": frappe.db.get_value("Quotation", QTN, "party_name")}, "name"),
			"fixture assumption broken: customer unexpectedly has a Sales Team mapping",
		)
		frappe.db.set_value("Quotation", QTN, "custom_sales_person", "Paul", update_modified=False)
		frappe.db.set_value("Presales Request", PR, "custom_deal_status", "ZZTEST-CLEARED", update_modified=False)
		q = frappe.get_doc("Quotation", QTN)
		q.flags.ignore_permissions = True
		q.save()
		self.assertEqual(
			frappe.db.get_value("Quotation", QTN, "custom_sales_person"), "Paul",
			"save must not clear custom_sales_person when no mapping exists",
		)
		self.assertNotEqual(
			frappe.db.get_value("Presales Request", PR, "custom_deal_status"), "ZZTEST-CLEARED",
			"link-back did not advance the Presales Request",
		)
