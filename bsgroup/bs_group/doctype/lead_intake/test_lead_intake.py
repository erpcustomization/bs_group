# Copyright (c) 2026, Tridots Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.bs_group.doctype.lead_intake.lead_intake import (
	normalize_email,
	normalize_phone,
)
from bsgroup.integrations import threecx

EXTRA_TEST_RECORD_DEPENDENCIES = []
# Lead Intake links to these ERPNext/Frappe doctypes, but the test suite builds
# its own records and the master data already exists on the target site. Ignoring
# them keeps setup fast and avoids pulling in ERPNext's heavy (and, on a populated
# site, colliding) global test-record bootstrap.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Lead", "Contact", "User"]


def _cleanup(external_ids):
	for eid in external_ids:
		for name in frappe.get_all("Lead Intake", filters={"external_interaction_id": eid}, pluck="name"):
			frappe.delete_doc("Lead Intake", name, force=True, ignore_permissions=True)


class IntegrationTestLeadIntake(IntegrationTestCase):
	"""End-to-end tests for the Lead Intake staging DocType and 3CX APIs."""

	# --- normalization -------------------------------------------------

	def test_normalize_email(self):
		self.assertEqual(normalize_email("  John.Doe@Example.COM "), "john.doe@example.com")
		self.assertIsNone(normalize_email(""))
		self.assertIsNone(normalize_email(None))
		self.assertIsNone(normalize_email("not-an-email"))

	def test_normalize_phone_uae(self):
		# Local UAE mobile with trunk 0 -> +971.
		self.assertEqual(normalize_phone("050 123 4567", "AE"), "+971501234567")
		# Already international.
		self.assertEqual(normalize_phone("+971 50 123 4567"), "+971501234567")
		# 00 prefix international.
		self.assertEqual(normalize_phone("0097150-123-4567"), "+971501234567")
		# Country code without plus.
		self.assertEqual(normalize_phone("971501234567", "AE"), "+971501234567")

	def test_normalize_phone_oman_and_empty(self):
		self.assertEqual(normalize_phone("92345678", "OM"), "+96892345678")
		self.assertIsNone(normalize_phone(""))
		self.assertIsNone(normalize_phone(None))
		self.assertIsNone(normalize_phone("abc"))

	# --- authentication ------------------------------------------------

	def test_guest_is_rejected(self):
		with self.set_user("Guest"):
			with self.assertRaises(frappe.PermissionError):
				threecx.chat_journal(external_interaction_id="GUEST-TEST-1", phone="+971501234567")
			with self.assertRaises(frappe.PermissionError):
				threecx.lookup(phone="+971501234567")

	# --- idempotency ---------------------------------------------------

	def test_idempotent_create(self):
		eid = "IDEMPOTENT-1"
		self.addCleanup(_cleanup, [eid])
		first = threecx.call_journal(external_interaction_id=eid, phone="+971501110000", subject="Hi")
		second = threecx.call_journal(external_interaction_id=eid, phone="+971501110000", subject="Hi")
		self.assertTrue(first["created"])
		self.assertFalse(second["created"])
		self.assertEqual(first["intake"], second["intake"])
		self.assertEqual(frappe.db.count("Lead Intake", {"external_interaction_id": eid}), 1)

	def test_missing_external_id_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			threecx.chat_journal(phone="+971501234567", subject="No id")

	# --- journal create then update -----------------------------------

	def test_journal_update(self):
		eid = "UPDATE-1"
		self.addCleanup(_cleanup, [eid])
		threecx.chat_journal(external_interaction_id=eid, phone="+971502220000", subject="First")
		res = threecx.chat_journal(external_interaction_id=eid, phone="+971502220000", subject="Second")
		self.assertFalse(res["created"])
		doc = frappe.get_doc("Lead Intake", res["intake"])
		self.assertEqual(doc.subject, "Second")

	# --- duplicate matching -------------------------------------------

	def test_duplicate_matching(self):
		eids = ["DUP-A", "DUP-B"]
		self.addCleanup(_cleanup, eids)
		a = threecx.chat_journal(external_interaction_id="DUP-A", phone="+971503330000")
		b = threecx.chat_journal(external_interaction_id="DUP-B", phone="050 333 0000")
		doc_b = frappe.get_doc("Lead Intake", b["intake"])
		self.assertEqual(doc_b.duplicate_of, a["intake"])

	# --- payload validation -------------------------------------------

	def test_payload_too_large(self):
		with self.assertRaises(frappe.ValidationError):
			threecx.chat_journal(
				external_interaction_id="BIG-1",
				phone="+971504440000",
				transcript="x" * (threecx.MAX_TRANSCRIPT_CHARS + 1),
			)

	# --- conversion ----------------------------------------------------

	def test_conversion_requires_qualified(self):
		eid = "CONV-GUARD"
		self.addCleanup(_cleanup, [eid])
		res = threecx.chat_journal(external_interaction_id=eid, phone="+971505550000")
		doc = frappe.get_doc("Lead Intake", res["intake"])
		with self.assertRaises(frappe.ValidationError):
			doc.convert_to_lead()

	def test_conversion_idempotent(self):
		eid = "CONV-1"
		self.addCleanup(_cleanup, [eid])
		res = threecx.chat_journal(
			external_interaction_id=eid, phone="+971506660000", full_name="Test Person"
		)
		doc = frappe.get_doc("Lead Intake", res["intake"])
		doc.db_set("status", "Qualified")
		doc.reload()

		lead_name = doc.convert_to_lead()
		self.addCleanup(lambda: frappe.delete_doc("Lead", lead_name, force=True, ignore_permissions=True))
		self.assertTrue(frappe.db.exists("Lead", lead_name))

		doc.reload()
		self.assertEqual(doc.status, "Converted")
		self.assertEqual(doc.converted_lead, lead_name)
		# Calling again returns the same Lead, creates no second one.
		self.assertEqual(doc.convert_to_lead(), lead_name)
