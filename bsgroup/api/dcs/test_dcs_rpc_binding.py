"""Transport-level (RPC) argument-binding regression tests for the governed DCS
endpoints.

Each test drives an endpoint through Frappe's real argument binding
(``frappe.call(dotted_path, **fields)`` -> ``frappe.get_newargs`` -> the
function), which is the exact seam the HTTP handler (``frappe.handler``) uses.
The direct-Python tests in ``test_dcs_api`` cannot catch a binding regression,
because a plain Python call passes ``**kwargs`` straight through regardless of
the callable's advertised signature; only the RPC path consults the signature.

Regression guarded: a ``governed_endpoint`` wrapper whose public signature was
masked to ``(args)`` (via ``functools.wraps``' ``__wrapped__``) made Frappe drop
every real request field, so every endpoint answered "dcs is required" over RPC
and no Governance Event could be written.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.dcs import governance
from bsgroup.tests.dcs_fixtures import ensure, initialise_living_position, make_dcs, make_user

COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]

SCREEN3 = "bsgroup.api.dcs.negotiation.dcs_screen3"
SCREEN4 = "bsgroup.api.dcs.approval.dcs_screen4"
SCREEN5 = "bsgroup.api.dcs.handover.dcs_screen5"
RECORD_AWARD = "bsgroup.api.dcs.award.dcs_record_award"
APPLY_REVISION = "bsgroup.api.dcs.negotiation.dcs_apply_revision"


class IntegrationTestDCSRpcBinding(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()
		for role in COMMERCIAL_ROLES + ["Technical Engineer", "Project Manager", "Sales User", "Presales"]:
			ensure("Role", role, {"role_name": role}, insert=False)
		cls.md = make_user(
			"zztest-md@example.com",
			["System Manager", "Sales Manager", "Commercial Controller", "Managing Director"],
		)
		cls.tech = make_user("zztest-tech@example.com", ["Technical Engineer", "Project Manager"])
		cls.nobody = make_user("zztest-nobody@example.com", ["Employee"])

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		governance.reset_correlation_id()
		self.dcs = make_dcs(suffix=frappe.generate_hash(length=6), submit=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# 1. read screens 3/4/5 bind their argument over the RPC path
	def test_rpc_read_screens_bind_arguments(self):
		frappe.set_user(self.md)
		for dotted in (SCREEN3, SCREEN4, SCREEN5):
			r = frappe.call(dotted, dcs=self.dcs.name)
			self.assertIsInstance(r, dict, dotted)
			self.assertEqual(r.get("ok"), 1, (dotted, r.get("error")))
			self.assertNotIn("dcs is required", (r.get("error") or ""), dotted)

	# 2. a genuinely missing argument is still rejected structurally (not a silent drop)
	def test_rpc_missing_argument_is_rejected(self):
		frappe.set_user(self.md)
		r = frappe.call(SCREEN5)  # no dcs
		self.assertIsInstance(r, dict)
		self.assertEqual(r.get("ok"), 0)
		self.assertIn("dcs is required", (r.get("error") or ""))

	# 3. permission rejection travels the same RPC path
	def test_rpc_permission_rejection(self):
		frappe.set_user(self.tech)  # may read the sheet, may not write it
		self.assertTrue(frappe.has_permission("Deal Cost Sheet", "read"))
		self.assertFalse(frappe.has_permission("Deal Cost Sheet", "write"))
		r = frappe.call(APPLY_REVISION, dcs=self.dcs.name, source="Technical", reason="ZZTEST", new_total_cost=900)
		self.assertEqual(r.get("ok"), 0)
		self.assertEqual(r.get("permission_denied"), 1)
		frappe.set_user(self.nobody)  # no read access at all -> raises over the same path
		with self.assertRaises(frappe.PermissionError):
			frappe.call(SCREEN5, dcs=self.dcs.name)

	# 4. a state-changing endpoint binds over RPC and writes exactly ONE app-owned event
	def test_rpc_state_change_writes_exactly_one_app_owned_event(self):
		frappe.set_user(self.md)
		lp = initialise_living_position(self.dcs.name)
		self.assertEqual(lp.get("ok"), 1, lp.get("error"))
		before = frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name})
		r = frappe.call(RECORD_AWARD, dcs=self.dcs.name, award_reference="ZZTEST-RPC-PO", evidence_type="Customer PO")
		self.assertEqual(r.get("ok"), 1, r.get("error"))  # proves the args bound over RPC
		self.assertTrue(r.get("governance_event"))
		after = frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name})
		self.assertEqual(after - before, 1, "exactly one app-owned event, no duplicate")
		ev = frappe.get_doc("DCS Governance Event", r["governance_event"])
		self.assertTrue((ev.source_event_id or "").startswith("REQ-"))
		self.assertTrue(ev.correlation_id)
		self.assertFalse((ev.correlation_id or "").startswith("AUTH"))
		self.assertEqual(ev.source_endpoint, "dcs_record_award")
		self.assertEqual(ev.actor, self.md)

	# 5. idempotency still holds over RPC: an identical request replays, writes no second event
	def test_rpc_idempotent_replay(self):
		frappe.set_user(self.md)
		lp = initialise_living_position(self.dcs.name)
		self.assertEqual(lp.get("ok"), 1, lp.get("error"))
		first = frappe.call(RECORD_AWARD, dcs=self.dcs.name, award_reference="ZZTEST-IDEM", evidence_type="Customer PO")
		self.assertEqual(first.get("ok"), 1, first.get("error"))
		events = frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name})
		second = frappe.call(RECORD_AWARD, dcs=self.dcs.name, award_reference="ZZTEST-IDEM", evidence_type="Customer PO")
		self.assertEqual(second.get("idempotent_replay"), 1)
		self.assertEqual(second.get("governance_event"), first.get("governance_event"))
		self.assertEqual(frappe.db.count("DCS Governance Event", {"dcs": self.dcs.name}), events)
