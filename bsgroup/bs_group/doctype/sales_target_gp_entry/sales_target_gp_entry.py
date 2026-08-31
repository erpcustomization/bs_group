# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class SalesTargetGPEntry(Document):
	def validate(self):
		self.check_duplicate()
		self.calculate_totals()

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
