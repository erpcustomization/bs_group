"""Project-scoped timesheet lines, using the parent document's permissions."""
import frappe
from frappe import _
from bsgroup.project_daily_work import enabled


def project_access(project):
    if not enabled():
        frappe.throw(_("Inline project timesheets are enabled for UAE only."))
    doc = frappe.get_doc("Project", project)
    doc.check_permission("read")
    return doc


def lines(project):
    project_access(project)
    parents = frappe.get_list("Timesheet", filters=[["Timesheet Detail", "project", "=", project]],
        fields=["name"], distinct=True, order_by="creation desc", limit_page_length=0)
    result = []
    for parent in parents:
        sheet = frappe.get_doc("Timesheet", parent.name)
        sheet.check_permission("read")
        editable = sheet.docstatus == 0 and frappe.has_permission("Timesheet", "write", doc=sheet)
        for row in sheet.time_logs:
            if row.project != project:
                continue
            result.append(dict(name=row.name, timesheet=sheet.name,
                date=str(row.get("custom_bs_work_date") or sheet.get("custom_date") or
                         (str(row.from_time)[:10] if row.from_time else "")),
                employee=sheet.employee_name or sheet.user or sheet.owner,
                task=row.task or "", task_title=frappe.db.get_value("Task", row.task, "subject") if row.task else "",
                work=row.description or "", editable=bool(editable),
                status=sheet.status or ["Draft", "Submitted", "Cancelled"][sheet.docstatus]))
    return sorted(result, key=lambda row: (row["date"], row["timesheet"]), reverse=True)


@frappe.whitelist(methods=["POST"])
def save_work(project, timesheet, row_name, work, expected_work):
    project_access(project)
    if not isinstance(work, str) or not work.strip() or len(work) > 20000:
        frappe.throw(_("Enter the work completed (up to 20,000 characters)."))
    sheet = frappe.get_doc("Timesheet", timesheet, for_update=True)
    sheet.check_permission("read")
    sheet.check_permission("write")
    if sheet.docstatus != 0:
        frappe.throw(_("Only draft timesheet entries can be edited."))
    row = next((item for item in sheet.time_logs if item.name == row_name and item.project == project), None)
    if row is None:
        frappe.throw(_("This entry does not belong to this project."))
    current = row.description or ""
    value = work.strip()
    if current == value:
        return dict(work=current, timesheet=sheet.name, row_name=row.name)
    if current != expected_work:
        frappe.throw(_("This entry was changed by another user. Refresh to see the latest work before editing."))
    row.description = value
    # Preserve the original work date, employee, task, hours and source history.
    sheet.save()
    return dict(work=row.description, timesheet=sheet.name, row_name=row.name)
