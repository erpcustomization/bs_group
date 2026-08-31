__version__ = "0.0.1"

# Patch frappe.model.document.Document.round_floats_in to accept do_not_round_fields
# Required for ERPNext 16.21.1 compatibility with Frappe 16.10.10
def _patch_round_floats_in():
	import frappe
	from frappe.model.document import Document

	original = Document.round_floats_in

	def patched_round_floats_in(self, doc, fieldnames=None, do_not_round_fields=None):
		if do_not_round_fields and not fieldnames:
			import frappe as f
			all_fieldnames = [
				df.fieldname
				for df in doc.meta.get("fields", {"fieldtype": ["in", ["Currency", "Float", "Percent"]]})
			]
			fieldnames = [fn for fn in all_fieldnames if fn not in do_not_round_fields]
		return original(self, doc, fieldnames=fieldnames)

	Document.round_floats_in = patched_round_floats_in

_patch_round_floats_in()
