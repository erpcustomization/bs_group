import frappe


def _num(v):
	try:
		return float(v or 0)
	except (TypeError, ValueError):
		return 0.0


def validate_targets(doc, method=None):
	"""Sales Person Target validation (Sales Command Center).

	Validates Target Detail rows on the standard Sales Person.targets table.
	Non-negative for all four target metrics; GP cannot exceed its revenue base
	only when BOTH figures are > 0. Zero/blank custom values are allowed so
	historic rows are never blocked. No core files modified; no ignore_permissions.
	"""
	for row in doc.targets or []:
		fy = row.fiscal_year
		inv_rev = _num(row.target_amount)
		inv_gp = _num(row.custom_invoiced_gp_target)
		bk_rev = _num(row.custom_booked_revenue_target)
		bk_gp = _num(row.custom_booked_gp_target)

		if inv_rev < 0 or inv_gp < 0 or bk_rev < 0 or bk_gp < 0:
			frappe.throw("Target values cannot be negative (Fiscal Year " + str(fy) + ").")

		if inv_gp > 0 and inv_rev > 0 and inv_gp > inv_rev:
			frappe.throw("Invoiced GP Target cannot exceed Invoiced Revenue Target (Fiscal Year " + str(fy) + ").")

		if bk_gp > 0 and bk_rev > 0 and bk_gp > bk_rev:
			frappe.throw("Booked GP Target cannot exceed Booked Revenue Target (Fiscal Year " + str(fy) + ").")
