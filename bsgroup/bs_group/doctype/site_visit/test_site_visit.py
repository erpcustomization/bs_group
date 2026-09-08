# Copyright (c) 2026, Tridots Tech and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from bsgroup.bs_group.doctype.site_visit.site_visit import SiteVisit
from unittest import TestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class TestSiteVisit(TestCase):
	"""
	Unit tests for Site Visit customer derivation.
	"""

	@patch.object(frappe.db, "get_value", return_value="Customer A")
	def test_customer_is_derived_from_presales_request(self, get_value):
		visit = object.__new__(SiteVisit); visit.__dict__.update(presales_request="PR-TEST", customer="Wrong Customer")
		visit._set_customer_from_presales_request()
		self.assertEqual(visit.customer, "Customer A")
		get_value.assert_called_once_with("Presales Request", "PR-TEST", "customer")

	@patch.object(frappe.db, "get_value", return_value=None)
	def test_presales_request_without_customer_is_rejected(self, _get_value):
		visit = object.__new__(SiteVisit); visit.__dict__.update(presales_request="PR-TEST")
		with self.assertRaises(frappe.ValidationError):
			visit._set_customer_from_presales_request()
