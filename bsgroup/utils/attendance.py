import frappe
from frappe import _
from frappe.utils import getdate


def create_comp_off_on_attendance_submit(doc, method=None):
	"""On Attendance submit, if the date is a holiday/weekly off and employee worked,
	auto-create a Compensatory Leave Request."""
	if doc.status not in ("Present", "Work From Home", "Half Day"):
		return

	attendance_date = getdate(doc.attendance_date)
	company = doc.company

	holiday_list = _get_holiday_list(doc.employee, attendance_date, company)
	if not holiday_list:
		return

	if not frappe.db.exists("Holiday", {"parent": holiday_list, "holiday_date": attendance_date}):
		return

	comp_leave_type = frappe.db.get_value("Leave Type", {"is_compensatory": 1}, "name")
	if not comp_leave_type:
		frappe.log_error(
			"No Leave Type with 'Is Compensatory' enabled found.",
			"Comp-Off Auto Creation",
		)
		return

	if frappe.db.exists(
		"Compensatory Leave Request",
		{
			"employee": doc.employee,
			"work_from_date": attendance_date,
			"work_end_date": attendance_date,
			"docstatus": ["!=", 2],
		},
	):
		return

	clr = frappe.new_doc("Compensatory Leave Request")
	clr.employee = doc.employee
	clr.leave_type = comp_leave_type
	clr.work_from_date = attendance_date
	clr.work_end_date = attendance_date
	clr.reason = _("Worked on holiday/weekly off on {0}").format(attendance_date)
	clr.company = company

	try:
		clr.insert(ignore_permissions=True)
		frappe.msgprint(
			_("Compensatory Leave Request created for {0} for {1}").format(
				doc.employee_name or doc.employee, attendance_date
			),
			indicator="green",
			alert=True,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Comp-Off Auto Creation Failed")


def _get_holiday_list(employee, date, company):
	"""Returns the applicable holiday list for an employee on a given date.
	Checks: 1) Holiday List Assignment doctype, 2) Employee field, 3) Company default."""
	# Check Holiday List Assignment (date-range based assignments)
	assignment = frappe.db.sql(
		"""
		SELECT holiday_list FROM `tabHoliday List Assignment`
		WHERE assigned_to = %s
		  AND from_date <= %s
		  AND docstatus = 1
		ORDER BY from_date DESC
		LIMIT 1
		""",
		(employee, date),
		as_dict=True,
	)
	if assignment and assignment[0].holiday_list:
		return assignment[0].holiday_list

	# Fallback to Employee field
	holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
	if holiday_list:
		return holiday_list

	# Fallback to Company default
	return frappe.db.get_value("Company", company, "default_holiday_list")
