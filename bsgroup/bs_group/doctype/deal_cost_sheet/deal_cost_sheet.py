# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
import re
from frappe.model.document import Document


class DealCostSheet(Document):
	def autoname(self):
		if self.customer:
			customer = re.sub(r'[^a-zA-Z0-9\s]', '', self.customer)
			customer = re.sub(r'\s+', '-', customer.strip())

			self.name = frappe.model.naming.make_autoname(f"DCS-{customer}-.###")

	def before_save(self):
		calculate_deal_financials(self)

	def before_submit(self):
		validate_deal_cost(self)

	def validate(self):
		if not self.project:
			frappe.throw("Project is mandatory on the Deal Cost Sheet before it can be used as a Project Cost Baseline source.")

		if self.presales_request:
			site_visit_required = frappe.db.get_value(
				"Presales Request", self.presales_request, "site_visit_required"
			)
			if site_visit_required and not self.site_visit:
				frappe.throw(
					"Site Visit is mandatory: the linked Presales Request requires a completed site visit."
				)


@frappe.whitelist()
def make_quotation(source_name):
	source = frappe.get_doc("Deal Cost Sheet", source_name)

	opp = frappe.db.get_value(
		"Opportunity",
		source.opportunity,
		["opportunity_from", "party_name", "custom_contact_person_name", "custom_organization_name"],
		as_dict=True,
	) or {}

	company_currency = frappe.db.get_value("Company", source.company, "default_currency") if source.company else None

	quotation = frappe.new_doc("Quotation")
	quotation.ignore_pricing_rule = 1
	quotation.opportunity = source.opportunity
	quotation.company = source.company
	if company_currency:
		quotation.currency = company_currency

	if source.company:
		vat_template = frappe.db.get_value(
			"Sales Taxes and Charges Template",
			{"company": source.company, "name": ["like", "%UAE VAT 5%%"]},
			"name"
		)
		if vat_template:
			quotation.taxes_and_charges = vat_template
			tax_rows = frappe.get_all(
				"Sales Taxes and Charges",
				filters={"parent": vat_template},
				fields=["charge_type", "account_head", "description", "rate", "included_in_print_rate"],
				order_by="idx"
			)
			for tax in tax_rows:
				quotation.append("taxes", tax)
	quotation.quotation_to = "Customer" if opp.get("opportunity_from") == "Customer" else "Lead"
	quotation.party_name = opp.get("party_name")
	quotation.custom_contact_person_name = opp.get("custom_contact_person_name") or opp.get("party_name")
	quotation.custom_organization_name = opp.get("custom_organization_name") or ""

	quotation.custom_subject = source.subject
	quotation.custom_customer_notes = source.customer_notes
	quotation.custom_scope_overview = source.scope_overview


	for row in source.items or []:
		if row.item_code:
			item = frappe.db.get_value(
				"Item",
				row.item_code,
				["item_name", "stock_uom", "description"],
				as_dict=True
			) or {}

			if row.description:
				description = row.description
			elif row.exclude_item_name_and_brand:
				description = row.item_name or item.get("item_name") or row.item_code
			else:
				parts = [p for p in [row.brand, row.item_code, row.item_name or item.get("item_name")] if p]
				description = " - ".join(parts) if parts else row.item_code

			selling_rate = frappe.utils.flt(row.selling_rate)
			qty = frappe.utils.flt(row.qty)
			quotation.append("items", {
				"item_code": row.item_code,
				"item_name": row.item_name or item.get("item_name") or row.item_code,
				"brand": row.brand,
				"custom_exclude_item_name_and_brand": row.exclude_item_name_and_brand,
				"uom": item.get("stock_uom"),
				"stock_uom": item.get("stock_uom"),
				"description": description,
				"custom_header": row.header,
				"qty": qty,
				"custom_cost_rate": frappe.utils.flt(row.cost_rate),
				"custom_selling_rate": selling_rate,
				"price_list_rate": selling_rate,
				"discount_percentage": 0,
				"rate": selling_rate,
				"amount": qty * selling_rate,
			})

	additional_charges_total = sum(frappe.utils.flt(c.amount) for c in source.addtional_charges or [])
	if additional_charges_total:
		dcs_addtional_item = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
		if not dcs_addtional_item:
			frappe.throw("Please configure 'DCS Addtional Item' in BS Group Settings to transfer Additional Charges.")

		item = frappe.db.get_value(
			"Item",
			dcs_addtional_item,
			["item_name", "stock_uom"],
			as_dict=True
		) or {}

		quotation.append("items", {
			"item_code": dcs_addtional_item,
			"item_name": item.get("item_name") or dcs_addtional_item,
			"uom": item.get("stock_uom"),
			"stock_uom": item.get("stock_uom"),
			"description": item.get("item_name") or dcs_addtional_item,
			"qty": 1,
			"price_list_rate": additional_charges_total,
			"discount_percentage": 0,
			"rate": additional_charges_total,
			"amount": additional_charges_total,
		})

	quotation.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.commit()
	return quotation.name


def validate_deal_cost(doc):
	if not doc.opportunity:
		frappe.throw("Opportunity is mandatory before submit.")

	if not doc.items:
		frappe.throw("At least one item is required before submit.")

	for d in doc.items:
		if not d.item_code:
			frappe.throw("Item Code is mandatory in all rows.")

	# 	if frappe.utils.flt(d.selling_rate) <= 0:
	# 		frappe.throw(f"Selling Rate is required before submit for item {d.item_code}.")

	# if frappe.utils.flt(doc.total_selling) <= 0:
	# 	frappe.throw("Total Selling must be greater than zero.")

	# if frappe.utils.flt(doc.margin_value) < 0:
	# 	frappe.throw("Margin cannot be negative.")


