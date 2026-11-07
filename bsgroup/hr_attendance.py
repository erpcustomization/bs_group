"""Permission-filtered HR calendar; manual entries never fabricate punches."""
from datetime import date, timedelta
import frappe
from frappe.utils import nowdate
from bsgroup.hr_management import _guard


def month_bounds(month):
    try:
        start = date.fromisoformat(str(month) + "-01")
    except (ValueError, TypeError):
        frappe.throw("Choose a valid month (YYYY-MM).")
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, end


def _rows(dt, fields, filters, restricted):
    if not frappe.has_permission(dt, "read"):
        restricted.append(dt)
        return []
    return frappe.get_list(dt, fields=fields, filters=filters, limit_page_length=0)


def calendar_days(start, end, logs, leaves, attendance, requests, today):
    days = {}
    day = start
    while day < end:
        key = day.isoformat()
        days[key] = dict(date=key, punches=[], leaves=[], attendance=[], requests=[],
                         future=key > today)
        day += timedelta(days=1)
    for row in logs:
        key = str(row["time"])[:10]
        if key in days:
            days[key]["punches"].append(dict(row))
    for row in attendance:
        key = str(row["attendance_date"])[:10]
        if key in days:
            days[key]["attendance"].append(dict(row))
    for kind, rows in (("leaves", leaves), ("requests", requests)):
        for row in rows:
            for key, entry in days.items():
                if str(row["from_date"])[:10] <= key <= str(row["to_date"])[:10]:
                    item = dict(row)
                    item["is_half_day"] = bool(row.get("half_day") and str(row.get("half_day_date"))[:10] == key)
                    if kind == "leaves":
                        item["approved"] = row.get("docstatus") == 1 and row.get("status") == "Approved"
                    entry[kind].append(item)
    for entry in days.values():
        entry["punches"].sort(key=lambda r: str(r["time"]))
    return list(days.values())


@frappe.whitelist()
def month_view(month, employee=None):
    _guard()
    start, end = month_bounds(month)
    if not frappe.has_permission("Employee", "read"):
        frappe.throw("Employee records are restricted by your existing access.", frappe.PermissionError)
    employees = frappe.get_list("Employee", fields=["name", "employee_name", "company", "status"],
                                order_by="employee_name asc", limit_page_length=0)
    if not employees:
        return dict(employees=[], days=[], restricted=[])
    employee = employee or employees[0].name
    if employee not in {e.name for e in employees}:
        frappe.throw("This employee is outside your permitted HR view.", frappe.PermissionError)
    emp = frappe.get_doc("Employee", employee)
    emp.check_permission("read")
    restricted = []
    logs = _rows("Employee Checkin", ["name", "time", "log_type"],
                 [["employee", "=", employee], ["time", ">=", str(start) + " 00:00:00"],
                  ["time", "<", str(end) + " 00:00:00"]], restricted)
    overlap = [["employee", "=", employee], ["docstatus", "!=", 2],
               ["from_date", "<", str(end)], ["to_date", ">=", str(start)]]
    leaves = _rows("Leave Application", ["name", "from_date", "to_date", "leave_type", "status",
                   "docstatus", "half_day", "half_day_date"], overlap, restricted)
    attendance = _rows("Attendance", ["name", "attendance_date", "status", "docstatus"],
                       [["employee", "=", employee], ["docstatus", "!=", 2],
                        ["attendance_date", ">=", str(start)], ["attendance_date", "<", str(end)]], restricted)
    requests = _rows("Attendance Request", ["name", "from_date", "to_date", "reason", "docstatus",
                     "half_day", "half_day_date"], overlap, restricted)
    return dict(employees=employees, employee=employee, company=emp.company, today=nowdate(),
                days=calendar_days(start, end, logs, leaves, attendance, requests, nowdate()),
                restricted=restricted,
                can_record=frappe.has_permission("Attendance", "create") and
                           frappe.has_permission("HR Service Request", "read"))


@frappe.whitelist(methods=["POST"])
def record_manual(employee, attendance_date, status, employee_request, reason):
    """Prepare native Attendance for HR review/submission, with a required request trail."""
    _guard()
    if not frappe.has_permission("Attendance", "create"):
        frappe.throw("Attendance creation is restricted by your existing access.", frappe.PermissionError)
    try:
        day = date.fromisoformat(str(attendance_date))
    except (ValueError, TypeError):
        frappe.throw("Choose a valid attendance date.")
    if str(day) > nowdate():
        frappe.throw("Manual attendance can only be recorded for today or a past date.")
    if status not in ("Present", "Absent", "Half Day", "Work From Home"):
        frappe.throw("Use the leave approval process to record leave.")
    if not str(reason or "").strip() or not employee_request:
        frappe.throw("An employee request and HR reason are required.")
    emp = frappe.get_doc("Employee", employee)
    emp.check_permission("read")
    request = frappe.get_doc("HR Service Request", employee_request)
    request.check_permission("read")
    if request.employee != employee or request.company != emp.company:
        frappe.throw("The request must belong to this employee and company.")
    # Serialize calendar corrections for this employee. Native Attendance validation
    # remains authoritative; no permission filters are bypassed for record writes.
    frappe.db.get_value("Employee", employee, "name", for_update=True)
    if frappe.db.exists("Attendance", {"employee": employee, "attendance_date": str(day), "docstatus": ["!=", 2]}):
        frappe.throw("An attendance record already exists. Open it from the calendar and use the existing HR correction or amendment process.")
    if frappe.db.exists("Leave Application", {"employee": employee, "docstatus": 1, "status": "Approved",
                       "from_date": ["<=", str(day)], "to_date": [">=", str(day)]}):
        frappe.throw("Approved leave covers this date. Review the leave application before recording a correction.")
    doc = frappe.get_doc(dict(doctype="Attendance", employee=employee, company=emp.company,
                             attendance_date=str(day), status=status))
    doc.insert()
    from frappe.utils import escape_html
    doc.add_comment("Info", "Manual attendance prepared by HR upon employee request {0}. Reason: {1}. "
                    "Original Employee Checkin records were not changed.".format(
                        escape_html(employee_request), escape_html(str(reason).strip())))
    return dict(name=doc.name, docstatus=doc.docstatus)
