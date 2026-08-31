import frappe
from frappe.utils import nowdate, get_first_day

HR_ROLES = {"HR User", "HR Manager", "System Manager"}
MANAGER_ROLES = {"HR Manager", "Leave Approver", "System Manager"}


def _get_employee(user):
	return frappe.db.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		["name", "employee_name", "department"],
		as_dict=True,
	)


def _is_hr(roles):
	return bool(HR_ROLES & set(roles))


def _get_direct_reports(employee_name, user):
	"""Direct reports via reports_to, plus anyone this user is set as
	Leave Approver for — both are legitimate native ERPNext manager scopes.
	System Manager is an administrative override and sees every active employee."""
	if "System Manager" in frappe.get_roles(user):
		return frappe.get_all(
			"Employee",
			filters={"status": "Active", "name": ["!=", employee_name or ""]},
			fields=["name", "employee_name"],
		)

	reports = {}
	if employee_name:
		for e in frappe.get_all(
			"Employee",
			filters={"reports_to": employee_name, "status": "Active"},
			fields=["name", "employee_name"],
		):
			reports[e.name] = e.employee_name
	for e in frappe.get_all(
		"Employee",
		filters={"leave_approver": user, "status": "Active"},
		fields=["name", "employee_name"],
	):
		reports[e.name] = e.employee_name
	return [{"name": k, "employee_name": v} for k, v in reports.items()]


@frappe.whitelist()
def get_dashboard_context():
	user = frappe.session.user
	roles = frappe.get_roles(user)
	employee = _get_employee(user)
	reports = _get_direct_reports(employee.name if employee else None, user)

	return {
		"employee": employee.name if employee else None,
		"employee_name": employee.employee_name if employee else user,
		"has_employee": bool(employee),
		"is_manager": bool(reports) or bool(MANAGER_ROLES & set(roles)),
		"is_hr": _is_hr(roles),
	}


@frappe.whitelist()
def get_employee_summary():
	employee = _get_employee(frappe.session.user)
	if not employee:
		return {"has_employee": False}

	today = nowdate()
	month_start = get_first_day(today)

	today_attendance = frappe.db.get_value(
		"Employee Checkin",
		{"employee": employee.name, "time": ["between", [f"{today} 00:00:00", f"{today} 23:59:59"]]},
		["log_type", "time"],
		order_by="time asc",
		as_dict=True,
	)

	month_attendance = frappe.get_all(
		"Attendance",
		filters={
			"employee": employee.name,
			"attendance_date": ["between", [month_start, today]],
			"docstatus": ["!=", 2],
		},
		fields=["status"],
	)
	att_counts = {}
	for a in month_attendance:
		att_counts[a.status] = att_counts.get(a.status, 0) + 1

	leave_rows = []
	try:
		from hrms.hr.doctype.leave_application.leave_application import get_leave_details

		details = get_leave_details(employee.name, today)
		for leave_type, d in details.get("leave_allocation", {}).items():
			leave_rows.append({
				"leave_type": leave_type,
				"entitlement": d.get("total_leaves", 0),
				"used": d.get("leaves_taken", 0),
				"pending": d.get("leaves_pending_approval", 0),
				"available": d.get("remaining_leaves", 0),
			})
	except Exception:
		frappe.log_error(title="HR Dashboard: leave balance fetch failed")

	pending_requests = frappe.get_all(
		"Leave Application",
		filters={"employee": employee.name, "status": "Open"},
		fields=["name", "leave_type", "from_date", "to_date", "status"],
		order_by="from_date desc",
		limit_page_length=5,
	)

	return {
		"has_employee": True,
		"employee_name": employee.employee_name,
		"today_status": today_attendance.log_type if today_attendance else None,
		"today_time": today_attendance.time if today_attendance else None,
		"attendance_summary": att_counts,
		"leave_balances": leave_rows,
		"pending_requests": pending_requests,
	}


