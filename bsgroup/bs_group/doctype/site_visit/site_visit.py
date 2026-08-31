# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class SiteVisit(Document):
	def validate(self):
		if self.status == "Completed":
			if not self.findings:
				frappe.throw(_("Findings is mandatory when Status is Completed"))
			if not self.visit_result:
				frappe.throw(_("Visit Result is mandatory when Status is Completed"))
			if not self.completed_by:
				self.completed_by = frappe.session.user
			if not self.completed_on:
				self.completed_on = now_datetime()
