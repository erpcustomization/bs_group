# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval import (
	block_delete_and_amend_unless_system_manager,
	get_remaining_person_days,
	get_scheduled_labor_count,
	validate_lpre_is_approved,
)


class LaborAttendance(Document):
	def validate(self):
		self.compute_total_hours()
		self.validate_labor_preapproval_authorization()

	def before_insert(self):
		if self.amended_from:
			block_delete_and_amend_unless_system_manager(self, "amend")

	def on_trash(self):
		block_delete_and_amend_unless_system_manager(self, "delete")

	def compute_total_hours(self):
		if self.check_in_time and self.check_out_time:
			diff = frappe.utils.time_diff_in_seconds(self.check_out_time, self.check_in_time)
			if diff and diff < 0:
				frappe.throw(_("Check-out time cannot be before check-in time"))
			self.total_hours = round(diff / 3600.0, 2) if diff else 0
		else:
			self.total_hours = 0

	def validate_labor_preapproval_authorization(self):
		"""Authoritative, hard-blocking control. Outsourced day-labor Attendance is only
		valid against an Approved Labor Preapproval with matching source/route,
		matching Role/Skill, and available person-day capacity. Any failure raises -
		it never merely records a soft status and permits the save to continue.
		"""
		if not self.labor_preapproval:
			self.validation_status = "Not Approved"
			frappe.throw(_("Labor Attendance requires a linked Labor Preapproval"))

		lpre = validate_lpre_is_approved(self.labor_preapproval)

		if lpre.source == "Project":
			if not self.project or self.project != lpre.reference:
				frappe.throw(
					_("Attendance Project must match the Project on Labor Preapproval {0}").format(lpre.name)
				)
			if not self.task or self.task != lpre.task:
				frappe.throw(
					_("Attendance Task must match the Task on Labor Preapproval {0}").format(lpre.name)
				)
		elif lpre.source == "HD Ticket":
			if not self.ticket or self.ticket != lpre.reference:
				frappe.throw(
					_("Attendance Ticket must match the HD Ticket on Labor Preapproval {0}").format(lpre.name)
				)

		self.validate_role_skill(lpre)
		self.validate_person_day_capacity(lpre)

		self.validation_status = "OK"

	def validate_role_skill(self, lpre):
		labour_type = frappe.db.get_value("Labour Name", self.labour, "labour_type") if self.labour else None
		approved_skills = {row.role__skill for row in lpre.labor_line_items}

		if not labour_type or labour_type not in approved_skills:
			frappe.throw(
				_("Labour {0}'s Role/Skill ({1}) is not part of the approved Labor Preapproval {2}").format(
					self.labour, labour_type or _("Not Set"), lpre.name
				)
			)

	def validate_person_day_capacity(self, lpre):
		remaining = get_remaining_person_days(lpre, exclude_attendance=self.name)
		if remaining <= 0:
			scheduled = get_scheduled_labor_count(lpre)
			cap_label = (
				_("Scheduled: {0}").format(scheduled)
				if scheduled
				else _("Approved: {0}").format(lpre.approved_person_days)
			)
			frappe.throw(
				_("Person-day capacity for Labor Preapproval {0} has been exhausted ({1})").format(
					lpre.name, cap_label
				)
			)


@frappe.whitelist()
def bulk_create(labor_preapproval, labourers, check_in_time, check_out_time=None,
	project=None, task=None, ticket=None, site_location=None, submit=1):
	"""Create one Labor Attendance per selected Labourer against the same
	Labor Preapproval, sharing the same check-in/out time and site details -
	so a supervisor doesn't have to fill the form once per person.

	Each row is created and (optionally) submitted independently, so one
	labourer failing capacity/skill validation doesn't block the rest; the
	caller gets back which rows succeeded and which failed and why.
	"""
	if isinstance(labourers, str):
		labourers = frappe.parse_json(labourers)

	if not labourers:
		frappe.throw(_("Select at least one Labourer"))

	lpre = frappe.get_doc("Labor Preapproval", labor_preapproval)

	created, errors = [], []
	for labour in labourers:
		try:
			doc = frappe.new_doc("Labor Attendance")
			doc.labour = labour
			doc.labor_preapproval = lpre.name
			doc.project = project or (lpre.reference if lpre.source == "Project" else None)
			doc.task = task or lpre.task
			doc.ticket = ticket or (lpre.reference if lpre.source == "HD Ticket" else None)
			doc.check_in_time = check_in_time
			doc.check_out_time = check_out_time
			doc.site_location = site_location
			doc.insert()
			if frappe.utils.cint(submit):
				doc.submit()
			created.append(doc.name)
		except Exception as e:
			errors.append(f"{labour}: {e}")

	return {"created": created, "errors": errors}