@frappe.whitelist()
def get_manager_summary():
	user = frappe.session.user
	employee = _get_employee(user)
	reports = _get_direct_reports(employee.name if employee else None, user)
	if not reports:
		return {"has_reports": False}

	report_ids = [r["name"] for r in reports]
	names_by_id = {r["name"]: r["employee_name"] for r in reports}
	today = nowdate()

	pending_leaves = frappe.get_all(
		"Leave Application",
		filters={"employee": ["in", report_ids], "status": "Open"},
		fields=["name", "employee", "leave_type", "from_date", "to_date"],
		order_by="from_date asc",
		limit_page_length=20,
	)
	for r in pending_leaves:
		r["employee_name"] = names_by_id.get(r.employee, r.employee)

	today_attendance = frappe.get_all(
		"Attendance",
		filters={"employee": ["in", report_ids], "attendance_date": today, "docstatus": ["!=", 2]},
		fields=["employee", "status"],
	)
	att_by_emp = {a.employee: a.status for a in today_attendance}

	team_today = []
	present = on_leave = exceptions = 0
	for r in reports:
		status = att_by_emp.get(r["name"], "Not Marked")
		if status == "Present":
			present += 1
		elif status == "On Leave":
			on_leave += 1
		if status == "Not Marked":
			exceptions += 1
		team_today.append({"employee_name": r["employee_name"], "status": status})

	return {
		"has_reports": True,
		"kpis": {
			"present_today": present,
			"on_leave": on_leave,
			"pending_approvals": len(pending_leaves),
			"attendance_exceptions": exceptions,
		},
		"pending_approvals": pending_leaves,
		"team_today": team_today,
	}


@frappe.whitelist()
def get_hr_summary():
	if not _is_hr(frappe.get_roles(frappe.session.user)):
		frappe.throw("Not permitted", frappe.PermissionError)

	# HR is already authorized above; query company-wide regardless of the
	# caller's own User Permission scoping (e.g. a self-scoping Employee
	# permission), which would otherwise silently hide most records from HR.
	active_employees = frappe.get_all(
		"Employee", filters={"status": "Active"}, fields=["name", "employee_name"], ignore_permissions=True
	)
	emp_ids = [e.name for e in active_employees]

	missing_approver = sum(
		1 for e in emp_ids if not frappe.db.get_value("Employee", e, "leave_approver")
	)

	allocated_ids = set(
		frappe.get_all(
			"Leave Allocation",
			filters={"employee": ["in", emp_ids], "docstatus": 1},
			pluck="employee",
			ignore_permissions=True,
		)
	) if emp_ids else set()
	missing_allocation = len([e for e in emp_ids if e not in allocated_ids])

	reconciliation = []
	try:
		from hrms.hr.doctype.leave_application.leave_application import get_leave_details

		today = nowdate()
		for e in active_employees[:50]:
			details = get_leave_details(e.name, today)
			for leave_type, d in details.get("leave_allocation", {}).items():
				pending = d.get("leaves_pending_approval", 0)
				available = d.get("remaining_leaves", 0)
				total = d.get("total_leaves", 0) or 0
				exception = None
				if available < 0:
					exception = f"{abs(available):.1f} days overcommitted"
				elif pending > 0 and total and available <= (0.25 * total):
					exception = "High pending"
				if exception:
					reconciliation.append({
						"employee_name": e.employee_name,
						"leave_type": leave_type,
						"ledger_balance": total - d.get("leaves_taken", 0),
						"pending": pending,
						"available": available,
						"exception": exception,
					})
	except Exception:
		frappe.log_error(title="HR Dashboard: leave reconciliation failed")

	return {
		"kpis": {
			"missing_leave_allocation": missing_allocation,
			"missing_leave_approver": missing_approver,
			"total_active_employees": len(emp_ids),
		},
		"leave_reconciliation": reconciliation[:20],
	}
