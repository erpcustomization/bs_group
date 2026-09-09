# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

MONTHS_MAP = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}


class PPMManagement(Document):
	def validate(self):
		self.compute_next_ppm_date()
		self.derive_status()

	def compute_next_ppm_date(self):
		if not (self.contract_start_date and self.frequency):
			return

		base_date = (
			frappe.utils.getdate(self.last_completed_on)
			if self.last_completed_on
			else frappe.utils.getdate(self.contract_start_date)
		)
		months = MONTHS_MAP.get(self.frequency, 1)
		self.next_ppm_date = frappe.utils.add_months(base_date, months)

	def derive_status(self):
		if self.status == "Completed" or not self.next_ppm_date:
			return

		today_date = frappe.utils.getdate(frappe.utils.nowdate())
		next_date = frappe.utils.getdate(self.next_ppm_date)

		if next_date < today_date:
			self.status = "Overdue"
		elif next_date <= frappe.utils.add_days(today_date, 5):
			self.status = "Upcoming"
		else:
			self.status = "Scheduled"


@frappe.whitelist()
def ppm_calendar_events(start, end, filters=None):
	"""Calendar events source for the PPM Management calendar view -
	one event per PPM Management record whose next_ppm_date falls in range,
	matching the field_map declared in frappe.views.calendar["PPM Management"]."""
	from frappe.desk.calendar import get_events

	return get_events(
		doctype="PPM Management",
		start=start,
		end=end,
		field_map=frappe.as_json({"start": "next_ppm_date", "end": "next_ppm_date"}),
		filters=filters,
		fields=frappe.as_json(["name", "project", "next_ppm_date", "status", "assigned_engineer"]),
	)
