# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

VISIBILITY_SCOPES = ("All Employees", "Department Specific")
CONFIDENTIALITY_LEVELS = ("Public", "Internal", "Confidential", "Restricted")
# Combinations that are not allowed together (visibility_scope, confidentiality).
INVALID_CLASSIFICATION_COMBOS = {
	("All Employees", "Restricted"),
}
SCOPE_DEPARTMENT_SPECIFIC = "Department Specific"
CONF_CONFIDENTIAL = "Confidential"

APPROVAL_STATUSES = ("Draft", "Under Review", "Pending Approval", "Approved", "Rejected")
LIFECYCLE_STATUSES = ("Active", "Superseded", "Archived", "Expired")
APPROVAL_APPROVED = "Approved"
LIFE_ACTIVE = "Active"
LIFE_SUPERSEDED = "Superseded"


class OrganizationDocument(Document):
	def validate(self):
		self._validate_classification()
		self._validate_department_scope()
		self._validate_explicit_access()
		self._validate_lifecycle()
		self._validate_superseding()
		self._validate_attachments_private()

	def on_update(self):
		self._sync_superseded_target()

	# ------------------------------------------------------------------ #
	# Classification: visibility x confidentiality truth table.
	# Invalid combinations must fail closed at save time.
	# ------------------------------------------------------------------ #
	def _validate_classification(self):
		if self.visibility_scope not in VISIBILITY_SCOPES:
			frappe.throw(
				_("Invalid Visibility Scope: {0}").format(self.visibility_scope),
				title=_("Invalid Classification"),
			)
		if self.confidentiality not in CONFIDENTIALITY_LEVELS:
			frappe.throw(
				_("Invalid Confidentiality: {0}").format(self.confidentiality),
				title=_("Invalid Classification"),
			)
		combo = (self.visibility_scope, self.confidentiality)
		if combo in INVALID_CLASSIFICATION_COMBOS:
			frappe.throw(
				_(
					"The combination Visibility '{0}' + Confidentiality '{1}' "
					"is not permitted."
				).format(self.visibility_scope, self.confidentiality),
				title=_("Invalid Classification"),
			)

	def _validate_department_scope(self):
		if self.visibility_scope == SCOPE_DEPARTMENT_SPECIFIC and not self.applicable_department:
			frappe.throw(
				_("Applicable Department is required for Department Specific documents."),
				title=_("Department Required"),
			)

	def _validate_explicit_access(self):
		"""Confidential documents must carry at least one explicit allowance."""
		if self.confidentiality == CONF_CONFIDENTIAL:
			has_roles = bool(self.get("allowed_roles"))
			has_users = bool(self.get("allowed_users"))
			if not (has_roles or has_users):
				frappe.throw(
					_(
						"Confidential documents require at least one Allowed Role "
						"or Allowed User."
					),
					title=_("Explicit Access Required"),
				)

	# ------------------------------------------------------------------ #
	# Lifecycle consistency.
	# ------------------------------------------------------------------ #
	def _validate_lifecycle(self):
		if self.approval_status not in APPROVAL_STATUSES:
			frappe.throw(
				_("Invalid Approval Status: {0}").format(self.approval_status),
				title=_("Invalid Lifecycle"),
			)
		if self.lifecycle_status not in LIFECYCLE_STATUSES:
			frappe.throw(
				_("Invalid Lifecycle Status: {0}").format(self.lifecycle_status),
				title=_("Invalid Lifecycle"),
			)

		if self.expiry_date and self.effective_date and self.expiry_date < self.effective_date:
			frappe.throw(
				_("Expiry Date cannot be earlier than Effective Date."),
				title=_("Invalid Dates"),
			)

	# ------------------------------------------------------------------ #
	# Superseding integrity.
	# ------------------------------------------------------------------ #
	def _validate_superseding(self):
		if not self.supersedes:
			return
		if self.supersedes == self.name:
			frappe.throw(
				_("A document cannot supersede itself."),
				title=_("Invalid Supersede"),
			)
		if not frappe.db.exists("Organization Document", self.supersedes):
			frappe.throw(
				_("Superseded document {0} does not exist.").format(self.supersedes),
				title=_("Invalid Supersede"),
			)

	def _sync_superseded_target(self):
		"""Mark the superseded document as Superseded and back-link it.

		Uses db_set with update_modified=False to avoid a recursive full save.
		"""
		if not self.supersedes:
			return
		target = frappe.get_doc("Organization Document", self.supersedes)
		changed = False
		if target.superseded_by != self.name:
			target.db_set("superseded_by", self.name, update_modified=False)
			changed = True
		if target.lifecycle_status == LIFE_ACTIVE:
			target.db_set("lifecycle_status", LIFE_SUPERSEDED, update_modified=False)
			changed = True
		if changed:
			frappe.msgprint(
				_("Document {0} has been marked as Superseded.").format(self.supersedes),
				indicator="orange",
				alert=True,
			)

	# ------------------------------------------------------------------ #
	# Attachment privacy: canonical File records must be private.
	# ------------------------------------------------------------------ #
	def _validate_attachments_private(self):
		for row in self.get("supporting_attachments") or []:
			if not row.file:
				continue
			file_name = frappe.db.get_value(
				"File",
				{
					"file_url": row.file,
					"attached_to_doctype": self.doctype,
					"attached_to_name": self.name,
				},
				"name",
			)
			if not file_name:
				# File not yet linked (new doc) — the after_insert link runs later.
				continue
			is_private = frappe.db.get_value("File", file_name, "is_private")
			if not is_private:
				frappe.throw(
					_(
						"Attachment '{0}' must be a private file. Public attachments "
						"are not allowed on organization documents."
					).format(row.attachment_title or row.file),
					title=_("Attachment Must Be Private"),
				)
			if not row.file_type:
				row.file_type = (row.file.rsplit(".", 1)[-1] or "").upper()
