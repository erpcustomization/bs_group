# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

# Explicit transition map: {from_status: {allowed to_status}}. Cancelled is
# reachable from any non-terminal status (a visit can be called off at any
# point), so it is added to every entry below rather than repeated per key.
SITE_VISIT_TRANSITIONS = {
	"Requested": {"Assigned"},
	"Assigned": {"Scheduled"},
	"Scheduled": {"In Progress"},
	"In Progress": {"Completed"},
}
for _allowed in SITE_VISIT_TRANSITIONS.values():
	_allowed.add("Cancelled")
SITE_VISIT_TERMINAL_STATUSES = ("Completed", "Cancelled")


class SiteVisit(Document):
	def validate(self):
		self._reset_amended_completion_fields()
		self._validate_status_transition()

		if self.status == "Completed":
			if not self.findings:
				frappe.throw(_("Findings is mandatory when Status is Completed"))
			if not self.visit_result:
				frappe.throw(_("Visit Result is mandatory when Status is Completed"))
			if not self.completed_by:
				self.completed_by = frappe.session.user
			if not self.completed_on:
				self.completed_on = now_datetime()
			self._validate_completed_on()
		else:
			# Leaving (or never having reached) Completed - a visit that
			# hasn't happened shouldn't carry a completion signature.
			self.completed_by = None
			self.completed_on = None

	def before_submit(self):
		if self.status not in SITE_VISIT_TERMINAL_STATUSES:
			frappe.throw(
				_("Site Visit can only be submitted once its Status is 'Completed' or 'Cancelled'"),
				title=_("Not Ready to Submit"),
			)

	def on_cancel(self):
		self.db_set("status", "Cancelled", update_modified=False)

	def _reset_amended_completion_fields(self):
		"""A fresh amendment (docstatus 0, born from a cancelled Site Visit)
		must not inherit the previous visit's completion signature - no_copy
		on completed_by/completed_on already stops most of this; this is a
		defensive second layer, matching the same fix applied to Project
		Cost Baseline."""
		if self.docstatus == 0 and self.amended_from:
			self.status = "Requested"
			self.completed_by = None
			self.completed_on = None

	def _validate_status_transition(self):
		if self.is_new():
			return

		previous_status = self._get_previous_status()
		if not previous_status or previous_status == self.status:
			return

		if previous_status in SITE_VISIT_TERMINAL_STATUSES:
			frappe.throw(
				_("Status '{0}' is terminal and cannot move to '{1}'").format(previous_status, self.status),
				title=_("Status Locked"),
			)

		allowed = SITE_VISIT_TRANSITIONS.get(previous_status, set())
		if self.status not in allowed:
			frappe.throw(
				_("Cannot move Status from '{0}' to '{1}'").format(previous_status, self.status),
				title=_("Invalid Status Transition"),
			)

	def _get_previous_status(self):
		before_save = self.get_doc_before_save()
		if before_save:
			return before_save.status
		return frappe.db.get_value("Site Visit", self.name, "status")

	def _validate_completed_on(self):
		completed_date = getdate(self.completed_on)
		if completed_date > getdate():
			frappe.throw(_("Completed On cannot be in the future"))
		if self.planned_visit_date and completed_date < getdate(self.planned_visit_date):
			frappe.throw(_("Completed On cannot be earlier than the Planned Visit Date"))
