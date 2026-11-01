"""Supplier quotation evidence is required only at DCS submission."""
import frappe
from frappe import _
from frappe.permissions import has_permission


def validate_supplier_quotations(doc):
    rows = doc.get("supplier_quotations") or []
    if not rows:
        frappe.throw(_("Attach a Supplier / Vendor Quotation under Costing before submitting this Deal Cost Sheet."))
    for index, row in enumerate(rows, 1):
        url = row.get("quotation")
        if not url:
            frappe.throw(_("Supplier / Vendor Quotation row {0}: attach the quotation before submission.").format(index))
        files = frappe.get_all("File", filters={"file_url": url, "is_folder": 0}, pluck="name")
        if not files or not any(has_permission("File", "read", doc=name, print_logs=False) for name in files):
            frappe.throw(_("Supplier / Vendor Quotation row {0}: upload a valid quotation file that you can access.").format(index))