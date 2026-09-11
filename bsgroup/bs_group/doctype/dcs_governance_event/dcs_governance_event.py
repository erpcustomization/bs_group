# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DCSGovernanceEvent(Document):
	def before_insert(self):
		# Written only by audit-guard code paths (e.g. DCS Record Authority
		# Guard) via `ev.flags.dcs_audit_write = 1; ev.insert(ignore_permissions=True)`.
		# This is a simple append-only log doctype: no submit, no update.
		pass

	def validate(self):
		# DCS Governance Event - Immutability Guard (D2a).
		# The canonical governed audit trail is append-only. A recorded event is never edited.
		prev = self.get_doc_before_save()

		if prev is not None:
			frappe.throw(
				"DCS Governance Event "
				+ str(self.name)
				+ " is immutable. A recorded governance event is append-only evidence and can never be edited. If an event was recorded in error, record a corrective governed action instead."
			)

	def on_trash(self):
		# DCS Governance Event - Deletion Guard (D2a).
		# Governed audit evidence is never removed.
		frappe.throw(
			"DCS Governance Event "
			+ str(self.name)
			+ " cannot be deleted. The governed audit trail is immutable, append-only evidence. If an event was recorded in error, record a corrective governed action instead."
		)
