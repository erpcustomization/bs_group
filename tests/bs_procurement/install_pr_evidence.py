"""Install manual-PR evidence fields and existing controls on the test site."""
import frappe
frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect(); frappe.set_user("Administrator")
try:
    from bsgroup.procurement_setup import execute
    execute()
    assert frappe.get_meta("Material Request").has_field("custom_bsp_request_evidence")
    frappe.db.commit()
    frappe.clear_cache()
    print("Installed manual PR supporting documents on rel1-test.local")
finally:
    frappe.destroy()
