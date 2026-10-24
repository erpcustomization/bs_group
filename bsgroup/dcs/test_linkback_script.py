"""Unit coverage for the hash-checked link-back Server Script migration. Needs no Frappe site.

Run anywhere: python3 bsgroup/dcs/test_linkback_script.py
"""
import importlib.util
import pathlib
import unittest

_spec = importlib.util.spec_from_file_location("linkback_script", pathlib.Path(__file__).with_name("linkback_script.py"))
lb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lb)


class LinkbackScriptMigration(unittest.TestCase):
	def test_stored_original_is_the_production_version(self):
		# sha256 and length read from rel1-test.local (copy of production) on 2026-10-23.
		text = lb.original()
		self.assertEqual(lb.sha256(text), "39be1445d34c3756ee8598164b3e4768b71a88b265fb98999e07516bbc13840f")
		self.assertEqual(len(text.encode()), 4001)

	def test_only_the_two_status_writes_are_removed(self):
		before, after = lb.original(), lb.convert(lb.original())
		self.assertNotIn("'custom_deal_status', 'Quoted'", after)
		self.assertEqual(after.count(lb.OWNER_NOTE), 2)
		removed = [l for l in before.splitlines() if l not in after.splitlines()]
		self.assertEqual(len(removed), 4)
		self.assertTrue(all("custom_deal_status" in l or l.strip().startswith("if cur not in") for l in removed), removed)
		for kept in ("'custom_quotation', doc.name", "'custom_presales_request', pr", "'Ready for Quotation'",
				"'status', 'Completed'", "dcs_presales_sync", "'custom_deal_cost_sheet', dcs"):
			self.assertIn(kept, after)
		compile(after, "linkback", "exec")

	def test_plan_is_idempotent_and_refuses_customised_versions(self):
		self.assertEqual(lb.plan(lb.original()), "convert")
		self.assertEqual(lb.plan(lb.convert(lb.original())), "already")
		self.assertEqual(lb.plan(lb.original() + "\n# local change\n"), "customised")
		self.assertEqual(lb.plan(None), "absent")
		with self.assertRaises(ValueError):
			lb.convert(lb.original().replace("Won", "WON"))


if __name__ == "__main__":
	unittest.main()
