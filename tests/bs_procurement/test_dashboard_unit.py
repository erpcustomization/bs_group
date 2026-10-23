"""Local checks for dashboard totals and permission boundaries; no ERP writes."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Row(dict):
    __getattr__ = dict.get


fake = SimpleNamespace(whitelist=lambda: lambda f: f, session=SimpleNamespace(user="buyer"),
                       has_permission=Mock(return_value=True), get_list=Mock())
utilities = SimpleNamespace(flt=lambda v: float(v or 0), nowdate=lambda: "2026-10-23",
                            now_datetime=lambda: "2026-10-23 12:00:00")
company_filter = Mock(side_effect=lambda dt, names: names)
spec = importlib.util.spec_from_file_location("dashboard_unit_target",
    Path(__file__).resolve().parents[2] / "bsgroup" / "procurement_dashboard.py")
dashboard = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"frappe": fake, "frappe.utils": utilities,
     "bsgroup.procurement_lists": SimpleNamespace(visible_company_names=company_filter)}):
    spec.loader.exec_module(dashboard)


def row(name, **values):
    return Row(name=name, company=values.pop("company", "Oman"), modified="2026-10-22 12:00:00",
               docstatus=values.pop("docstatus", 1), status=values.pop("status", "Submitted"), **values)


class DashboardTests(unittest.TestCase):
    def test_denied_type_never_queries_records(self):
        with patch.object(fake, "has_permission", return_value=False), patch.object(fake, "get_list") as query:
            self.assertIsNone(dashboard.visible_rows("Purchase Invoice", [], {}))
            query.assert_not_called()

    def test_company_permissions_filter_the_visible_rows(self):
        with patch.object(fake, "get_list", return_value=[row("allowed"), row("hidden")]), \
                patch.object(dashboard, "visible_company_names", return_value=["allowed"]):
            self.assertEqual([r.name for r in dashboard.visible_rows("Purchase Order", [], {})], ["allowed"])

    def test_balances_currencies_and_company_scope(self):
        data = {
            "Material Request": [row("PR1", docstatus=0, workflow_state="Pending Approval")],
            "Purchase Order": [
                row("PO1", custom_bsp_approval_state="Approved", currency="OMR", grand_total=100,
                    schedule_date="2026-10-20", per_received=20),
                row("PO2", company="Dubai", custom_bsp_approval_state="Approved", currency="AED",
                    grand_total=400, per_received=100),
                row("PO3", docstatus=2, custom_bsp_approval_state="Approved", currency="OMR", grand_total=999)],
            "Purchase Invoice": [
                row("INV1", workflow_state="Approved", currency="USD", party_account_currency="OMR",
                    outstanding_amount=30, due_date="2026-10-20", is_return=0),
                row("INV2", docstatus=0, workflow_state="Draft", currency="OMR", outstanding_amount=900),
                row("RET", workflow_state="Approved", currency="OMR", outstanding_amount=50, is_return=1)]}
        with patch.object(dashboard, "visible_rows", side_effect=lambda dt, *a: data[dt]):
            result = dashboard.get_dashboard()
            self.assertEqual(result["poValue"], {"OMR": 100, "AED": 400})
            self.assertEqual(result["unpaidValue"], {"OMR": 30})
            self.assertEqual((result["pending"], result["awaitingReceipt"], result["overduePayments"]), (1, 1, 1))
            self.assertEqual(result["attention"][0]["id"], "INV1")
            for metric, names in {"pending": ["PR1"], "awaitingReceipt": ["PO1"],
                                  "unpaidCount": ["INV1"], "overduePayments": ["INV1"]}.items():
                self.assertEqual([r["id"] for r in result["records"][metric]], names)
                self.assertEqual(len(result["records"][metric]), result[metric])
            scoped = dashboard.get_dashboard("Dubai")
            self.assertEqual(scoped["poValue"], {"AED": 400})
            self.assertEqual(scoped["stages"]["requests"]["total"], 0)
            self.assertTrue(all(not rows for rows in scoped["records"].values()))

    def test_restricted_sections_are_not_reported_as_empty(self):
        with patch.object(dashboard, "visible_rows", return_value=None):
            result = dashboard.get_dashboard()
            self.assertIsNone(result["stages"]["payments"])
            self.assertIn("Payment Order", result["restricted"])
            self.assertTrue(all(not rows for rows in result["records"].values()))


if __name__ == "__main__":
    unittest.main()
