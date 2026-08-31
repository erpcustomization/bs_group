import frappe
from frappe.utils import today, add_days


def run():
	"""One-off demo: create a Supplier + Purchase Invoice + partial Payment Entry,
	then render supplier_statement.html to confirm the Account Summary is populated
	(was previously always 0 - see supplier_statement.html for the fix)."""
	frappe.set_user("Administrator")
	company = frappe.db.get_single_value("Global Defaults", "default_company") or frappe.db.get_value(
		"Company", {}, "name"
	)

	supplier_name = "Test SOA Supplier"
	if not frappe.db.exists("Supplier", supplier_name):
		supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": supplier_name,
				"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
				"supplier_type": "Company",
			}
		).insert(ignore_permissions=True)
	else:
		supplier = frappe.get_doc("Supplier", supplier_name)

	if not frappe.db.exists("Purchase Invoice", {"supplier": supplier.name, "docstatus": 1}):
		item_code = frappe.db.get_value("Item", {"is_stock_item": 0}, "name") or frappe.db.get_value(
			"Item", {}, "name"
		)
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"supplier": supplier.name,
				"company": company,
				"posting_date": add_days(today(), -30),
				"items": [{"item_code": item_code, "qty": 1, "rate": 1000}],
			}
		)
		pi.insert(ignore_permissions=True)
		pi.submit()

		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Purchase Invoice", pi.name)
		pe.reference_no = "TEST-REF"
		pe.reference_date = today()
		pe.paid_amount = 600
		pe.received_amount = 600
		for r in pe.references:
			r.allocated_amount = 600
		pe.insert(ignore_permissions=True)
		pe.submit()

	from erpnext.accounts.report.general_ledger.general_ledger import execute as get_gl

	filters = frappe._dict(
		{
			"company": company,
			"party_type": "Supplier",
			"party": [supplier.name],
			"party_name": [supplier.supplier_name],
			"from_date": add_days(today(), -60),
			"to_date": today(),
			"presentation_currency": frappe.get_cached_value("Company", company, "default_currency"),
			"show_opening_entries": 0,
			"include_default_book_entries": 0,
			"group_by": "Group by Voucher (Consolidated)",
		}
	)
	col, res = get_gl(filters)

	html = frappe.render_template(
		"bsgroup/templates/supplier_statement.html",
		{"filters": filters, "data": res},
	)

	print("---- GL rows ----")
	for row in res:
		print(dict(row))

	body = html[html.find("</style>") :]
	start = body.find('<div class="soa-summary">')
	print("---- rendered Account Summary block ----")
	print(body[start : start + 900])
