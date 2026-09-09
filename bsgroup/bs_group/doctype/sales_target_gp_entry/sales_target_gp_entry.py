# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from bsgroup.permissions import get_sales_target_gp_entry_allowed_sales_persons


class SalesTargetGPEntry(Document):
	def validate(self):
		self.check_duplicate()
		self.validate_monthly_data()
		self.calculate_totals()

		if not self.data_basis:
			self.data_basis = "Sales Data"

	def check_duplicate(self):
		duplicate = frappe.db.get_value(
			"Sales Target GP Entry",
			{
				"salesperson": self.salesperson,
				"fiscal_year": self.fiscal_year,
				"name": ["!=", self.name],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				f"An entry for {self.salesperson} / {self.fiscal_year} already exists: {duplicate}"
			)

	def validate_monthly_data(self):
		seen_months = []

		for row in self.monthly_data or []:
			ir = flt(row.invoiced_sales_revenue)
			ig = flt(row.invoiced_sales_gp)
			br = flt(row.booked_sales_revenue)
			bg = flt(row.booked_sales_gp)

			if not row.month:
				frappe.throw("Please select a Month for every row in Monthly Data.")

			if row.month in seen_months:
				frappe.throw(f"Month {row.month} appears more than once. Each month must be unique.")
			seen_months.append(row.month)

			if ig > ir:
				frappe.throw(f"Invoiced Sales GP cannot exceed Invoiced Sales Revenue for {row.month}.")
			if bg > br:
				frappe.throw(f"Booked Sales GP cannot exceed Booked Sales Revenue for {row.month}.")

			if ir < 0 or ig < 0 or br < 0 or bg < 0:
				frappe.throw(f"Values cannot be negative for {row.month}.")

			# Status: derive Not Entered when a row is entirely empty and status not manually set.
			# `row.is_new()` (rather than `not row.status`) because Frappe auto-fills a new Select
			# row to its first option ("Not Entered") before validate() runs, so the field is
			# never actually falsy here - `not row.status` alone would never recompute anything.
			if row.is_new() or not row.status:
				row.status = "Not Entered" if not (ir or ig or br or bg) else "Draft"

	def calculate_totals(self):
		total_invoiced_revenue = total_invoiced_gp = 0.0
		total_booked_revenue = total_booked_gp = 0.0

		for row in self.monthly_data:
			ir = flt(row.invoiced_sales_revenue)
			ig = flt(row.invoiced_sales_gp)
			br = flt(row.booked_sales_revenue)
			bg = flt(row.booked_sales_gp)

			row.invoiced_gp_pct = (ig / ir * 100) if ir else 0
			row.booked_gp_pct = (bg / br * 100) if br else 0

			total_invoiced_revenue += ir
			total_invoiced_gp += ig
			total_booked_revenue += br
			total_booked_gp += bg

		self.total_invoiced_revenue = total_invoiced_revenue
		self.total_invoiced_gp = total_invoiced_gp
		self.total_booked_revenue = total_booked_revenue
		self.total_booked_gp = total_booked_gp


@frappe.whitelist()
def stgp_allowed_sales_persons():
	"""Sales Person names the current user may pick as `salesperson` on
	Sales Target GP Entry, per the Employee reporting hierarchy."""
	allowed = get_sales_target_gp_entry_allowed_sales_persons(frappe.session.user)
	if allowed is None:
		return frappe.get_all("Sales Person", pluck="name")
	return allowed
