# Copyright (c) 2026, Tridots Tech and Contributors
# See license.txt

from unittest.mock import patch
import frappe
from frappe.tests.classes import integration_test_case
from frappe.tests.classes import integration_test_case
from frappe.tests import IntegrationTestCase


class IntegrationTestDealCostSheet(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()

    def make_submitted_dcs(self):
        doc = frappe.get_doc(
            {
                "doctype": "Deal Cost Sheet",
                "opportunity": "ZZ-QA-OPP-SUBMITTED-UPDATES",
                "subject": "ZZ-QA-Submitted DCS Updates",
                "deal_owner": "Administrator",
                "items": [{"item_code": "_Test Extra Item 1", "qty": 1, "cost_rate": 1}],
            }
        )
        doc.flags.ignore_links = True
        doc.insert()
        doc.flags.ignore_links = True
        doc.submit()
        return doc

    def test_submitted_dcs_allows_only_governed_updates(self):
        allowed_fields = {
            field.fieldname
            for field in frappe.get_meta("Deal Cost Sheet").fields
            if field.allow_on_submit
        }
        self.assertEqual(allowed_fields, {"deal_owner", "workflow_state"})

        doc = self.make_submitted_dcs()
        doc.deal_owner = "Guest"
        doc.save()

        self.assertEqual(
            frappe.db.get_value("Deal Cost Sheet", doc.name, "deal_owner"),
            "Guest",
        )

        doc.subject = "ZZ-QA-Submitted DCS Must Stay Locked"
        with self.assertRaises(frappe.ValidationError):
            doc.save()
