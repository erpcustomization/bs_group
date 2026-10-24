"""Isolated unit checks of the customer-output guards, with a stub ``frappe`` (no site, no rendering).

These prove the decision logic only. Real rendering (print view, wkhtmltopdf/Chrome PDF,
Print Designer, email queue) is covered by ``test_quote_alignment`` on a staging site.

Run anywhere: python3 bsgroup/dcs/test_quote_output_unit.py
"""
import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Flags(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class Thrown(Exception):
	pass


def _stub_frappe():
	if "frappe" in sys.modules and getattr(sys.modules["frappe"], "__stub__", False) is False:
		return None  # a real Frappe is present: these isolated checks are not meaningful there
	frappe = types.ModuleType("frappe")
	frappe.__stub__ = True
	frappe.flags = Flags()
	frappe.form_dict = Flags()
	frappe.hooks = {}
	frappe.attrs = {}
	frappe.messages = []
	frappe.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
	frappe.get_hooks = lambda name: list(frappe.hooks.get(name, []))
	frappe.get_attr = lambda path: frappe.attrs[path]
	frappe.msgprint = lambda *a, **k: frappe.messages.append(a)

	def throw(msg, *a, **k):
		raise Thrown(msg)

	frappe.throw = throw
	frappe.db = types.SimpleNamespace(exists=lambda *a, **k: True, get_value=lambda *a, **k: frappe.beta.get(a[1], 0))
	frappe.beta = {}
	frappe.get_meta = lambda dt: types.SimpleNamespace(default_print_format=None)
	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda v: int(float(v or 0))
	utils.flt = lambda v, p=None: float(v or 0)
	utils.strip_html_tags = lambda v: v
	utils.escape_html = lambda v: str(v).replace("<", "&lt;").replace(">", "&gt;")
	frappe.utils = utils
	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")
	document.Document = type("Document", (), {"round_floats_in": lambda self, doc, fieldnames=None: None})
	for name, module in (("frappe", frappe), ("frappe.utils", utils), ("frappe.model", model),
			("frappe.model.document", document)):
		sys.modules[name] = module
	return frappe


frappe = _stub_frappe()
if frappe is not None:
	sys.path.insert(0, str(ROOT))
	from bsgroup.dcs import quote_alignment as qa


class Doc:
	def __init__(self, docstatus=0, dcs="DCS-1", items=None, **values):
		self.doctype = "Quotation"
		self.docstatus = docstatus
		self.flags = Flags()
		self.values = {"custom_deal_cost_sheet": dcs, "items": items or [], **values}

	def get(self, key, default=None):
		return self.values.get(key, default)

	def __getattr__(self, key):  # Frappe documents expose fields as attributes too
		values = self.__dict__.get("values", {})
		if key in values:
			return values[key]
		raise AttributeError(key)


class Row(dict):
	def get(self, key, default=None):
		return dict.get(self, key, default)

	def __getattr__(self, key):
		return self.get(key)


SELF = "bsgroup.dcs.quote_alignment.pdf_body_html"


@unittest.skipIf(frappe is None, "real Frappe present; run the staging integration suite instead")
class OutputGuards(unittest.TestCase):
	def setUp(self):
		frappe.flags.clear()
		frappe.form_dict.clear()
		frappe.beta.clear()
		frappe.messages.clear()
		self.rendered = []
		frappe.attrs = {
			"frappe.utils.pdf.pdf_body_html": lambda **k: self.rendered.append("frappe") or "<p>frappe</p>",
			"print_designer.pdf.pdf_body_html": lambda **k: self.rendered.append("pd") or "<p>offer</p>",
		}
		frappe.hooks = {"pdf_body_html": ["frappe.utils.pdf.pdf_body_html", "print_designer.pdf.pdf_body_html", SELF]}

	def doc(self, problems, **values):
		d = Doc(**values)
		d.flags.dcs_issue_problems = problems
		return d

	def test_delegates_to_the_previous_renderer_and_marks_unapproved(self):
		html = qa.pdf_body_html(template="t", args={"doc": self.doc(["Repriced"])}, print_format=None)
		self.assertEqual(self.rendered, ["pd"], "Print Designer stays the renderer")
		self.assertTrue(html.startswith(qa.MARK))
		self.assertIn("<p>offer</p>", html)

	def test_issuable_and_non_dcs_output_is_unchanged(self):
		self.assertEqual(qa.pdf_body_html(template="t", args={"doc": self.doc([])}), "<p>offer</p>")
		self.assertEqual(qa.pdf_body_html(template="t", args={"doc": self.doc(["x"], dcs=None)}), "<p>offer</p>")

	def test_attachment_and_system_paths_are_refused(self):
		frappe.flags.ignore_print_permissions = True  # set by frappe.attach_print
		with self.assertRaises(Thrown):
			qa.pdf_body_html(template="t", args={"doc": self.doc(["Repriced"])})
		self.assertEqual(self.rendered, [])

	def test_submitted_superseded_is_marked_too(self):
		html = qa.pdf_body_html(template="t", args={"doc": self.doc(["superseded"], docstatus=1)})
		self.assertTrue(html.startswith(qa.MARK))

	def test_confidential_template_is_refused_even_when_issuable(self):
		fmt = Row(name="Custom Q", html="{{ doc.items[0].custom_cost_rate }}")
		with self.assertRaisesRegex(Thrown, "custom_cost_rate"):
			qa.pdf_body_html(template="t", args={"doc": self.doc([])}, print_format=fmt)
		for text in ("{{ frappe.db.get_value('Deal Cost Sheet', doc.custom_deal_cost_sheet, 'total_cost') }}",
				"{{ doc.custom_gp }}", '{"fieldname": "gp_percent"}'):
			with self.assertRaises(Thrown):
				qa.assert_confidential_template(Row(name="X", html=text))
		qa.assert_confidential_template(Row(name="CSS only", html=".a{margin:0;margin-top:2mm}"))

	def test_before_print_refuses_when_another_renderer_runs_last(self):
		frappe.hooks["pdf_body_html"] = [SELF, "print_designer.pdf.pdf_body_html"]
		original = qa.output_problems
		qa.output_problems = lambda doc: ["Repriced"]
		try:
			with self.assertRaises(Thrown):
				qa.before_print(Doc())
			frappe.hooks["pdf_body_html"] = ["print_designer.pdf.pdf_body_html", SELF]
			d = Doc()
			qa.before_print(d)
			self.assertEqual(d.flags.dcs_issue_block, "Repriced")
		finally:
			qa.output_problems = original

	def test_beta_formats_are_denied_only_when_unapproved(self):
		frappe.beta["Quotation Modern"] = 1
		frappe.form_dict.format = "Quotation Modern"
		self.assertFalse(qa.has_print_permission(self.doc(["Repriced"]), "print"))
		self.assertTrue(qa.has_print_permission(self.doc([]), "print"))
		self.assertTrue(qa.has_print_permission(self.doc(["Repriced"]), "read"))
		frappe.form_dict.format = "Enterprise Quotation format 2"
		self.assertTrue(qa.has_print_permission(self.doc(["Repriced"]), "print"), "markable formats print with the mark")
		frappe.form_dict.clear()
		self.assertTrue(qa.has_print_permission(self.doc(["Repriced"]), "print"), "Standard is markable")

	def test_email_is_refused_before_any_communication(self):
		original_get_doc = getattr(frappe, "get_doc", None)
		docs = {"Q-BAD": self.doc(["Repriced"]), "Q-OK": self.doc([])}
		frappe.get_doc = lambda dt, name: docs[name]
		try:
			with self.assertRaises(Thrown):
				qa.guard_email("Quotation", "Q-BAD", print_format="Standard", send_email=1)
			with self.assertRaisesRegex(Thrown, "client HTML"):
				qa.guard_email("Quotation", "Q-OK", print_html="<p>forged</p>", send_email=1)
			qa.guard_email("Quotation", "Q-OK", print_format="Standard", send_email=1)
			qa.guard_email("Quotation", "Q-BAD", send_email=1)  # no print attached: an ordinary email
		finally:
			frappe.get_doc = original_get_doc

	def test_legacy_evidence_is_server_owned(self):
		unmapped = [Row(custom_dcs_source_rows=None)]
		self.assertTrue(qa.legacy_evidence(Doc(docstatus=1, items=unmapped, custom_dcs_legacy_basis="migration")))
		self.assertFalse(qa.legacy_evidence(Doc(docstatus=1, items=unmapped)), "an empty mapping is not evidence")
		self.assertFalse(qa.legacy_evidence(Doc(docstatus=0, items=unmapped, custom_dcs_legacy_basis="forged")))
		submitting = Doc(docstatus=1, items=unmapped, custom_dcs_legacy_basis="forged")
		submitting._action = "submit"
		self.assertFalse(qa.legacy_evidence(submitting))
		self.assertFalse(qa.legacy_evidence(Doc(docstatus=1, items=[Row(custom_dcs_source_rows="L1")],
			custom_dcs_legacy_basis="migration")))


if __name__ == "__main__":
	unittest.main()
