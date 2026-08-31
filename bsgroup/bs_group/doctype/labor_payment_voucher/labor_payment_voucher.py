# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval import (
	block_delete_and_amend_unless_system_manager,
	get_consumed_cost,
	validate_lpre_is_approved,
)


class LaborPaymentVoucher(Document):
	def validate(self):
		self.validate_items()
		self.calculate_totals()
		self.validate_cost_ceiling()

	def before_insert(self):
		if self.amended_from:
			block_delete_and_amend_unless_system_manager(self, "amend")

	def on_trash(self):
		block_delete_and_amend_unless_system_manager(self, "delete")

	def validate_items(self):
		if not self.items:
			frappe.throw(_("At least one Attendance Line is required"))

		seen_in_this_voucher = set()

		for row in self.items:
			if not row.labor_attendance:
				frappe.throw(_("Row {0}: Labor Attendance is required").format(row.idx))

			attendance = frappe.db.get_value(
				"Labor Attendance",
				row.labor_attendance,
				["docstatus", "labor_preapproval", "project", "ticket"],
				as_dict=True,
			)
			if not attendance:
				frappe.throw(_("Row {0}: Labor Attendance {1} does not exist").format(row.idx, row.labor_attendance))

			if attendance.docstatus != 1:
				frappe.throw(
					_("Row {0}: Labor Attendance {1} is not Submitted").format(row.idx, row.labor_attendance)
				)

			if not attendance.labor_preapproval:
				frappe.throw(
					_("Row {0}: Labor Attendance {1} has no linked Labor Preapproval").format(
						row.idx, row.labor_attendance
					)
				)

			lpre = validate_lpre_is_approved(attendance.labor_preapproval)

			if lpre.source == "Project" and attendance.project != lpre.reference:
				frappe.throw(
					_("Row {0}: Attendance Project does not match its Labor Preapproval {1}").format(
						row.idx, lpre.name
					)
				)
			if lpre.source == "HD Ticket" and attendance.ticket != lpre.reference:
				frappe.throw(
					_("Row {0}: Attendance Ticket does not match its Labor Preapproval {1}").format(
						row.idx, lpre.name
					)
				)

			if row.labor_attendance in seen_in_this_voucher:
				frappe.throw(
					_("Row {0}: Labor Attendance {1} is listed more than once in this voucher").format(
						row.idx, row.labor_attendance
					)
				)
			seen_in_this_voucher.add(row.labor_attendance)

			duplicate = frappe.db.sql(
				"""
				SELECT lpv.name
				FROM `tabLabor Payment Voucher Item` lpvi
				INNER JOIN `tabLabor Payment Voucher` lpv ON lpv.name = lpvi.parent
				WHERE lpvi.labor_attendance = %(attendance)s
				AND lpv.docstatus = 1
				AND lpv.name != %(self_name)s
				LIMIT 1
				""",
				{"attendance": row.labor_attendance, "self_name": self.name or ""},
			)
			if duplicate:
				frappe.throw(
					_("Row {0}: Labor Attendance {1} has already been settled in Labor Payment Voucher {2}").format(
						row.idx, row.labor_attendance, duplicate[0][0]
					)
				)

			# Server-authoritative amount; never trust a client/API-supplied value.
			row.amount = frappe.utils.flt(row.rate)

	def calculate_totals(self):
		gross_amount = sum(frappe.utils.flt(row.amount) for row in self.items)
		self.gross_amount = gross_amount
		self.net_payable = gross_amount - frappe.utils.flt(self.deductions)

	def validate_cost_ceiling(self):
		"""LPRE approved cost is a hard ceiling. Sum new amounts per LPRE and check
		against that LPRE's remaining budget (already-consumed cost across all other
		submitted vouchers is excluded here so amending this same voucher doesn't
		double count itself)."""
		new_amount_by_lpre = {}
		for row in self.items:
			lpre_name = frappe.db.get_value("Labor Attendance", row.labor_attendance, "labor_preapproval")
			new_amount_by_lpre.setdefault(lpre_name, 0)
			new_amount_by_lpre[lpre_name] += frappe.utils.flt(row.amount)

		for lpre_name, new_amount in new_amount_by_lpre.items():
			lpre = frappe.get_doc("Labor Preapproval", lpre_name)
			already_consumed = get_consumed_cost(lpre_name, exclude_voucher=self.name)
			total_after = already_consumed + new_amount

			if total_after > frappe.utils.flt(lpre.total_labor_cost):
				frappe.throw(
					_(
						"Labor Preapproval {0} cost ceiling exceeded. Approved: {1}, Already Paid: {2}, "
						"This Voucher: {3}, Total: {4}"
					).format(
						lpre.name,
						lpre.total_labor_cost,
						already_consumed,
						new_amount,
						total_after,
					)
				)
