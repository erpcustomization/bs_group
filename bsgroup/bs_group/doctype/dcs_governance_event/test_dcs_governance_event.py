# Copyright (c) 2026, Tridots Tech and Contributors
# See license.txt

"""A-15: the DCS Governance Event trust boundary (A-1 / A-13).

Runs on a staging or local site only (`bench --site <site> run-tests
--module bsgroup.bs_group.doctype.dcs_governance_event.test_dcs_governance_event`).
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.dcs import governance
from bsgroup.tests.dcs_fixtures import make_dcs


class IntegrationTestDCSGovernanceEvent(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()
		cls.dcs = make_dcs(suffix="GOV")

	def setUp(self):
		super().setUp()
		governance.reset_correlation_id()

	def _event_doc(self, **over):
		values = {
			"doctype": "DCS Governance Event",
			"dcs": self.dcs.name,
			"event_code": "ZZTEST_EVENT",
			"action_label": "test",
			"source_endpoint": "test",
			"changes": json.dumps([{"fieldname": "subject", "old_value": "a", "new_value": "b"}]),
		}
		values.update(over)
		return frappe.get_doc(values)

	# --- trust boundary -----------------------------------------------------
	def test_insert_without_flag_is_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self._event_doc().insert(ignore_permissions=True)

	def test_insert_with_flag_and_changes_succeeds(self):
		ev = self._event_doc()
		ev.flags.dcs_audit_write = 1
		ev.insert(ignore_permissions=True)
		self.assertTrue(ev.name)
		self.assertEqual(ev.change_count, 1)

	def test_empty_change_set_is_refused(self):
		ev = self._event_doc(changes=json.dumps([]))
		ev.flags.dcs_audit_write = 1
		with self.assertRaises(frappe.ValidationError):
			ev.insert(ignore_permissions=True)

	def test_actor_timestamp_and_correlation_are_server_derived(self):
		ev = self._event_doc(actor="Guest", event_timestamp="2000-01-01 00:00:00", correlation_id="FORGED")
		ev.flags.dcs_audit_write = 1
		ev.insert(ignore_permissions=True)
		self.assertEqual(ev.actor, frappe.session.user)
		self.assertNotEqual(ev.correlation_id, "FORGED")
		self.assertEqual(ev.correlation_id, governance.get_correlation_id())
		self.assertNotEqual(str(ev.event_timestamp)[:4], "2000")

	def test_correlation_id_is_shared_within_one_request_and_reset_between(self):
		a = governance.get_correlation_id()
		b = governance.get_correlation_id()
		self.assertEqual(a, b)
		governance.reset_correlation_id()
		self.assertNotEqual(a, governance.get_correlation_id())

	# --- append-only ---------------------------------------------------------
	def test_update_is_refused(self):
		ev = self._event_doc()
		ev.flags.dcs_audit_write = 1
		ev.insert(ignore_permissions=True)
		ev.reload()
		ev.reason = "tampered"
		with self.assertRaises(frappe.ValidationError):
			ev.save(ignore_permissions=True)

	def test_delete_is_refused(self):
		ev = self._event_doc()
		ev.flags.dcs_audit_write = 1
		ev.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("DCS Governance Event", ev.name, ignore_permissions=True)

	def test_no_role_holds_create_write_or_delete(self):
		meta = frappe.get_meta("DCS Governance Event")
		for perm in meta.permissions:
			self.assertFalse(perm.create, f"{perm.role} may create")
			self.assertFalse(perm.write, f"{perm.role} may write")
			self.assertFalse(perm.delete, f"{perm.role} may delete")

	# --- single writer + idempotency -------------------------------------------
	def test_record_governance_event_drops_noops_and_returns_empty(self):
		name = governance.record_governance_event(
			self.dcs.name, "ZZTEST_NOOP", changes=[{"field": "subject", "old": "x", "new": "x"}]
		)
		self.assertEqual(name, "")

	def test_record_governance_event_writes_once_per_request_key(self):
		key = governance.make_request_key("zztest_endpoint", {"dcs": self.dcs.name, "n": 1})
		first = governance.record_governance_event(
			self.dcs.name, "ZZTEST_IDEMP", changes=[{"field": "subject", "old": "a", "new": "b"}], request_key=key
		)
		self.assertTrue(first)
		self.assertEqual(governance.find_replay(key), first)
		with self.assertRaises(frappe.DuplicateEntryError):
			governance.record_governance_event(
				self.dcs.name, "ZZTEST_IDEMP", changes=[{"field": "subject", "old": "a", "new": "b"}], request_key=key
			)

	def test_request_key_is_stable_and_payload_sensitive(self):
		k1 = governance.make_request_key("e", {"a": 1, "b": 2})
		k2 = governance.make_request_key("e", {"b": 2, "a": 1})
		k3 = governance.make_request_key("e", {"a": 1, "b": 3})
		self.assertEqual(k1, k2)
		self.assertNotEqual(k1, k3)

	def test_source_event_id_is_null_not_blank_when_no_key(self):
		name = governance.record_governance_event(
			self.dcs.name, "ZZTEST_NOKEY", changes=[{"field": "subject", "old": "a", "new": "b"}]
		)
		self.assertIsNone(frappe.db.get_value("DCS Governance Event", name, "source_event_id"))
