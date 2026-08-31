# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class ServiceReport(Document):
	def validate(self):
		if self.source == "HD Ticket":
			if not self.ticket:
				frappe.throw(_("Ticket is mandatory when Source is HD Ticket"))
			self.ppm_management = None
			self.ppm_visit_date = None
		elif self.source == "PPM Visit":
			if not self.ppm_management:
				frappe.throw(_("PPM Contract is mandatory when Source is PPM Visit"))
			if not self.ppm_visit_date:
				frappe.throw(_("Scheduled Visit Date is mandatory when Source is PPM Visit"))
			self.ticket = None
			self.get_matching_visit_row()

	def get_matching_visit_row(self):
		ppm = frappe.get_doc("PPM Management", self.ppm_management)
		for row in ppm.ppm_schedule:
			if getdate(row.visit_date) == getdate(self.ppm_visit_date):
				return row
		frappe.throw(
			_("No Scheduled visit dated {0} was found in PPM Contract {1}").format(
				self.ppm_visit_date, self.ppm_management
			)
		)

	def on_submit(self):
		if self.source == "PPM Visit":
			self.mark_ppm_visit_completed()

	def mark_ppm_visit_completed(self):
		ppm = frappe.get_doc("PPM Management", self.ppm_management)
		row = None
		for r in ppm.ppm_schedule:
			if getdate(r.visit_date) == getdate(self.ppm_visit_date):
				row = r
				break

		if not row:
			frappe.throw(
				_("No Scheduled visit dated {0} was found in PPM Contract {1}").format(
					self.ppm_visit_date, self.ppm_management
				)
			)

		row.status = "Completed"
		row.completed_on = nowdate()
		row.service_report = self.name

		ppm.last_completed_on = nowdate()
		if all(r.status == "Completed" for r in ppm.ppm_schedule):
			ppm.status = "Completed"

		ppm.save(ignore_permissions=True)
