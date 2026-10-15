# Copyright (c) 2026, Tridots Tech and Contributors
# See license.txt

"""A-15: DCS Handover Condition guards, now live through the app controller
(after the Step-4 reconciliation the DocType is standard, so
``get_controller`` resolves to ``DCSHandoverCondition``)."""

from unittest.mock import patch

import frappe
from frappe.model.base_document import get_controller
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from bsgroup.api.dcs._common import raise_condition
from bsgroup.tests.dcs_fixtures import make_dcs


class IntegrationTestDCSHandoverCondition(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()

	def setUp(self):
		super().setUp()
		self.dcs = make_dcs(suffix=frappe.generate_hash(length=6), submit=True)

	def test_doctype_is_standard_and_controller_is_the_app_class(self):
		row = frappe.db.get_value("DocType", "DCS Handover Condition", ["custom", "module"], as_dict=True)
		self.assertFalse(frappe.utils.cint(row.custom))
		self.assertEqual(row.module, "BS Group")
		self.assertEqual(get_controller("DCS Handover Condition").__name__, "DCSHandoverCondition")

	def test_direct_creation_is_refused_and_service_creation_allowed(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({
				"doctype": "DCS Handover Condition", "dcs": self.dcs.name, "condition_no": 1, "condition_title": "forged",
				"category": "Blocker", "original_category": "Blocker", "domain": "Technical", "state": "Open",
			}).insert(ignore_permissions=True)
		name = raise_condition(self.dcs.name, "zztest_key", "ZZTEST blocker", "Blocker", "Technical", "detail")
		self.assertTrue(name)
		self.assertEqual(name, raise_condition(self.dcs.name, "zztest_key", "again", "Blocker", "Technical", "d"))

	def test_governed_fields_cannot_be_edited_directly(self):
		name = raise_condition(self.dcs.name, "zztest_gov", "ZZTEST watch", "Watch Item", "Commercial", "detail")
		c = frappe.get_doc("DCS Handover Condition", name)
		c.state = "Cleared"
		with self.assertRaises(frappe.ValidationError):
			c.save(ignore_permissions=True)

	def test_accepted_risk_is_immutable_and_never_cleared(self):
		name = raise_condition(self.dcs.name, "zztest_risk", "ZZTEST risk", "Blocker", "Commercial", "detail")
		c = frappe.get_doc("DCS Handover Condition", name)
		c.state, c.category = "Accepted Risk", "Accepted Risk"
		c.accepted_by, c.accepted_on = frappe.session.user, now_datetime()
		c.acceptance_reason, c.acknowledged, c.assigned_to = "ZZTEST reason", 1, frappe.session.user
		c.flags.dcs_api_write = 1
		c.save(ignore_permissions=True)
		c.reload()
		c.state = "Cleared"
		c.flags.dcs_api_write = 1
		with self.assertRaises(frappe.ValidationError):
			c.save(ignore_permissions=True)
		c.reload()
		c.acceptance_reason = "rewritten"
		c.flags.dcs_api_write = 1
		with self.assertRaises(frappe.ValidationError):
			c.save(ignore_permissions=True)

	def test_deletion_is_refused(self):
		name = raise_condition(self.dcs.name, "zztest_del", "ZZTEST del", "Watch Item", "Delivery", "detail")
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("DCS Handover Condition", name, ignore_permissions=True)
