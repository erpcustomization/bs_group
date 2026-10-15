"""Company identity must follow the selected company and retain safe selection."""
from unittest import TestCase
from unittest.mock import patch
import frappe
from bsgroup.api.dcs.presentation import company_context

class TestDCSCompanyPresentation(TestCase):
    def context(self, companies, selected, country, currency):
        with patch("frappe.has_permission", return_value=True), \
             patch("frappe.get_all", return_value=companies), \
             patch("frappe.get_list", return_value=[{"name":selected,"country":country,"default_currency":currency}]):
            return company_context(selected)

    def test_single_uae_hides_redundant_selector(self):
        result=self.context(["AE"],"AE","United Arab Emirates","AED")
        self.assertTrue(result["hide_company"])
        self.assertEqual((result["country_label"],result["base_currency"]),("UAE","AED"))

    def test_oman_identity_comes_from_company(self):
        result=self.context(["OM"],"OM","Oman","OMR")
        self.assertTrue(result["hide_company"])
        self.assertEqual((result["country_label"],result["base_currency"]),("Oman","OMR"))

    def test_multiple_companies_always_retain_selection(self):
        self.assertFalse(self.context(["AE","OM"],"OM","Oman","OMR")["hide_company"])

    def test_single_different_company_does_not_hide_existing_record_company(self):
        self.assertFalse(self.context(["AE"],"OLD","Oman","OMR")["hide_company"])

    def test_multiple_companies_without_selection_does_not_guess(self):
        with patch("frappe.has_permission",return_value=True), \
             patch("frappe.get_all",return_value=["AE","OM"]), patch("frappe.get_list") as lookup:
            self.assertEqual(company_context(),{"company":None,"hide_company":False})
            lookup.assert_not_called()

    def test_unpermitted_company_is_not_disclosed(self):
        with patch("frappe.has_permission",return_value=True), \
             patch("frappe.get_all",return_value=["AE"]), \
             patch("frappe.get_list",return_value=[]), \
             patch("frappe.throw",side_effect=frappe.PermissionError):
            with self.assertRaises(frappe.PermissionError):
                company_context("PRIVATE")

    def test_no_dcs_permission_stops_company_lookup(self):
        with patch("frappe.has_permission",return_value=False), \
             patch("frappe.throw",side_effect=frappe.PermissionError), patch("frappe.get_all") as lookup:
            with self.assertRaises(frappe.PermissionError):
                company_context("AE")
            lookup.assert_not_called()
