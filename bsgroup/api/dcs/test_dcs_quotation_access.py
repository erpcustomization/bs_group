"""Regression: managers can quote with select-only account access."""
from unittest.mock import patch
import frappe
from frappe.tests import IntegrationTestCase
from bsgroup.tests.dcs_fixtures import make_dcs, make_user
from bsgroup.patches.v0_1.dcs_quotation_account_select import execute
from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation


class IntegrationTestDCSQuotationAccess(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()
        cls.manager = make_user("zztest-quote-manager@example.com", ["Sales Manager"])
        cls.presales = make_user("zztest-quote-presales@example.com", ["Presales"])

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        execute()

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_manager_creates_charge_quotation_without_account_read_or_write(self):
        item = frappe.db.get_value("Item", {"disabled": 0}, "name")
        frappe.db.set_single_value("BS Group Settings", "dcs_addtional_item", item)
        d = make_dcs(suffix=frappe.generate_hash(length=8), submit=True, deal_owner=self.manager,
                     addtional_charges=[{"amount": 100, "selling_amount": 150}])
        frappe.set_user(self.manager)
        account = frappe.db.get_value("Company", d.company, "default_receivable_account")
        self.assertTrue(frappe.has_permission("Account", "select", doc=account))
        self.assertFalse(frappe.has_permission("Account", "read", doc=account))
        self.assertFalse(frappe.has_permission("Account", "write", doc=account))
        q = frappe.get_doc("Quotation", make_quotation(d.name, payment_terms="ZZTEST 100% on delivery"))
        self.assertEqual(q.total, 1650)
        self.assertEqual(q.items[-1].amount, 150)
        self.assertEqual(q.custom_dcs_revision_reference, d.custom_revision_reference)

    def test_permission_patch_is_idempotent_and_preserves_other_rules(self):
        before = frappe.get_all("Custom DocPerm", filters={"parent":"Account"}, fields=["name","role","read","write","report","select","create","delete"])
        execute()
        after = frappe.get_all("Custom DocPerm", filters={"parent":"Account"}, fields=["name","role","read","write","report","select","create","delete"])
        self.assertEqual(sorted(before,key=lambda r:r.name), sorted(after,key=lambda r:r.name))
        self.assertEqual(frappe.db.count("Custom DocPerm", {"parent":"Account","role":"Sales Manager","permlevel":0,"if_owner":0}), 1)

    def test_presales_still_cannot_create_quotation(self):
        d = make_dcs(suffix=frappe.generate_hash(length=8), submit=True)
        frappe.set_user(self.presales)
        self.assertFalse(frappe.has_permission("Quotation", "create"))
        with self.assertRaises(frappe.PermissionError):
            make_quotation(d.name)
