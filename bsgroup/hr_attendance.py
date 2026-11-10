"""Permission-filtered HR calendar; manual entries never fabricate punches."""
from datetime import date, timedelta
import frappe
from bsgroup.attendance_place import describe_location
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
            days[key]["punches"].append(dict(row, location=describe_location(row.get("latitude"), row.get("longitude"))))
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
    logs = _rows("Employee Checkin", ["name", "time", "log_type", "latitude", "longitude"],
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
                repair_mithun=employee == "1047" and str(start) == "2026-11-01" and
                    "System Manager" in frappe.get_roles() and any(
                        r.name in ("HR-ATT-2026-03642", "HR-ATT-2026-03658") and r.docstatus == 1
                        for r in attendance),
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


# One-time, explicitly requested correction. No generic attendance override and
# no broad shift reprocessing: only these two original attendance/punch pairs.
MITHUN_REPAIR = (
    ("2026-11-06", "HR-ATT-2026-03642", (("EMP-CKIN-11-2026-000100", "IN", "2026-11-06 09:01:37"),
                                         ("EMP-CKIN-11-2026-000114", "OUT", "2026-11-06 21:17:34"))),
    ("2026-11-07", "HR-ATT-2026-03658", (("EMP-CKIN-11-2026-000116", "IN", "2026-11-07 08:37:38"),
                                         ("EMP-CKIN-11-2026-000129", "OUT", "2026-11-07 19:00:33"))),
)


@frappe.whitelist(methods=["POST"])
def repair_mithun_november():
    """Cancel/amend erroneous absences using native validation and original punches."""
    frappe.only_for("System Manager")
    from frappe.utils import getdate, get_datetime
    frappe.db.get_value("Employee", "1047", "name", for_update=True)
    shift = frappe.get_doc("Shift Type", "General - UAE")
    shift.check_permission("read")
    if int(shift.allow_check_out_after_shift_end_time or 0) < 360:
        frappe.throw("Save the corrected evening checkout window before recalculating.")
    if not frappe.has_permission("Attendance", "create") or not frappe.has_permission("Attendance", "submit"):
        frappe.throw("Native Attendance create and submit permission are required.", frappe.PermissionError)
    results = []
    for day, old_name, expected in MITHUN_REPAIR:
        old = frappe.get_doc("Attendance", old_name, for_update=True)
        old.check_permission("read")
        if old.docstatus == 2:
            replacement = frappe.get_list("Attendance", filters={"amended_from":old_name,"docstatus":1},
                                          fields=["name","status"], limit_page_length=2)
            if len(replacement) == 1 and replacement[0].status == "Present":
                results.append(dict(date=day,name=replacement[0].name,status="Present",already_done=True))
                continue
            frappe.throw("The original attendance was already cancelled. Review its amendment before continuing.")
        old.check_permission("cancel")
        old.check_permission("amend")
        if old.employee != "1047" or str(getdate(old.attendance_date)) != day or old.docstatus != 1 or old.status != "Absent" or old.shift != shift.name:
            frappe.throw("Attendance no longer matches the reviewed absence. No correction was applied.")
        if frappe.db.exists("Leave Application", {"employee":"1047","docstatus":1,"status":"Approved",
                            "from_date":["<=",day],"to_date":[">=",day]}):
            frappe.throw("Approved leave now covers this date. HR review is required.")
        logs=[]
        for name, kind, stamp in expected:
            log=frappe.get_doc("Employee Checkin",name,for_update=True)
            log.check_permission("write")
            if log.employee != "1047" or log.log_type != kind or get_datetime(log.time) != get_datetime(stamp) or log.skip_auto_attendance or log.attendance not in (None,"",old_name):
                frappe.throw("The original punches changed or are excluded. No correction was applied.")
            logs.append(log)
        # Exact pair only; do not silently ignore any newly added punch on either date.
        names=frappe.get_list("Employee Checkin",filters=[["employee","=","1047"],
                             ["time",">=",day+" 00:00:00"],["time","<=",day+" 23:59:59"]],pluck="name",limit_page_length=0)
        if set(names) != {x[0] for x in expected}:
            frappe.throw("Additional punches exist for this date. Review them before recalculation.")
        old.cancel()  # Native cancellation unlinks punches; entire request rolls back on failure.
        for log in logs:
            log.reload()
            log.fetch_shift()
            if log.offshift or log.shift != shift.name:
                frappe.throw("A punch is still outside the corrected shift window.")
            log.save()
        status,hours,late,early,in_time,out_time=shift.get_attendance(
            [frappe._dict(log.as_dict()) for log in logs],
            shift.working_hours_threshold_for_absent,shift.working_hours_threshold_for_half_day)
        if status != "Present" or not in_time or not out_time:
            frappe.throw("Original punches do not meet the unchanged Present threshold.")
        corrected=frappe.get_doc(dict(doctype="Attendance",employee=old.employee,company=old.company,
            attendance_date=day,shift=shift.name,status=status,working_hours=hours,late_entry=late,
            early_exit=early,in_time=in_time,out_time=out_time,amended_from=old.name))
        corrected.insert()
        corrected.submit()
        from hrms.hr.doctype.employee_checkin.employee_checkin import update_attendance_in_checkins
        update_attendance_in_checkins([log.name for log in logs],corrected.name)
        note="Corrected premature absence after repairing the General - UAE checkout window. Recalculated from original punches {0}; no timestamps or working-hours thresholds changed. Replaces {1}.".format(
            ", ".join(log.name for log in logs),old.name)
        corrected.add_comment("Info",note)
        old.add_comment("Info","Corrected by amendment {0}. {1}".format(corrected.name,note))
        results.append(dict(date=day,name=corrected.name,status=status,working_hours=hours))
    return results
