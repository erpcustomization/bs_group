# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils.nestedset import NestedSet


class OrganizationDocumentCategory(NestedSet):
	nsm_parent_field = "parent_organization_document_category"

	def validate(self):
		self._prevent_self_parent()

	def on_trash(self):
		self._block_delete_if_referenced()
		super().on_trash()

	def _prevent_self_parent(self):
		if self.parent_organization_document_category == self.name:
			frappe.throw(
				_("A category cannot be its own parent."),
				title=_("Invalid Hierarchy"),
			)

	def _block_delete_if_referenced(self):
		referenced = frappe.db.count("Organization Document", {"category": self.name})
		if referenced:
			frappe.throw(
				_(
					"Cannot delete category '{0}': {1} document(s) reference it."
				).format(self.name, referenced),
				title=_("Category In Use"),
			)


def validate_leaf_category(doc, method=None):
	"""doc_events hook on Organization Document: enforce leaf-only categories.

	Registered in hooks.py so the rule lives with the category domain but
	fires on document save.
	"""
	if not doc.category:
		return
	is_group = frappe.db.get_value("Organization Document Category", doc.category, "is_group")
	if is_group:
		frappe.throw(
			_(
				"Category '{0}' is a group. Documents can only be assigned to "
				"leaf categories."
			).format(doc.category),
			title=_("Group Category Not Allowed"),
		)
	disabled = frappe.db.get_value("Organization Document Category", doc.category, "disabled")
	if disabled:
		frappe.throw(
			_("Category '{0}' is disabled.").format(doc.category),
			title=_("Disabled Category"),
		)
