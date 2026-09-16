import frappe

from bsgroup.permissions import get_user_customers


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Customer", "fieldname": "party", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": "Customer Name", "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 150},
		{"label": "Balance", "fieldname": "balance", "fieldtype": "Currency", "width": 150},
	]


def get_allowed_customers(user=None):
	"""None = unrestricted (System Manager / Sales Manager); [] = no access;
	otherwise the list of Customers permitted for the logged-in Sales Person."""
	if not user:
		user = frappe.session.user

	roles = frappe.get_roles(user)
	if "System Manager" in roles or "Sales Manager" in roles:
		return None

	return get_user_customers(user)


def get_data(filters):
	conditions = ["gle.party_type = 'Customer'", "gle.is_cancelled = 0"]
	values = {}

	if filters.get("company"):
		conditions.append("gle.company = %(company)s")
		values["company"] = filters.get("company")

	allowed_customers = get_allowed_customers()
	if allowed_customers is not None:
		if not allowed_customers:
			return []
		conditions.append("gle.party IN %(allowed_customers)s")
		values["allowed_customers"] = tuple(allowed_customers)

	condition_sql = " AND ".join(conditions)

	return frappe.db.sql(
		f"""
		SELECT
			gle.party AS party,
			cust.customer_name AS customer_name,
			gle.company AS company,
			SUM(gle.debit - gle.credit) AS balance
		FROM `tabGL Entry` gle
		LEFT JOIN `tabCustomer` cust ON cust.name = gle.party
		WHERE {condition_sql}
		GROUP BY gle.party, gle.company
		HAVING balance != 0
		ORDER BY balance DESC
		""",
		values,
		as_dict=True,
	)
