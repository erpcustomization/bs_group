from frappe import _


def get_dashboard_for_employee(data):
	data["transactions"].append(
		{"label": _("Holiday"), "items": ["Holiday List Assignment"]}
	)
	data["non_standard_fieldnames"].update({"Holiday List Assignment": "assigned_to"})
	return data