def calculate_deal_financials(doc):
	products_cost_total = 0
	products_selling_total = 0
	services_cost_total = 0
	services_selling_total = 0

	for d in doc.items or []:
		qty = frappe.utils.flt(d.qty)
		cost_rate = frappe.utils.flt(d.cost_rate)
		selling_rate = frappe.utils.flt(d.selling_rate)

		d.cost_amount = qty * cost_rate
		d.selling_amount = qty * selling_rate
		d.gp_value = d.selling_amount - d.cost_amount
		d.gp_percent = (d.gp_value / d.selling_amount) * 100 if d.selling_amount else 0

		is_stock_item = frappe.db.get_value("Item", d.item_code, "is_stock_item") if d.item_code else 1

		if not is_stock_item:
			d.item_category = "Professional Services"
			services_cost_total += d.cost_amount
			services_selling_total += d.selling_amount
		else:
			d.item_category = "Products"
			products_cost_total += d.cost_amount
			products_selling_total += d.selling_amount

	total_resource_cost = 0
	for r in doc.resources or []:
		persons = frappe.utils.flt(r.no_of_persons)
		days = frappe.utils.flt(r.no_of_days)
		hours = frappe.utils.flt(r.hours)
		rate = frappe.utils.flt(r.cost_rate)

		if persons and days:
			r.cost_amount = persons * days * rate
		elif hours:
			r.cost_amount = hours * rate
		else:
			r.cost_amount = 0

		total_resource_cost += r.cost_amount

	additional_charges_total = 0
	for c in doc.addtional_charges or []:
		additional_charges_total += frappe.utils.flt(c.amount)

	doc.products_cost_total = products_cost_total
	doc.products_selling_total = products_selling_total
	doc.services_cost_total = services_cost_total
	doc.services_selling_total = services_selling_total
	doc.total_resource_cost = total_resource_cost

	doc.total_cost = products_cost_total + services_cost_total + additional_charges_total + total_resource_cost
	doc.total_selling = products_selling_total + services_selling_total
	doc.margin_value = doc.total_selling - doc.total_cost
	doc.margin_percent = ((doc.total_selling / doc.total_cost) - 1) * 100 if doc.total_cost else 0


@frappe.whitelist()
def get_site_visit_evidence(site_visit):
	if not site_visit:
		return {}

	doc = frappe.get_doc("Site Visit", site_visit)

	return {
		"status": doc.status,
		"planned_visit_date": doc.planned_visit_date,
		"site_conditions": doc.site_conditions,
		"technical_observations": doc.technical_observations,
		"requirements_identified": doc.requirements_identified,
		"constraints_issues": doc.constraints_issues,
		"findings": doc.findings,
		"recommendations": doc.recommendations,
		"visit_result": doc.visit_result,
		"measurements": [
			{
				"measurement_type": m.measurement_type,
				"value": m.value,
				"unit": m.unit,
				"remarks": m.remarks,
			}
			for m in doc.measurements or []
		],
		"evidence": [
			{
				"evidence_type": e.evidence_type,
				"description": e.description,
				"attachment": e.attachment,
			}
			for e in doc.evidence or []
		],
	}


@frappe.whitelist()
def read_deal_cost_sheet(file_url, docname):
	import csv
	import os
	import openpyxl
	from frappe.utils.file_manager import get_file_path

	if docname.startswith("new-"):
		frappe.throw("Please save the document before importing.")

	doc = frappe.get_doc("Deal Cost Sheet", docname)
	doc.set("items", [])

	file_name = frappe.db.get_value("File", {"file_url": file_url}, "file_name")
	if not file_name:
		frappe.throw(f"File not found for URL: {file_url}")
	file_path = get_file_path(file_name)

	ext = os.path.splitext(file_path)[1].lower()

	if ext not in (".xlsx", ".csv"):
		frappe.throw("Only .xlsx or .csv files are supported")

	def read_rows():
		if ext == ".csv":
			with open(file_path, newline="", encoding="utf-8-sig") as f:
				reader = csv.reader(f)
				for row in reader:
					yield row
		else:
			wb = openpyxl.load_workbook(file_path, data_only=True)
			sheet = wb.active
			for row in sheet.iter_rows(values_only=True):
				yield list(row)

	column_map = {}

	for row in read_rows():
		if not row:
			continue

		row = [str(c).strip() if c is not None else "" for c in row]

		# Detect header row
		if not column_map:
			column_map = {col: idx for idx, col in enumerate(row)}
			continue

		def get_val(col):
			idx = column_map.get(col)
			return row[idx] if idx is not None and idx < len(row) else ""

		def to_float(col):
			try:
				return float(get_val(col) or 0)
			except (ValueError, TypeError):
				return 0.0

		def to_int(col):
			try:
				return int(float(get_val(col) or 0))
			except (ValueError, TypeError):
				return 0

		child = doc.append("items", {})

		child.header = get_val("Header (Items)")
		child.item_code = get_val("Item Code (Items)")
		child.item_name = get_val("Item Name (Items)")
		child.brand = get_val("Brand (Items)")
		child.customer_item_name = get_val("Customer Item Name (Items)")
		child.exclude_item_name_and_brand = to_int("Exclude Item Name and Brand (Items)")

		child.qty = to_float("Qty (Items)")
		child.cost_rate = to_float("Cost Rate (Items)")
		child.cost_amount = to_float("Cost Amount (Items)")

		child.item_category = get_val("Item Category (Items)")

		child.selling_rate = to_float("Selling Rate (Items)")
		child.selling_amount = to_float("Selling Amount (Items)")

		child.gp_value = to_float("GP Value (Items)")
		child.gp_percent = to_float("GP % (Items)")

	doc.save(ignore_permissions=True)

	return "Success"