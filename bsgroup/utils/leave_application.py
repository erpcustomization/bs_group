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

	from bsgroup.dashboard_leave import validate_self_service
	validate_self_service(doc)
	from bsgroup.time_off_policy import validate as validate_policy
	validate_policy(doc)
	if doc.get('custom_time_off_category') == 'Emergency Leave':
		if doc.is_new() and not doc.flags.get('time_off_request'):
			frappe.throw('Please apply for Emergency Leave through Time Off on your dashboard so the paid/unpaid split is calculated.')
		if not (doc.get('custom_emergency_contact_name') or '').strip() or not (doc.get('custom_emergency_contact_phone') or '').strip():
			frappe.throw('Emergency contact name and phone number are required.')
	if doc.leave_type == 'Sick Leave':
		if (doc.total_leave_days or 0) > 1 and not doc.get('custom_medical_certificate'):
			frappe.throw('A medical certificate is required for sick leave exceeding one day.')
		return
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
