"""Proofs for the manifest (allow-list) party backfill: ``bsgroup.utils.party_backfill`` and the
``Party Backfill Run`` DocType.

Run on staging / local only:
    bench --site rel1-test.local run-tests --module bsgroup.tests.test_party_backfill_allowlist

Every fixture is a ZZTEST record created here; no production identifier appears in this file.

What is proven
--------------
1. the gate: nothing is written without mode Apply AND the site-config flag AND the manifest
   sha256; a Dry Run never writes; the flag is cleared after every Apply/Restore attempt,
   refused, applied or raised;
2. only manifest records change, only in the approved fields, ``modified`` untouched; a
   record outside the manifest is byte-for-byte unchanged;
3. before-values are exported for every record written and Restore puts them back;
4. a second execution changes zero records;
5. drift is rejected, never adjusted: before values, Opportunity party, a link, record
   missing, tampered after values - and a change between evaluation and the locked
   re-evaluation immediately before the write;
6. a populated party is preserved unless the entry explicitly approves overwriting it;
7. a Won, Customer-sourced sheet keeps its Customer and still satisfies D3 after the fill;
8. a normal save works after the fill and leaves the filled values in place;
9. the DocType path (private manifest File, run document, attached exports, immutability);
10. an armed Apply that fails input validation or manifest loading (missing private file,
    public path, malformed JSON, wrong schema, duplicate entries, missing SHA token) writes
    nothing and still leaves the flag absent;
11. if the flag cannot be removed after an Apply, the run raises instead of completing.
"""

import hashlib
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from bsgroup.tests.dcs_fixtures import make_customer, make_dcs
from bsgroup.utils import party_backfill as pb
from bsgroup.utils.party import require_customer

PF = list(pb.PARTY_FIELDS)


def _legacy(doc, customer_text):
	"""Put a record into its pre-REL-1 shape: no party, only a customer value (free text or a real link)."""
	frappe.db.set_value(
		doc.doctype, doc.name,
		{"party_type": None, "party": None, "organisation_name": None, "customer": customer_text},
		update_modified=False,
	)


def _vals(doctype, name):
	return pb._party_values(frappe.db.get_value(doctype, name, PF, as_dict=True))


def _entry(doctype, name, **override):
	"""A manifest entry captured from the live record, exactly as the production manifest is built."""
	snap = pb.snapshot(doctype, name)
	entry = {
		"doctype": doctype, "name": name, "before": snap["before"],
		"after": pb._recomputed_after(doctype, snap["row"]), "source": snap["source"],
		"allow_overwrite_populated": False,
	}
	entry.update(override)
	return entry


def _manifest(*entries):
	return {"schema": pb.SCHEMA, "entries": list(entries)}


def _sha(manifest):
	return pb.load_manifest(manifest)[1]


def _rows(result):
	import csv
	import io
	return {r["name"]: r for r in csv.DictReader(io.StringIO(result["evaluation_csv"]))}


