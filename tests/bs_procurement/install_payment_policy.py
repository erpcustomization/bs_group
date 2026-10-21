"""Apply the authorised purchasing/payment policy on the test site only."""
import frappe
frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
try:
    assert frappe.local.site == "rel1-test.local"
    from bsgroup.procurement_setup import execute
    from bsgroup.procurement_payments import SUPPLIER_EXCEPTIONS
    execute()
    for field in SUPPLIER_EXCEPTIONS:
        assert not frappe.db.count("Supplier", {field: 1})
        assert frappe.get_meta("Supplier").get_field(field).read_only
    assert frappe.get_meta("Purchase Invoice").has_field("custom_bsp_approved_by")
    frappe.db.commit()
    frappe.clear_cache()
    print("Installed supplier payment policy on rel1-test.local.")
finally:
    frappe.destroy()
