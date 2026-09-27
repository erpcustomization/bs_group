# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import hashlib

import frappe
from frappe import _
from frappe.model.document import Document

from bsgroup.utils import party_backfill as pb


class PartyBackfillRun(Document):
	"""One audited execution of the REL-1 party backfill (see ``bsgroup.utils.party_backfill``).

	The run happens inside the insert transaction: a failure anywhere raises, the insert
	fails and every write of the run rolls back with it. Nothing here is whitelisted; the
	DocType's own permissions (System Manager: create, read) are the only access path,
	from the desk form or from the System Console with ``frappe.get_doc({...}).insert()``.
	A run is immutable once inserted.
	"""

	def validate(self):
		if not self.is_new():
			frappe.throw(_("Party Backfill Run {0} is immutable; insert a new run instead.").format(self.name))

	def _check_input(self):
		# before_insert runs ahead of validate, so the input checks live here
		if self.mode not in pb.MODES:
			frappe.throw(_("Mode must be one of {0}.").format(", ".join(pb.MODES)))
		if self.mode in (pb.MODE_APPLY, pb.MODE_RESTORE) and not (self.manifest_sha256 or "").strip():
			frappe.throw(_("{0} requires the manifest SHA-256 approval token.").format(self.mode))
		if not (self.manifest or "").startswith("/private/files/"):
			frappe.throw(_("The manifest must be a private file on this site (/private/files/...)."))

	def before_insert(self):
		frappe.only_for("System Manager")  # permission check before any configuration mutation
		try:
			self._check_input()
			result = pb.execute(self.mode, self.manifest, self.manifest_sha256, run_id=self.name or None)
		finally:
			# an Apply/Restore attempt that fails input validation must still disarm the site;
			# pb.execute clears the flag itself in every other case (idempotent here)
			if self.mode in (pb.MODE_APPLY, pb.MODE_RESTORE):
				pb.clear_flag()
		summary = result["summary"]
		self.outcome = summary["outcome"]
		self.refusal = summary.get("refusal")
		self.eligible = summary["eligible"]
		self.written = summary["written"]
		self.rejected = summary["rejected"]
		self.flag_cleared = 1 if summary.get("flag_cleared") else 0
		self.summary = frappe.as_json(summary)
		self.flags.pb_result = result

	def after_insert(self):
		result = self.flags.pb_result
		updates = {"evaluation_file": self._attach("evaluation.csv", result["evaluation_csv"])}
		if result.get("before_values_json"):
			updates["before_values_file"] = self._attach("before-values.json", result["before_values_json"])
			updates["before_values_sha256"] = hashlib.sha256(result["before_values_json"].encode("utf-8")).hexdigest()
		self.db_set(updates, update_modified=False)

	def _attach(self, suffix, content):
		f = frappe.get_doc({
			"doctype": "File",
			"file_name": f"{self.name}-{suffix}",
			"attached_to_doctype": self.doctype,
			"attached_to_name": self.name,
			"is_private": 1,
			"content": content,
		})
		f.insert(ignore_permissions=True)
		return f.file_url
