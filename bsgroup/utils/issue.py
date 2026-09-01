import frappe


@frappe.whitelist()
def update_resolution(issue_name, resolution_details):
	if not frappe.db.exists("Issue", issue_name):
		frappe.throw(f"Issue {issue_name} does not exist")

	frappe.db.set_value("Issue", issue_name, "resolution_details", resolution_details)
	return frappe.db.get_value("Issue", issue_name, "resolution_details")
