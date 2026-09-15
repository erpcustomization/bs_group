# Copyright (c) 2026, Tridots Tech and Contributors
# See license.txt

"""A-15: party model (A-5/A-6, D1-D3), duplicate guard (A-7), scheduler (A-8)
and the closed presales-sync endpoint (A-2)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from bsgroup.bs_group.doctype.presales_request import presales_request as pr_module
from bsgroup.tests.dcs_fixtures import make_customer, make_opportunity


class IntegrationTestPresalesRequest(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()

	def make_pr(self, party_type="Customer", suffix=None, **extra):
		suffix = suffix or frappe.generate_hash(length=6)
		opp = make_opportunity(party_type=party_type, suffix=suffix)
		values = {
			"doctype": "Presales Request",
			"opportunity": opp.name,
			"subject": f"ZZTEST PR {suffix}",
			"status": "Open",
			"request_date": nowdate(),
		}
		values.update(extra)
		pr = frappe.get_doc(values)
		pr.flags.ignore_links = True
		pr.insert(ignore_permissions=True, ignore_mandatory=True)
		return pr

	# --- party model ------------------------------------------------------------
	def test_party_is_taken_from_the_opportunity_and_customer_derived(self):
		pr = self.make_pr("Customer")
		self.assertEqual(pr.party_type, "Customer")
		self.assertEqual(pr.customer, pr.party)
		self.assertTrue(pr.organisation_name)
		# The name follows the documented rule PR-<slug(organisation_name)>-###. slug()
		# strips non-alphanumerics before turning whitespace into hyphens, which is what
		# names "Abela & Co" as PR-Abela-Co-001, so a fixture called
		# "ZZTEST-Customer-<suffix>" correctly loses its own hyphens.
		from bsgroup.utils.party import slug

		self.assertTrue(pr.name.startswith(f"PR-{slug(pr.organisation_name)}-"), pr.name)
		self.assertNotIn("ZZTEST-Customer", pr.name)

	def test_lead_sourced_request_has_no_customer(self):
		pr = self.make_pr("Lead")
		self.assertEqual(pr.party_type, "Lead")
		self.assertFalse(pr.customer)
		self.assertIn("ZZTEST Lead Co", pr.organisation_name)

	def test_customer_supplied_by_client_is_ignored_for_a_lead(self):
		other = make_customer("OTHER")
		pr = self.make_pr("Lead", customer=other)
		self.assertFalse(pr.customer)

	def test_customer_that_contradicts_the_party_is_refused(self):
		pr = self.make_pr("Customer")
		other = make_customer("OTHER")
		pr.customer = other
		with self.assertRaises(frappe.ValidationError):
			pr.save(ignore_permissions=True)

	def test_won_requires_a_customer_record(self):
		pr = self.make_pr("Lead", actual_hours=1)
		pr.status = "Won"
		with self.assertRaises(frappe.ValidationError):
			pr.save(ignore_permissions=True)
		# switch the party to a Customer created for the lead: now allowed
		pr.reload()
		pr.party_type, pr.party = "Customer", make_customer("WON")
		pr.status, pr.actual_hours = "Won", 1
		pr.flags.ignore_links = True
		pr.save(ignore_permissions=True)
		self.assertEqual(pr.customer, pr.party)

	# --- duplicate guard ----------------------------------------------------------
	def test_second_live_request_on_the_same_opportunity_is_refused(self):
		first = self.make_pr("Customer")
		dup = frappe.get_doc({
			"doctype": "Presales Request", "opportunity": first.opportunity, "subject": "dup", "status": "Open",
		})
		dup.flags.ignore_links = True
		with self.assertRaises(frappe.ValidationError):
			dup.insert(ignore_permissions=True, ignore_mandatory=True)

	def test_pre_existing_duplicate_stays_saveable(self):
		first = self.make_pr("Customer")
		dup = frappe.get_doc({
			"doctype": "Presales Request", "opportunity": first.opportunity, "subject": "legacy dup", "status": "Open",
			"party_type": first.party_type, "party": first.party, "organisation_name": first.organisation_name,
		})
		dup.flags.ignore_links = True
		dup.flags.ignore_validate = True
		dup.insert(ignore_permissions=True, ignore_mandatory=True)  # simulates historical data
		dup.reload()
		dup.subject = "legacy dup edited"
		dup.flags.ignore_links = True
		dup.save(ignore_permissions=True)  # the link did not change: no throw

	# --- scheduler ----------------------------------------------------------------
	def test_calculate_due_date_touches_only_open_changed_records(self):
		overdue = self.make_pr("Customer", due_date=add_days(nowdate(), -3))
		closed = self.make_pr("Customer", due_date=add_days(nowdate(), -3), status="Lost", actual_hours=1)
		before = frappe.db.get_value("Presales Request", overdue.name, "modified")
		summary = pr_module.calculate_due_date()
		self.assertGreaterEqual(summary["updated"], 1)
		self.assertEqual(summary["failed"], 0)
		self.assertEqual(frappe.db.get_value("Presales Request", overdue.name, "overdue"), 1)
		self.assertEqual(frappe.db.get_value("Presales Request", overdue.name, "delay_days"), 3)
		self.assertEqual(frappe.db.get_value("Presales Request", overdue.name, "modified"), before)
		self.assertFalse(frappe.db.get_value("Presales Request", closed.name, "overdue"))
		again = pr_module.calculate_due_date()
		self.assertEqual(again["updated"], 0)  # nothing changed since: no writes

	# --- A-2 --------------------------------------------------------------------
	def test_dcs_presales_sync_is_not_whitelisted(self):
		from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import dcs_presales_sync
		self.assertNotIn(dcs_presales_sync, frappe.whitelisted)
		with self.assertRaises(frappe.ValidationError):
			dcs_presales_sync("does-not-matter", source="rest")
