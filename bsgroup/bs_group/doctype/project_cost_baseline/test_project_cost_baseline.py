# Copyright (c) 2026, Tridots Tech and Contributors
# See license.txt

from unittest.mock import patch
import frappe
from frappe.tests.classes import integration_test_case
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class IntegrationTestProjectCostBaseline(IntegrationTestCase):
	"""Covers the DEV-020 acceptance scenarios end to end."""

	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()

	def ensure_link_record(self, doctype, name, values):
		if not frappe.db.exists(doctype, name):
			doc = frappe.get_doc({"doctype": doctype, "name": name, **values})
			doc.db_insert()
		return name

	def make_project(self, suffix):
		project_type = self.ensure_link_record("Project Type", "ZZ-QA-PCB-Project-Type", {"project_type": "ZZ-QA-PCB-Project-Type"})
		customer = self.ensure_link_record("Customer", "ZZ-QA-PCB-Customer", {"customer_name": "ZZ-QA-PCB-Customer", "customer_type": "Company"})
		manager = self.ensure_link_record("Employee", "ZZ-QA-PCB-Employee", {"first_name": "ZZ QA PCB", "status": "Active"})
		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": f"PCB Test Project {suffix}",
			"project_type": project_type,
			"customer": customer,
			"custom_project_manager": manager,
			"custom_project_description": "Test project for Project Cost Baseline",
			"expected_start_date": nowdate(),
			"expected_end_date": nowdate(),
		})
		project.insert(ignore_permissions=True, ignore_mandatory=True)
		return project

	def make_opportunity(self, suffix):
		opp = frappe.get_doc({
			"doctype": "Opportunity",
			"opportunity_from": "Customer",
			"customer_name": f"PCB Test Customer {suffix}",
		})
		opp.insert(ignore_permissions=True, ignore_mandatory=True)
		return opp

	def make_dcs(self, project=None, submit=False, suffix="A"):
		opp = self.make_opportunity(suffix)
		dcs = frappe.get_doc({
			"doctype": "Deal Cost Sheet",
			"opportunity": opp.name,
			"subject": f"PCB Test DCS {suffix}",
			"project": project.name if project else None,
			"items": [{
				"item_code": frappe.db.get_value("Item", {"disabled": 0}, "name"),
				"qty": 1,
				"cost_rate": 1000,
				"selling_rate": 1500,
			}],
		})
		dcs.insert(ignore_permissions=True, ignore_mandatory=True)
		if submit:
			dcs.submit()
		return dcs

	def test_dcs_without_project_succeeds(self):
		dcs = self.make_dcs(project=None, suffix="NoProj")
		self.assertFalse(dcs.project)

	def test_baseline_from_projectless_dcs_fails(self):
		dcs = self.make_dcs(project=None, submit=True, suffix="PCB-NoProj")
		project = self.make_project("PCB-NoProj")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs.name,
		})
		with self.assertRaises(frappe.ValidationError):
			baseline.insert(ignore_permissions=True)

	def test_dcs_with_project_succeeds(self):
		project = self.make_project("DCS-OK")
		dcs = self.make_dcs(project=project, suffix="OK")
		self.assertEqual(dcs.project, project.name)

	def test_baseline_amount_matches_dcs(self):
		project = self.make_project("Baseline-Amt")
		dcs = self.make_dcs(project=project, submit=True, suffix="Amt")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs.name,
		})
		baseline.insert(ignore_permissions=True)
		self.assertEqual(baseline.baseline_amount, dcs.total_cost)

	def test_baseline_with_mismatched_project_fails(self):
		project_a = self.make_project("Mismatch-A")
		project_b = self.make_project("Mismatch-B")
		dcs = self.make_dcs(project=project_a, submit=True, suffix="Mismatch")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project_b.name,
			"deal_cost_sheet": dcs.name,
		})
		with self.assertRaises(frappe.ValidationError):
			baseline.insert(ignore_permissions=True)

	def test_baseline_from_unsubmitted_dcs_fails(self):
		project = self.make_project("Unsubmitted")
		dcs = self.make_dcs(project=project, submit=False, suffix="Unsubmitted")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs.name,
		})
		with self.assertRaises(frappe.ValidationError):
			baseline.insert(ignore_permissions=True)
			baseline.submit()

	def test_second_active_baseline_for_same_project_fails(self):
		project = self.make_project("Dup-Active")
		dcs1 = self.make_dcs(project=project, submit=True, suffix="Dup1")
		dcs2 = self.make_dcs(project=project, submit=True, suffix="Dup2")

		baseline1 = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs1.name,
		})
		baseline1.insert(ignore_permissions=True)
		baseline1.submit()

		baseline2 = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs2.name,
		})
		baseline2.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			baseline2.submit()

	def test_approved_baseline_amount_is_locked(self):
		project = self.make_project("Locked")
		dcs = self.make_dcs(project=project, submit=True, suffix="Locked")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs.name,
		})
		baseline.insert(ignore_permissions=True)
		baseline.submit()

		reloaded = frappe.get_doc("Project Cost Baseline", baseline.name)
		reloaded.baseline_amount = 1
		with self.assertRaises(frappe.exceptions.UpdateAfterSubmitError):
			reloaded.save(ignore_permissions=True)

	def test_baseline_revision_preserves_previous_version(self):
		project = self.make_project("Revision")
		dcs = self.make_dcs(project=project, submit=True, suffix="Revision")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs.name,
		})
		baseline.insert(ignore_permissions=True)
		baseline.submit()

		frappe.db.set_value("Project Cost Baseline", baseline.name, "docstatus", 2, update_modified=False)
		baseline.reload()
		amended = frappe.copy_doc(baseline)
		amended.docstatus = 0
		amended.amended_from = baseline.name
		amended.insert(ignore_permissions=True)
		amended.submit()

		self.assertEqual(amended.revision, baseline.revision + 1)
		self.assertEqual(amended.amended_from, baseline.name)
		# Previous version remains on record, just cancelled - not deleted.
		self.assertTrue(frappe.db.exists("Project Cost Baseline", baseline.name))
		self.assertEqual(frappe.db.get_value("Project Cost Baseline", baseline.name, "docstatus"), 2)

	def test_variance_calculated_against_baseline(self):
		from bsgroup.utils.project_cost_baseline import get_project_cost_summary

		project = self.make_project("Variance")
		dcs = self.make_dcs(project=project, submit=True, suffix="Variance")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs.name,
		})
		baseline.insert(ignore_permissions=True)
		baseline.submit()

		frappe.db.set_value("Project", project.name, "total_expense_claim", baseline.baseline_amount + 500)

		summary = get_project_cost_summary(project.name)
		self.assertEqual(summary["baseline_amount"], baseline.baseline_amount)
		self.assertTrue(summary["is_overrun"])
		self.assertEqual(summary["variance"], -500)

	def test_committed_purchase_order_alone_triggers_overrun(self):
		"""A submitted-but-unbilled Purchase Order must count as exposure
		against the baseline on its own - ERPNext core never rolls an open PO
		into `Project.total_purchase_cost` (that only happens on Purchase
		Receipt/Invoice), so judging overrun by actual cost alone would let a
		Project blow past its baseline via open POs with no warning."""
		from bsgroup.utils.project_cost_baseline import get_project_cost_summary

		project = self.make_project("PO-Overrun")
		dcs = self.make_dcs(project=project, submit=True, suffix="PO-Overrun")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs.name,
		})
		baseline.insert(ignore_permissions=True)
		baseline.submit()

		supplier = self.ensure_link_record("Supplier", "ZZ-QA-PCB-Supplier", {"supplier_name": "ZZ-QA-PCB-Supplier", "supplier_type": "Company"})
		item = frappe.db.get_value("Item", {"disabled": 0}, "name")
		po = frappe.get_doc({
			"doctype": "Purchase Order",
			"supplier": supplier,
			"company": project.company,
			"schedule_date": nowdate(),
			"project": project.name,
			"items": [{
				"item_code": item,
				"qty": 1,
				"rate": baseline.baseline_amount + 4000,
				"schedule_date": nowdate(),
			}],
		})
		po.insert(ignore_permissions=True, ignore_mandatory=True)
		po.submit()

		reloaded = frappe.get_doc("Project Cost Baseline", baseline.name)
		self.assertEqual(reloaded.remaining_amount, -4000)

		summary = get_project_cost_summary(project.name)
		self.assertTrue(summary["is_overrun"])

	def test_overrun_blocks_purchase_order_submit_under_block_policy(self):
		frappe.db.set_value("BS Group Settings", None, "cost_overrun_policy", "Block")
		self.addCleanup(frappe.db.set_value, "BS Group Settings", None, "cost_overrun_policy", "Warn")

		project = self.make_project("PO-Block")
		dcs = self.make_dcs(project=project, submit=True, suffix="PO-Block")

		baseline = frappe.get_doc({
			"doctype": "Project Cost Baseline",
			"project": project.name,
			"deal_cost_sheet": dcs.name,
		})
		baseline.insert(ignore_permissions=True)
		baseline.submit()

		supplier = self.ensure_link_record("Supplier", "ZZ-QA-PCB-Supplier", {"supplier_name": "ZZ-QA-PCB-Supplier", "supplier_type": "Company"})
		item = frappe.db.get_value("Item", {"disabled": 0}, "name")
		po = frappe.get_doc({
			"doctype": "Purchase Order",
			"supplier": supplier,
			"company": project.company,
			"schedule_date": nowdate(),
			"project": project.name,
			"items": [{
				"item_code": item,
				"qty": 1,
				"rate": baseline.baseline_amount + 4000,
				"schedule_date": nowdate(),
			}],
		})
		po.insert(ignore_permissions=True, ignore_mandatory=True)
		with self.assertRaises(frappe.ValidationError):
			po.submit()
