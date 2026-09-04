# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from bsgroup.utils.project_cost_baseline import (
	carry_forward_revision,
	mark_amended_from_superseded,
	reset_approval_fields_for_draft,
	set_baseline_amount_from_dcs,
	set_remaining_amount,
	supersede_previous_baselines,
	validate_dcs_belongs_to_project,
	validate_dcs_is_submitted,
	validate_no_active_baseline_for_project,
)


class ProjectCostBaseline(Document):
	def before_insert(self):
		carry_forward_revision(self)

	def validate(self):
		reset_approval_fields_for_draft(self)
		validate_dcs_belongs_to_project(self)
		validate_dcs_is_submitted(self)
		set_baseline_amount_from_dcs(self)
		set_remaining_amount(self)

	def before_submit(self):
		validate_no_active_baseline_for_project(self)
		self.status = "Approved"
		self.approved_by = frappe.session.user
		self.approved_on = frappe.utils.now_datetime()

	def on_submit(self):
		supersede_previous_baselines(self)
		mark_amended_from_superseded(self)

	def on_cancel(self):
		self.db_set("status", "Cancelled", update_modified=False)