class IntegrationTestPartyBackfillAllowlist(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
			super().setUpClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.conf.pop(pb.CONF_FLAG, None)
		h = frappe.generate_hash(length=5)
		self.lead_dcs = make_dcs(party_type="Lead", suffix="AL" + h, submit=True)
		self.cust_dcs = make_dcs(party_type="Customer", suffix="AC" + h)
		self.control = make_dcs(party_type="Lead", suffix="AX" + h)
		self.free_text = "ZZTEST free text " + h
		_legacy(self.lead_dcs, self.free_text)          # free-text customer, Lead-sourced Opportunity
		_legacy(self.cust_dcs, self.cust_dcs.party)     # real Customer link, Customer-sourced Opportunity
		_legacy(self.control, "ZZTEST control " + h)    # NOT in any manifest
		self.control_row = frappe.db.get_value("Deal Cost Sheet", self.control.name, ["*"], as_dict=True)

	def tearDown(self):
		frappe.conf.pop(pb.CONF_FLAG, None)
		frappe.set_user("Administrator")
		super().tearDown()

	# --- helpers -------------------------------------------------------------------
	def _run(self, mode, manifest, sha="auto", gate=True):
		if gate:
			frappe.conf[pb.CONF_FLAG] = 1
		if sha == "auto":
			sha = pb.load_manifest(manifest, pb.SCHEMA_BEFORE_VALUES if mode == pb.MODE_RESTORE else pb.SCHEMA)[1]
		return pb.execute(mode, manifest, sha)

	def _both(self):
		return _manifest(_entry("Deal Cost Sheet", self.lead_dcs.name), _entry("Deal Cost Sheet", self.cust_dcs.name))

	def _assert_control_untouched(self):
		self.assertEqual(frappe.db.get_value("Deal Cost Sheet", self.control.name, ["*"], as_dict=True), self.control_row)

	def _before_values_manifest(self, result):
		return json.loads(result["before_values_json"])

	# --- 1. the gate --------------------------------------------------------------------
	def test_gate_off_and_wrong_checksum_never_write_and_flag_is_cleared(self):
		m = self._both()
		before = {n: _vals("Deal Cost Sheet", n) for n in (self.lead_dcs.name, self.cust_dcs.name)}

		s = self._run(pb.MODE_APPLY, m, gate=False)["summary"]
		self.assertEqual(s["outcome"], "refused")
		self.assertIn("gate off", s["refusal"])
		self.assertEqual((s["written"], s["eligible"]), (0, 2))

		s = self._run(pb.MODE_APPLY, m, sha="0" * 64)["summary"]  # flag on, wrong token
		self.assertEqual(s["outcome"], "refused")
		self.assertIn("sha256", s["refusal"])
		self.assertEqual(s["written"], 0)
		self.assertFalse(frappe.conf.get(pb.CONF_FLAG))  # cleared even though the run was refused
		self.assertTrue(s["flag_cleared"])

		r = self._run(pb.MODE_DRY_RUN, m, gate=False)
		self.assertEqual(r["summary"]["outcome"], "dry run")
		self.assertEqual(r["summary"]["written"], 0)
		self.assertIsNone(r["before_values_json"])
		self.assertEqual(len(_rows(r)), 2)

		for n, v in before.items():
			self.assertEqual(_vals("Deal Cost Sheet", n), v)
		self._assert_control_untouched()

	def test_flag_is_cleared_even_when_the_run_raises(self):
		m = self._both()
		with patch.object(pb, "_write", side_effect=frappe.ValidationError("ZZTEST simulated write failure")):
			with self.assertRaises(frappe.ValidationError):
				self._run(pb.MODE_APPLY, m)
		self.assertFalse(frappe.conf.get(pb.CONF_FLAG))
		self.assertIsNone(_vals("Deal Cost Sheet", self.lead_dcs.name)["party_type"])

	# --- 2/3/4. apply writes only the approved records, exports before values, second run is a no-op ---
	def test_apply_writes_only_manifest_records_exports_before_values_and_is_idempotent(self):
		m = self._both()
		legacy = {n: _vals("Deal Cost Sheet", n) for n in (self.lead_dcs.name, self.cust_dcs.name)}
		modified = {n: frappe.db.get_value("Deal Cost Sheet", n, "modified") for n in legacy}

		r = self._run(pb.MODE_APPLY, m)
		s = r["summary"]
		self.assertEqual((s["outcome"], s["written"], s["rejected"]), ("applied", 2, 0))
		self.assertFalse(frappe.conf.get(pb.CONF_FLAG))

		lead_vals = _vals("Deal Cost Sheet", self.lead_dcs.name)
		self.assertEqual((lead_vals["party_type"], lead_vals["party"], lead_vals["organisation_name"], lead_vals["customer"]),
			("Lead", self.lead_dcs.party, self.lead_dcs.organisation_name, None))
		cust_vals = _vals("Deal Cost Sheet", self.cust_dcs.name)
		self.assertEqual((cust_vals["party_type"], cust_vals["party"], cust_vals["customer"]),
			("Customer", self.cust_dcs.party, self.cust_dcs.party))
		for n in legacy:
			self.assertEqual(frappe.db.get_value("Deal Cost Sheet", n, "modified"), modified[n])
		self._assert_control_untouched()

		export = self._before_values_manifest(r)
		self.assertEqual(export["schema"], pb.SCHEMA_BEFORE_VALUES)
		self.assertEqual(export["manifest_sha256"], s["manifest_sha256"])
		self.assertEqual({x["name"]: x["before"] for x in export["records"]}, legacy)
		self.assertEqual(sorted(export["records"][0]["written_fields"]), ["customer", "organisation_name", "party", "party_type"])

		again = self._run(pb.MODE_APPLY, m)["summary"]
		self.assertEqual(again["written"], 0)
		self.assertEqual(again["by_status"], {pb.ALREADY_APPLIED: 2})
		self.assertEqual(_vals("Deal Cost Sheet", self.lead_dcs.name), lead_vals)

	# --- 5. drift is rejected, never adjusted ---------------------------------------------
	def test_before_value_drift_is_rejected(self):
		m = self._both()
		frappe.db.set_value("Deal Cost Sheet", self.lead_dcs.name, "customer", "ZZTEST edited since assessment", update_modified=False)
		rows = _rows(self._run(pb.MODE_APPLY, m))
		self.assertEqual(rows[self.lead_dcs.name]["status"], pb.REJECTED_BEFORE)
		self.assertIsNone(_vals("Deal Cost Sheet", self.lead_dcs.name)["party_type"])
		self.assertEqual(rows[self.cust_dcs.name]["status"], pb.APPLIED)  # the unaffected entry still applies

	def test_opportunity_party_or_link_drift_is_rejected(self):
		m = self._both()
		other_customer = make_customer("DRIFT" + frappe.generate_hash(length=4))
		frappe.db.set_value("Opportunity", self.lead_dcs.opportunity,
			{"opportunity_from": "Customer", "party_name": other_customer}, update_modified=False)
		frappe.db.set_value("Deal Cost Sheet", self.cust_dcs.name, "custom_quotation", "SAL-QTN-ZZTEST-DRIFT", update_modified=False)
		s = self._run(pb.MODE_APPLY, m)["summary"]
		self.assertEqual(s["written"], 0)
		self.assertEqual(s["by_status"], {pb.REJECTED_SOURCE: 2})
		for n in (self.lead_dcs.name, self.cust_dcs.name):
			self.assertIsNone(_vals("Deal Cost Sheet", n)["party_type"])

	def test_missing_record_and_tampered_after_values_are_rejected(self):
		tampered = _entry("Deal Cost Sheet", self.lead_dcs.name)
		tampered["after"]["party"] = self.control.party  # not what the live data proposes
		m = _manifest(tampered, {**_entry("Deal Cost Sheet", self.cust_dcs.name), "name": "DCS-ZZTEST-DOES-NOT-EXIST-001"})
		s = self._run(pb.MODE_APPLY, m)["summary"]
		self.assertEqual(s["written"], 0)
		self.assertEqual(s["by_status"], {pb.REJECTED_PROPOSAL: 1, pb.REJECTED_MISSING: 1})
		self.assertIsNone(_vals("Deal Cost Sheet", self.lead_dcs.name)["party_type"])

	def test_change_between_evaluation_and_locked_write_is_rejected(self):
		"""A concurrent edit landing after the first evaluation is caught by the locked
		re-evaluation immediately before the write; nothing is overwritten."""
		m = self._both()
		real_evaluate = pb.evaluate
		target = self.lead_dcs.name

		def racing_evaluate(entry, lock=False):
			if lock and entry["name"] == target:
				# the "other user" edits the record between our two reads
				frappe.db.set_value("Deal Cost Sheet", target, "customer", "ZZTEST concurrent edit", update_modified=False)
			return real_evaluate(entry, lock=lock)

		with patch.object(pb, "evaluate", side_effect=racing_evaluate):
			r = self._run(pb.MODE_APPLY, m)
		rows = _rows(r)
		self.assertEqual(rows[target]["status"], pb.REJECTED_RACE)
		self.assertEqual(rows[self.cust_dcs.name]["status"], pb.APPLIED)
		live = _vals("Deal Cost Sheet", target)
		self.assertEqual(live["customer"], "ZZTEST concurrent edit")  # the concurrent edit survived
		self.assertIsNone(live["party_type"])                          # and nothing of ours was written
		self.assertEqual(r["summary"]["written"], 1)

	# --- 6. populated party is preserved unless explicitly approved --------------------------
	def test_populated_party_is_preserved_unless_explicitly_approved(self):
		populated = make_dcs(party_type="Lead", suffix="AP" + frappe.generate_hash(length=5))
		customer = make_customer("POP" + frappe.generate_hash(length=4))
		frappe.db.set_value("Opportunity", populated.opportunity,
			{"opportunity_from": "Customer", "party_name": customer}, update_modified=False)
		was = _vals("Deal Cost Sheet", populated.name)
		self.assertEqual(was["party_type"], "Lead")

		s = self._run(pb.MODE_APPLY, _manifest(_entry("Deal Cost Sheet", populated.name)))["summary"]
		self.assertEqual(s["by_status"], {pb.REJECTED_POPULATED: 1})
		self.assertEqual(_vals("Deal Cost Sheet", populated.name), was)

		s = self._run(pb.MODE_APPLY, _manifest(_entry("Deal Cost Sheet", populated.name, allow_overwrite_populated=True)))["summary"]
		self.assertEqual(s["by_status"], {pb.APPLIED: 1})
		now = _vals("Deal Cost Sheet", populated.name)
		self.assertEqual((now["party_type"], now["party"], now["customer"]), ("Customer", customer, customer))

	# --- 7. Won, Customer-sourced sheet: Customer kept, D3 satisfied -------------------------
	def test_won_customer_sourced_sheet_keeps_customer_and_satisfies_d3(self):
		frappe.db.set_value("Deal Cost Sheet", self.cust_dcs.name, "custom_deal_status", "Won", update_modified=False)
		entry = _entry("Deal Cost Sheet", self.cust_dcs.name)
		self.assertEqual((entry["before"]["customer"], entry["after"]["customer"]), (self.cust_dcs.party, self.cust_dcs.party))
		self.assertEqual(sorted(k for k in PF if entry["before"][k] != entry["after"][k]), ["organisation_name", "party", "party_type"])

		self.assertEqual(self._run(pb.MODE_APPLY, _manifest(entry))["summary"]["written"], 1)
		doc = frappe.get_doc("Deal Cost Sheet", self.cust_dcs.name)
		self.assertEqual(doc.custom_deal_status, "Won")
		self.assertEqual((doc.party_type, doc.party, doc.customer), ("Customer", self.cust_dcs.party, self.cust_dcs.party))
		require_customer(doc, "ZZTEST D3 check")  # must not raise
		doc.flags.ignore_links = True
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual((doc.party_type, doc.party, doc.customer), ("Customer", self.cust_dcs.party, self.cust_dcs.party))

	# --- 8. normal save works after the fill ------------------------------------------------
	def test_normal_save_works_after_fill_and_keeps_filled_values(self):
		self._run(pb.MODE_APPLY, _manifest(_entry("Deal Cost Sheet", self.lead_dcs.name)))
		doc = frappe.get_doc("Deal Cost Sheet", self.lead_dcs.name)  # submitted sheet
		doc.deal_owner = "Administrator"
		doc.flags.ignore_links = True
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertEqual((doc.party_type, doc.party, doc.customer), ("Lead", self.lead_dcs.party, None))
		self.assertEqual(doc.organisation_name, self.lead_dcs.organisation_name)

	# --- 3. restore ----------------------------------------------------------------------
	def test_restore_returns_written_records_to_their_before_values(self):
		m = self._both()
		legacy = {n: _vals("Deal Cost Sheet", n) for n in (self.lead_dcs.name, self.cust_dcs.name)}
		export = self._before_values_manifest(self._run(pb.MODE_APPLY, m))

		s = self._run(pb.MODE_RESTORE, export, gate=False)["summary"]
		self.assertIn("gate off", s["refusal"])
		self.assertEqual(s["written"], 0)

		s = self._run(pb.MODE_RESTORE, export)["summary"]
		self.assertEqual((s["outcome"], s["written"]), ("restored", 2))
		for n, v in legacy.items():
			self.assertEqual(_vals("Deal Cost Sheet", n), v)
		self.assertFalse(frappe.conf.get(pb.CONF_FLAG))

		s = self._run(pb.MODE_RESTORE, export)["summary"]
		self.assertEqual((s["written"], s["by_status"]), (0, {pb.ALREADY_APPLIED: 2}))
		self._assert_control_untouched()

	# --- 9. the DocType path: private manifest File -> Party Backfill Run -> attached exports -----
	def test_party_backfill_run_document_drives_the_whole_cycle(self):
		m = self._both()
		raw = json.dumps(m, sort_keys=True, ensure_ascii=False).encode("utf-8")
		sha = hashlib.sha256(raw).hexdigest()
		mf = frappe.get_doc({"doctype": "File", "file_name": "zztest-party-backfill-manifest.json", "is_private": 1, "content": raw})
		mf.insert(ignore_permissions=True)
		self.assertTrue(mf.file_url.startswith("/private/files/"))
		legacy = {n: _vals("Deal Cost Sheet", n) for n in (self.lead_dcs.name, self.cust_dcs.name)}

		dry = frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_DRY_RUN, "manifest": mf.file_url}).insert()
		self.assertEqual((dry.outcome, dry.eligible, dry.written), ("dry run", 2, 0))
		self.assertTrue(dry.evaluation_file and frappe.db.exists("File", {"file_url": dry.evaluation_file, "is_private": 1}))
		self.assertFalse(dry.before_values_file)

		# Apply without the token is refused by validation; with the token but flag off it is refused by the gate
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_APPLY, "manifest": mf.file_url}).insert()
		refused = frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_APPLY, "manifest": mf.file_url, "manifest_sha256": sha}).insert()
		self.assertEqual((refused.outcome, refused.written), ("refused", 0))
		self.assertEqual(_vals("Deal Cost Sheet", self.lead_dcs.name), legacy[self.lead_dcs.name])

		frappe.conf[pb.CONF_FLAG] = 1
		applied = frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_APPLY, "manifest": mf.file_url, "manifest_sha256": sha}).insert()
		self.assertEqual((applied.outcome, applied.written, applied.rejected, applied.flag_cleared), ("applied", 2, 0, 1))
		self.assertFalse(frappe.conf.get(pb.CONF_FLAG))
		self.assertTrue(applied.before_values_file.startswith("/private/files/"))
		self.assertEqual(_vals("Deal Cost Sheet", self.lead_dcs.name)["party_type"], "Lead")
		self._assert_control_untouched()

		# a run is immutable
		applied.mode = pb.MODE_DRY_RUN
		with self.assertRaises(frappe.ValidationError):
			applied.save()

		# Restore from the attached before-values export, with its own token
		bv = frappe.get_doc("File", {"file_url": applied.before_values_file}).get_content()
		bv_sha = hashlib.sha256(bv.encode("utf-8") if isinstance(bv, str) else bytes(bv)).hexdigest()
		frappe.conf[pb.CONF_FLAG] = 1
		restored = frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_RESTORE, "manifest": applied.before_values_file, "manifest_sha256": bv_sha}).insert()
		self.assertEqual((restored.outcome, restored.written), ("restored", 2))
		for n, v in legacy.items():
			self.assertEqual(_vals("Deal Cost Sheet", n), v)
		self.assertFalse(frappe.conf.get(pb.CONF_FLAG))

	# --- 10. armed attempts that fail before evaluation still disarm the site ------------------
	def _flag_absent_everywhere(self):
		self.assertFalse(frappe.conf.get(pb.CONF_FLAG))
		with open(frappe.get_site_path("site_config.json")) as f:
			self.assertNotIn(pb.CONF_FLAG, json.load(f))

	def _private_file(self, name, content):
		f = frappe.get_doc({"doctype": "File", "file_name": name, "is_private": 1, "content": content})
		f.insert(ignore_permissions=True)
		return f.file_url

	def test_invalid_manifests_write_nothing_and_leave_the_flag_absent(self):
		good = self._both()
		dup = _manifest(_entry("Deal Cost Sheet", self.lead_dcs.name), _entry("Deal Cost Sheet", self.lead_dcs.name))
		h = frappe.generate_hash(length=5)
		cases = {
			"missing private file": "/private/files/zztest-missing-" + h + ".json",
			"public (not private) path": "/files/zztest-public-" + h + ".json",
			"malformed JSON": self._private_file("zztest-malformed-" + h + ".json", b"{not json"),
			"wrong schema": self._private_file("zztest-schema-" + h + ".json", json.dumps({"schema": "zztest/other/1", "entries": good["entries"]}).encode()),
			"duplicate entries": self._private_file("zztest-dup-" + h + ".json", json.dumps(dup).encode()),
		}
		before = {n: _vals("Deal Cost Sheet", n) for n in (self.lead_dcs.name, self.cust_dcs.name)}
		runs_before = frappe.db.count("Party Backfill Run")
		for label, url in cases.items():
			with self.subTest(label):
				frappe.conf[pb.CONF_FLAG] = 1
				with self.assertRaises(frappe.ValidationError):
					frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_APPLY, "manifest": url, "manifest_sha256": "0" * 64}).insert()
				self._flag_absent_everywhere()
				for n, v in before.items():
					self.assertEqual(_vals("Deal Cost Sheet", n), v)
		self.assertEqual(frappe.db.count("Party Backfill Run"), runs_before)
		self._assert_control_untouched()

	def test_missing_sha_token_on_apply_writes_nothing_and_leaves_the_flag_absent(self):
		m = self._both()
		url = self._private_file("zztest-manifest-" + frappe.generate_hash(length=5) + ".json", json.dumps(m, sort_keys=True).encode())
		before = {n: _vals("Deal Cost Sheet", n) for n in (self.lead_dcs.name, self.cust_dcs.name)}
		# controller: the token is mandatory for Apply -> validation error, flag still removed
		frappe.conf[pb.CONF_FLAG] = 1
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_APPLY, "manifest": url}).insert()
		self._flag_absent_everywhere()
		# module: a missing token is a refusal, never a write
		frappe.conf[pb.CONF_FLAG] = 1
		s = pb.execute(pb.MODE_APPLY, url, None)["summary"]
		self.assertEqual((s["outcome"], s["written"]), ("refused", 0))
		self.assertIn("sha256", s["refusal"])
		self._flag_absent_everywhere()
		for n, v in before.items():
			self.assertEqual(_vals("Deal Cost Sheet", n), v)

	# --- 11. a flag that cannot be removed fails the run -----------------------------------------
	def test_flag_removal_failure_fails_the_run_instead_of_completing(self):
		m = self._both()
		url = self._private_file("zztest-manifest-" + frappe.generate_hash(length=5) + ".json", json.dumps(m, sort_keys=True).encode())
		sha = pb.load_manifest(url)[1]
		runs_before = frappe.db.count("Party Backfill Run")
		with patch("frappe.installer.update_site_config", side_effect=OSError("ZZTEST site config not writable")):
			frappe.conf[pb.CONF_FLAG] = 1
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_APPLY, "manifest": url, "manifest_sha256": sha}).insert()
		with patch.object(pb, "_flag_still_set", return_value=True):
			frappe.conf[pb.CONF_FLAG] = 1
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": "Party Backfill Run", "mode": pb.MODE_APPLY, "manifest": url, "manifest_sha256": sha}).insert()
		self.assertEqual(frappe.db.count("Party Backfill Run"), runs_before)  # no run completed
		self.assertFalse(frappe.conf.get(pb.CONF_FLAG))
