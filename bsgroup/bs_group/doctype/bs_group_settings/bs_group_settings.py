# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BSGroupSettings(Document):
	def validate(self):
		if self.dcs_approval_policy == "Mohan" and not frappe.db.get_value("User", "mohan@bitssecureit.com", "enabled"):
			frappe.throw("Enable Mohan's user before selecting him as the DCS approver.")

	def on_update(self):
		before = self.get_doc_before_save()
		if before and before.get("dcs_approval_policy") != self.dcs_approval_policy:
			from bsgroup.dcs.manager_approval import reroute_pending
			reroute_pending()
