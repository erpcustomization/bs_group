"""One-off demo data seeder for the HR Dashboard page (bs_group/page/hr_dashboard).

Run once from bench execute, optionally naming a manager Employee id whose
direct reports already exist (via reports_to). If omitted, the first Active
employee with at least one direct report is used automatically:

	bench --site <site> execute bsgroup.utils.seed_hr_dashboard_demo.run
	bench --site <site> execute bsgroup.utils.seed_hr_dashboard_demo.run --kwargs '{"manager_employee": "0001"}'

Safe to re-run: it skips records that already exist for the same
employee/leave_type/date combination instead of duplicating them.
Company and leave_approver are always derived from each Employee's own
record — nothing is hardcoded to a specific site.
"""
import frappe
from frappe.utils import add_days, nowdate, today

LEAVE_TYPE = "Annual Vacation"


def _ensure_leave_allocation(employee, company, total, from_date, to_date):
	existing = frappe.db.get_value(
		"Leave Allocation",
		{
			"employee": employee,
			"leave_type": LEAVE_TYPE,
			"docstatus": 1,
			"from_date": ["<=", to_date],
			"to_date": [">=", from_date],
		},
	)
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Leave Allocation",
		"employee": employee,
		"leave_type": LEAVE_TYPE,
		"company": company,
		"from_date": from_date,
		"to_date": to_date,
		"new_leaves_allocated": total,
		"total_leaves_allocated": total,
	})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _ensure_leave_application(employee, company, leave_approver, from_date, to_date, status="Open"):
	existing = frappe.db.exists(
		"Leave Application",
		{"employee": employee, "leave_type": LEAVE_TYPE, "from_date": from_date, "to_date": to_date},
	)
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Leave Application",
		"employee": employee,
		"leave_type": LEAVE_TYPE,
		"company": company,
		"from_date": from_date,
		"to_date": to_date,
		"posting_date": nowdate(),
		"status": status,
		"leave_approver": leave_approver,
		"description": "Demo seed record for HR Dashboard",
	})
	doc.insert(ignore_permissions=True)
	if status != "Open":
		doc.submit()
	return doc.name


def _ensure_attendance(employee, company, attendance_date, status):
	existing = frappe.db.exists(
		"Attendance", {"employee": employee, "attendance_date": attendance_date, "docstatus": ["!=", 2]}
	)
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Attendance",
		"employee": employee,
		"attendance_date": attendance_date,
		"status": status,
		"company": company,
	})
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _ensure_checkin(employee, log_type, log_time):
	existing = frappe.db.exists(
		"Employee Checkin", {"employee": employee, "log_type": log_type, "time": log_time}
	)
	if existing:
		return existing
	try:
		doc = frappe.get_doc({
			"doctype": "Employee Checkin",
			"employee": employee,
			"log_type": log_type,
			"time": log_time,
		})
		doc.insert(ignore_permissions=True)
		return doc.name
	except frappe.ValidationError:
		# some sites enforce geofence lat/long on checkins; retry with a placeholder location
		frappe.clear_last_message()
		doc = frappe.get_doc({
			"doctype": "Employee Checkin",
			"employee": employee,
			"log_type": log_type,
			"time": log_time,
			"latitude": 25.2048,
			"longitude": 55.2708,
		})
		doc.insert(ignore_permissions=True)
		return doc.name


def _pick_manager():
	"""First Active employee that already has at least one direct report."""
	for emp in frappe.get_all("Employee", filters={"status": "Active"}, fields=["name"]):
		if frappe.db.count("Employee", {"reports_to": emp.name, "status": "Active"}) > 0:
			return emp.name
	return None


def run(manager_employee=None):
	frappe.set_user("Administrator")
	from_date = add_days(nowdate(), -60)
	to_date = add_days(nowdate(), 300)
	today_date = today()

	manager_employee = manager_employee or _pick_manager()
	if not manager_employee:
		frappe.throw(
			"No Employee has any direct reports (reports_to) on this site. "
			"Pass manager_employee explicitly, or set reports_to on some Employees first."
		)

	manager = frappe.db.get_value(
		"Employee", manager_employee, ["name", "user_id", "company"], as_dict=True
	)
	if not manager:
		frappe.throw(f"Employee {manager_employee} not found.")

	team = frappe.get_all(
		"Employee",
		filters={"reports_to": manager.name, "status": "Active"},
		fields=["name", "company"],
		limit_page_length=5,
	)
	if not team:
		frappe.throw(f"Employee {manager.name} has no direct reports to seed.")

	statuses = ["Present", "Half Day", "Absent", "On Leave", "Present"]
	created = {"leave_allocation": [], "leave_application": [], "attendance": [], "checkin": []}

	for i, emp in enumerate(team):
		alloc = _ensure_leave_allocation(emp.name, emp.company, 20, from_date, to_date)
		created["leave_allocation"].append(alloc)

		# pending leave request -> shows in Manager "Pending Approvals"
		req_from = add_days(today_date, 5 + i)
		req_to = add_days(req_from, 1)
		app = _ensure_leave_application(
			emp.name, emp.company, manager.user_id, req_from, req_to, status="Open"
		)
		created["leave_application"].append(app)

		att = _ensure_attendance(emp.name, emp.company, today_date, statuses[i % len(statuses)])
		created["attendance"].append(att)

	# Seed the manager's own "My Dashboard" data too
	mgr_alloc = _ensure_leave_allocation(manager.name, manager.company, 20, from_date, to_date)
	created["leave_allocation"].append(mgr_alloc)
	mgr_req_from = add_days(today_date, 10)
	mgr_req_to = add_days(mgr_req_from, 2)
	created["leave_application"].append(
		_ensure_leave_application(
			manager.name, manager.company, manager.user_id, mgr_req_from, mgr_req_to, status="Open"
		)
	)
	for d in range(5):
		created["attendance"].append(
			_ensure_attendance(manager.name, manager.company, add_days(today_date, -d), "Present")
		)
	created["checkin"].append(_ensure_checkin(manager.name, "IN", f"{today_date} 09:02:00"))

	frappe.db.commit()
	print(frappe.as_json({"manager_employee": manager.name, **created}))
