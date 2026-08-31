import re
import frappe
from frappe.utils import getdate

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	summary = get_summary(data)

	return columns, data, None, None, summary


def get_columns():
	return [
		{"label": "Opportunity", "fieldname": "name", "fieldtype": "Link", "options": "Opportunity", "width": 180},
		{"label": "Account", "fieldname": "account", "fieldtype": "Data", "width": 180},
		{"label": "Scope", "fieldname": "scope", "fieldtype": "Data", "width": 150},
		{"label": "Order Value", "fieldname": "order_value", "fieldtype": "Currency", "width": 120},
		{"label": "Margin", "fieldname": "margin", "fieldtype": "Currency", "width": 120},
		{"label": "Month", "fieldname": "month", "fieldtype": "Data", "width": 100},
		{"label": "Year", "fieldname": "year", "fieldtype": "Int", "width": 80},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
		{"label": "Action Plan", "fieldname": "action_plan", "fieldtype": "Small Text", "width": 180},
	]


def get_data(filters):
	conditions = ""

	if filters.get("from_date"):
		conditions += " AND transaction_date >= %(from_date)s"
	if filters.get("to_date"):
		conditions += " AND transaction_date <= %(to_date)s"
	if filters.get("account"):
		conditions += " AND custom_contact_person_name = %(account)s"
	if filters.get("scope"):
		conditions += " AND opportunity_type = %(scope)s"
	if filters.get("status"):
		conditions += " AND sales_stage = %(status)s"

	company = frappe.defaults.get_user_default("company")
	if company:
		conditions += " AND company = %(company)s"
		if not filters:
			filters = {}
		filters = dict(filters)
		filters["company"] = company

	data = frappe.db.sql(f"""
		SELECT
			name,
			custom_contact_person_name AS account,
			opportunity_type AS scope,
			opportunity_amount AS order_value,
			custom_margin AS margin,
			MONTHNAME(transaction_date) AS month,
			YEAR(transaction_date) AS year,
			sales_stage AS status,
			custom_next_action AS action_plan
		FROM `tabOpportunity`
		WHERE docstatus < 2
		{conditions}
		ORDER BY transaction_date DESC
	""", filters, as_dict=True)

	for row in data:
		status = row.get("status")

		if status == "Won":
			row["status"] = f'<span style="color:green; font-weight:bold;">{status}</span>'
		
		elif status in ["Proposal", "Committed"]:
			row["status"] = f'<span style="color:orange; font-weight:bold;">{status}</span>'
		
		elif status == "Lost":
			row["status"] = f'<span style="color:red; font-weight:bold;">{status}</span>'
		
		else:
			row["status"] = status
   
	return data


def get_summary(data):
	total_value = sum(d.get("order_value") or 0 for d in data)
	total_margin = sum(d.get("margin") or 0 for d in data)

	return [
		{"label": "Total Order Value", "value": total_value, "indicator": "Green"},
		{"label": "Total Margin", "value": total_margin, "indicator": "Blue"},
		{"label": "Total Records", "value": len(data), "indicator": "Orange"},
	]