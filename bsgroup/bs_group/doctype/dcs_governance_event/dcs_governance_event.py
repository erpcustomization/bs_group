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
