import frappe


@frappe.whitelist()
def get_org_chart():
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=[
			"name",
			"employee_name",
			"designation",
			"department",
			"reports_to",
			"company_email",
			"cell_number",
			"date_of_joining",
		],
	)
	return {"data": employees}
