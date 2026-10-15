"""Exercise the workspace patch against native records and missing prerequisites."""
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from bsgroup.patches.v0_1 import dcs_workspace_counts as migration


class IntegrationTestDCSWorkspaceMigration(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.savepoint = "workspace_" + frappe.generate_hash(length=8)
        frappe.db.savepoint(self.savepoint)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point=self.savepoint)
        frappe.clear_cache()
        super().tearDown()

    def assert_cards_once(self):
        workspace = frappe.get_doc("Workspace", "DCS Governance")
        blocks = json.loads(workspace.content)
        for name in migration.CARDS:
            self.assertEqual(sum(b.get("type") == "number_card" and
                b.get("data", {}).get("number_card_name") == name for b in blocks), 1)
            self.assertEqual(sum(r.number_card_name == name for r in workspace.number_cards), 1)
        return workspace

    def test_bootstrap_missing_workspace_and_cards(self):
        # Renaming is transactional: preserve existing configuration for rollback.
        for doctype, names in (("Workspace", ("DCS Governance",)), ("Number Card", migration.CARDS)):
            for name in names:
                if frappe.db.exists(doctype, name):
                    frappe.rename_doc(doctype, name, "ZZTEST-" + frappe.generate_hash(length=10),
                        force=True)
        migration.execute()
        workspace = self.assert_cards_once()
        self.assertEqual(workspace.public, 1)
        self.assertTrue(workspace.shortcuts)
        for name in migration.CARDS:
            card = frappe.get_doc("Number Card", name)
            self.assertEqual(card.function, "Count")
            self.assertEqual(card.type, "Document Type")
            self.assertTrue(json.loads(card.filters_json))
        before = workspace.content
        migration.execute()
        self.assertEqual(self.assert_cards_once().content, before)

    def test_existing_customizations_survive_rerun(self):
        migration.execute()
        workspace = frappe.get_doc("Workspace", "DCS Governance")
        roles = [r.role for r in workspace.roles]
        module = workspace.module
        blocks = json.loads(workspace.content)
        marker = {"id": "zztest_custom_note", "type": "paragraph", "data": {"text": "Keep this custom note"}}
        blocks.append(marker)
        workspace.content = json.dumps(blocks)
        workspace.save(ignore_permissions=True)
        card = frappe.get_doc("Number Card", migration.CARDS[0])
        card.color = "#123456"
        card.save(ignore_permissions=True)
        for _ in range(2):
            migration.execute()
        workspace = self.assert_cards_once()
        self.assertEqual(json.loads(workspace.content).count(marker), 1)
        self.assertEqual([r.role for r in workspace.roles], roles)
        self.assertEqual(workspace.module, module)
        self.assertEqual(frappe.db.get_value("Number Card", migration.CARDS[0], "color"), "#123456")
