import frappe
from frappe import _
from frappe.utils import getdate, get_url


def create_holiday_list_assignment(doc, method=None):
	"""Auto-create a Holiday List Assignment for the employee's current holiday list.

	Holiday List Assignment has no explicit "to date" field - its effective
	period is derived from the linked Holiday List's own from_date/to_date.
	We only control the assignment's from_date, which we pin to Jan 1 of the
	current calendar year so the assignment is understood to cover the
	current year.
	"""
	if not doc.holiday_list:
		return

	if frappe.db.exists(
		"Holiday List Assignment",
		{
			"assigned_to": doc.name,
			"applicable_for": "Employee",
			"holiday_list": doc.holiday_list,
			"docstatus": 1,
		},
	):
		return

	current_year = getdate().year
	from_date = getdate(f"{current_year}-01-01")

	holiday_list_start, holiday_list_end = frappe.db.get_value(
		"Holiday List", doc.holiday_list, ["from_date", "to_date"]
	)

	if from_date < holiday_list_start:
		from_date = holiday_list_start

	try:
		hla = frappe.new_doc("Holiday List Assignment")
		hla.applicable_for = "Employee"
		hla.assigned_to = doc.name
		hla.employee_name = doc.employee_name
		hla.holiday_list = doc.holiday_list
		hla.employee_company = doc.company
		hla.from_date = from_date
		hla.insert(ignore_permissions=True)
		hla.submit()
	except Exception:
		frappe.log_error(
			title="Holiday List Assignment auto-creation failed",
			message=frappe.get_traceback(),
		)


@frappe.whitelist()
def send_login_details(employee):
	"""Email the linked user account's login details / reset-password instructions."""
	doc = frappe.get_doc("Employee", employee)
	frappe.has_permission("Employee", doc=doc, throw=True)

	if not doc.user_id:
		frappe.throw(_("This Employee has no linked User account"))

	site_url = get_url()
	company = doc.company or frappe.defaults.get_global_default("company") or ""

	message = f"""
		<p>Hello,</p>
		<p>Your user account has been created successfully.</p>
		<p>Please use the link below to access the site:</p>
		<p><b>Site URL:</b> <a href="{site_url}">{site_url}</a></p>
		<p>If you need to set or reset your password, click <b>&quot;Forgot Password&quot;</b>
		on the login page and follow the instructions to create a new password.</p>
		<p>Regards,<br>{company}</p>
	"""

	frappe.sendmail(
		recipients=[doc.user_id],
		subject=_("Your Account Login Details"),
		message=message,
		now=True,
	)

	return doc.user_id
