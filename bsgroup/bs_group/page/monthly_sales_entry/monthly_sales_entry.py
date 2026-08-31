import frappe


ALL_SALES_PERSONS = "__all__"

MONTHS = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
]


def _get_employee_for_user(user):
	return frappe.db.get_value("Employee", {"user_id": user}, "name")


def _allowed_sales_persons():
	"""Sales persons the current user is allowed to view."""
	user = frappe.session.user
	roles = frappe.get_roles(user)

	if "System Manager" in roles or "Sales Manager" in roles:
		return frappe.get_all(
			"Sales Person", filters={"enabled": 1}, pluck="name", order_by="name asc"
		)

	employee = _get_employee_for_user(user)
	if not employee:
		return []

	return frappe.get_all(
		"Sales Person",
		filters={"enabled": 1, "employee": employee},
		pluck="name",
	)


@frappe.whitelist()
def stgp_allowed_sales_persons():
	return _allowed_sales_persons()


def _check_sales_person_permission(salesperson):
	user = frappe.session.user
	roles = frappe.get_roles(user)
	if "System Manager" in roles or "Sales Manager" in roles:
		return
	employee = _get_employee_for_user(user)
	own_sales_person = (
		frappe.db.get_value("Sales Person", {"employee": employee}, "name") if employee else None
	)
	if not own_sales_person or own_sales_person != salesperson:
		frappe.throw("You do not have permission to view this data.", frappe.PermissionError)


def _empty_months():
	return [
		{
			"month": month,
			"invoiced_sales_revenue": 0.0,
			"invoiced_sales_gp": 0.0,
			"booked_sales_revenue": 0.0,
			"booked_sales_gp": 0.0,
			"invoiced_gp_pct": 0.0,
			"booked_gp_pct": 0.0,
			"comments": None,
			"comments_list": [],
			"status": "Not Entered",
		}
		for month in MONTHS
	]


def _months_from_doc(doc):
	return [
		{
			"month": row.month,
			"invoiced_sales_revenue": row.invoiced_sales_revenue,
			"invoiced_sales_gp": row.invoiced_sales_gp,
			"booked_sales_revenue": row.booked_sales_revenue,
			"booked_sales_gp": row.booked_sales_gp,
			"invoiced_gp_pct": row.invoiced_gp_pct,
			"booked_gp_pct": row.booked_gp_pct,
			"comments": row.comments,
			"comments_list": [{"salesperson": doc.salesperson, "text": row.comments}] if row.comments else [],
			"status": row.status,
		}
		for row in doc.monthly_data
	]


def _totals_from_doc(doc):
	return {
		"total_invoiced_revenue": doc.total_invoiced_revenue,
		"total_invoiced_gp": doc.total_invoiced_gp,
		"total_booked_revenue": doc.total_booked_revenue,
		"total_booked_gp": doc.total_booked_gp,
	}


def _load_single_entry(salesperson, fiscal_year):
	_check_sales_person_permission(salesperson)

	existing_name = frappe.db.get_value(
		"Sales Target GP Entry",
		{"salesperson": salesperson, "fiscal_year": fiscal_year},
		"name",
	)

	if not existing_name:
		return {
			"data_basis": "Sales Data",
			"months": _empty_months(),
			"totals": {
				"total_invoiced_revenue": 0.0,
				"total_invoiced_gp": 0.0,
				"total_booked_revenue": 0.0,
				"total_booked_gp": 0.0,
			},
		}

	doc = frappe.get_doc("Sales Target GP Entry", existing_name)
	return {
		"data_basis": doc.data_basis or "Sales Data",
		"months": _months_from_doc(doc),
		"totals": _totals_from_doc(doc),
	}


def _load_all_entries(fiscal_year):
	"""Aggregate every accessible salesperson's entry for this fiscal year."""
	salespersons = _allowed_sales_persons()

	by_month = {
		month: {
			"month": month,
			"invoiced_sales_revenue": 0.0,
			"invoiced_sales_gp": 0.0,
			"booked_sales_revenue": 0.0,
			"booked_sales_gp": 0.0,
			"comments": [],
			"statuses": set(),
		}
		for month in MONTHS
	}
	totals = {"total_invoiced_revenue": 0.0, "total_invoiced_gp": 0.0, "total_booked_revenue": 0.0, "total_booked_gp": 0.0}

	entry_names = frappe.get_all(
		"Sales Target GP Entry",
		filters={"salesperson": ["in", salespersons or [""]], "fiscal_year": fiscal_year},
		pluck="name",
	)

	for name in entry_names:
		doc = frappe.get_doc("Sales Target GP Entry", name)
		totals["total_invoiced_revenue"] += doc.total_invoiced_revenue or 0
		totals["total_invoiced_gp"] += doc.total_invoiced_gp or 0
		totals["total_booked_revenue"] += doc.total_booked_revenue or 0
		totals["total_booked_gp"] += doc.total_booked_gp or 0

		for row in doc.monthly_data:
			m = by_month.get(row.month)
			if not m:
				continue
			m["invoiced_sales_revenue"] += row.invoiced_sales_revenue or 0
			m["invoiced_sales_gp"] += row.invoiced_sales_gp or 0
			m["booked_sales_revenue"] += row.booked_sales_revenue or 0
			m["booked_sales_gp"] += row.booked_sales_gp or 0
			if row.comments:
				m["comments"].append({"salesperson": doc.salesperson, "text": row.comments})
			m["statuses"].add(row.status or "Not Entered")

	months_out = []
	for month in MONTHS:
		m = by_month[month]
		ir, ig = m["invoiced_sales_revenue"], m["invoiced_sales_gp"]
		br, bg = m["booked_sales_revenue"], m["booked_sales_gp"]
		statuses = m["statuses"] - {"Not Entered"}
		if not statuses:
			status = "Not Entered"
		elif len(statuses) == 1:
			status = next(iter(statuses))
		else:
			status = "Mixed"
		months_out.append({
			"month": month,
			"invoiced_sales_revenue": ir,
			"invoiced_sales_gp": ig,
			"booked_sales_revenue": br,
			"booked_sales_gp": bg,
			"invoiced_gp_pct": (ig / ir * 100) if ir else 0,
			"booked_gp_pct": (bg / br * 100) if br else 0,
			"comments": None,
			"comments_list": m["comments"],
			"status": status,
		})

	return {"data_basis": "Sales Data", "months": months_out, "totals": totals}


@frappe.whitelist()
def stgp_load_entry(salesperson, fiscal_year):
	"""Read-only lookup: show the saved Sales Target GP Entry for this
	Salesperson + Fiscal Year exactly as entered (or the sum across all
	accessible salespersons when "All Salespersons" is selected). Never
	creates or recalculates figures - data entry happens on the doctype itself."""
	if not fiscal_year:
		frappe.throw("Fiscal Year is required")

	if salesperson == ALL_SALES_PERSONS:
		return _load_all_entries(fiscal_year)

	if not salesperson:
		frappe.throw("Salesperson is required")

	return _load_single_entry(salesperson, fiscal_year)
