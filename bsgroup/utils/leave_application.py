import frappe
from frappe import _


def validate_medical_certificate(doc, method=None):
	"""Require Custom Medical Certificate on Leave Application once the leave
	type and duration cross the threshold configured in BS Group Settings.

	Configuration (BS Group Settings, single doctype):
	  - select_leave_type: the Leave Type this rule applies to.
	  - attachment_required_after_days: the certificate becomes mandatory once
	    total_leave_days exceeds this number.
	"""

	settings = frappe.get_cached_doc("BS Group Settings")
	configured_leave_type = settings.get("select_leave_type")
	threshold_days = settings.get("attachment_required_after_days")

	if not configured_leave_type or not threshold_days:
		return

	if doc.leave_type != configured_leave_type:
		return

	if (doc.total_leave_days or 0) <= threshold_days:
		return

	if not doc.custom_medical_certificate:
		frappe.throw(
			_(
				"Medical Certificate is mandatory for {0} leave exceeding {1} day(s)."
			).format(configured_leave_type, threshold_days)
		)
