"""Read the one known legacy module when reconciling the Oman release."""
import frappe


@frappe.whitelist()
def opportunity_source():
    if frappe.session.user != 'Administrator':
        frappe.throw('Administrator only', frappe.PermissionError)
    from pathlib import Path
    return Path(frappe.get_app_path('bsgroup', 'utils', 'opportunity.py')).read_text()
