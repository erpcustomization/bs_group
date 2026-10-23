"""Permission and attribution checks for read-only PO connections."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Doc(dict):
    __getattr__ = dict.get

    @property
    def items(self):
        return self.get("items", [])


fake = SimpleNamespace(whitelist=lambda: lambda f: f, has_permission=Mock(return_value=True),
    get_list=Mock(), get_doc=Mock(), PermissionError=PermissionError)
spec = importlib.util.spec_from_file_location("connections_target",
    Path(__file__).resolve().parents[2] / "bsgroup" / "procurement_connections.py")
connections = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"frappe": fake, "frappe.utils": SimpleNamespace(flt=lambda v: float(v or 0)),
    "bsgroup.procurement": SimpleNamespace(access=lambda d: d, load=Mock()),
    "bsgroup.procurement_accounts": SimpleNamespace(document_state=lambda d: "Submitted")}):
    spec.loader.exec_module(connections)


def invoice():
    return Doc(name="INV1", doctype="Purchase Invoice", company="Oman", currency="OMR",
        grand_total=300, outstanding_amount=200, items=[
            Doc(purchase_order="PO1", item_code="A", qty=1, uom="Nos", rate=100, amount=100),
            Doc(purchase_order="PO2", item_code="B", qty=2, uom="Nos", rate=100, amount=200)])


class ConnectionsTests(unittest.TestCase):
    def test_no_read_permission_does_not_query_documents(self):
        with patch.object(fake, "has_permission", return_value=False), patch.object(fake, "get_list") as query:
            self.assertEqual(connections.visible("Purchase Invoice", {"hidden"}, "Oman"), ([], True))
            query.assert_not_called()

    def test_document_company_access_rechecked(self):
        with patch.object(fake, "get_list", return_value=["blocked"]), \
             patch.object(fake, "get_doc", return_value=Doc(name="blocked")), \
             patch.object(connections, "access", side_effect=PermissionError):
            self.assertEqual(connections.visible("Purchase Invoice", {"blocked"}, "Oman"), ([], True))

    def test_shared_invoice_does_not_attribute_whole_total_to_po(self):
        with patch.object(connections, "ledger", return_value=None), patch.object(connections, "attachments", return_value=[]):
            result = connections.purchase_record(invoice(), "PO1")
        self.assertTrue(result["shared"])
        self.assertEqual(dict(result["facts"])["Document total"], 300)
        self.assertEqual(dict(result["facts"])["Lines linked to this PO (before document taxes)"], 100)
        self.assertEqual(len(result["tables"][0]["rows"]), 1)
        self.assertTrue(result["ledgerRestricted"])

    def test_indirect_return_is_not_reported_as_zero_allocated(self):
        doc = invoice()
        doc.update(is_return=1, return_against="INV1", items=[Doc(item_code="A", qty=-1, amount=-100)])
        with patch.object(connections, "ledger", return_value=None), patch.object(connections, "attachments", return_value=[]):
            result = connections.purchase_record(doc, "PO1")
        self.assertEqual(dict(result["facts"])["Lines linked to this PO (before document taxes)"], "Not directly allocated")
        self.assertIn("original document", result["note"])

    def test_hidden_invoices_do_not_expand_payment_queries(self):
        calls = []
        def candidates(dt, filters, field="parent"):
            calls.append((dt, filters))
            return {"hidden-invoice"} if dt == "Purchase Invoice Item" else set()
        with patch.object(connections, "load", return_value=Doc(custom_bsp_managed=1, company="Oman")), \
             patch.object(connections, "candidates", side_effect=candidates), \
             patch.object(connections, "visible", return_value=([], True)):
            result = connections.get_connections("PO1")
        self.assertTrue(all(not s["records"] for s in result["sections"]))
        self.assertFalse(any(filters.get("reference_name") == "hidden-invoice" for _, filters in calls))


if __name__ == "__main__":
    unittest.main()
