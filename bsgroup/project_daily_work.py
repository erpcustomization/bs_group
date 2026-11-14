"""Oman/UAE daily work capture; UAE project completion rollup."""
import hashlib
from html import escape
from urllib.parse import urlparse

import frappe
from frappe import _

TERMINAL = ("Completed", "Closed", "Cancelled", "Template")


class ProjectDailyWorkMixin:
    def update_percent_complete(self):
        if complete_project(self):
            return
        return super().update_percent_complete()


def enabled():
    """Existing UAE completion behaviour, kept separate from timesheet rollout."""
    hosts = {"erp.bitssecureit.com", "erp-bitssecureit.u.frappe.cloud"}
    return (urlparse((getattr(frappe, "conf", None) or {}).get("host_name") or "").hostname in hosts
            or getattr(getattr(frappe, "local", None), "site", None) in hosts)


def timesheets_enabled():
    hosts = {"erp-om.bitssecureit.com", "erp-om.k.frappe.cloud"}
    return (enabled() or
            urlparse((getattr(frappe, "conf", None) or {}).get("host_name") or "").hostname in hosts or
            getattr(getattr(frappe, "local", None), "site", None) in hosts)


def install():
    if not timesheets_enabled():
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Timesheet Detail": [
        dict(fieldname="custom_bs_work_date", label="Work Date", fieldtype="Date", read_only=1,
             insert_after="description", in_list_view=1),
        dict(fieldname="custom_bs_work_entry", label="Project Daily Work", fieldtype="Link",
             options="Comment", read_only=1, no_copy=1, hidden=1, insert_after="custom_bs_work_date"),
    ]}, update=False)


def capture(project, task, work, request_id):
    from frappe.utils import getdate
    from bsgroup.project_plan import WORK_SUBJECT
    if task.status in TERMINAL or project.status in ("Completed", "Cancelled"):
        frappe.throw(_("This task is closed. Reopen it before recording more work."))
    if not request_id or not isinstance(request_id, str) or len(request_id) > 100:
        frappe.throw(_("Refresh the Project Plan and try saving your work again."))
    user = frappe.session.user
    key = "pdw-" + hashlib.sha256((user + "|" + task.name + "|" + request_id).encode()).hexdigest()[:32]
    existing = frappe.db.get_value("Timesheet Detail", {"custom_bs_work_entry": key, "docstatus": ["!=", 2]}, "parent")
    if existing:
        return dict(name=key, task=task.name, timesheet=existing)
    # Serialize this person's daily draft, including entries against different tasks.
    frappe.get_doc("User", user, for_update=True)
    day = getdate()
    drafts = frappe.get_all("Timesheet", filters={"owner": user, "user": user,
        "company": project.company, "custom_date": day, "docstatus": 0,
        "parent_project": ["is", "not set"]}, pluck="name", limit_page_length=1)
    sheet = frappe.get_doc("Timesheet", drafts[0], for_update=True) if drafts else frappe.new_doc("Timesheet")
    sheet.check_permission("write" if drafts else "create")
    if not drafts:
        from bsgroup.project_workspace import own_employee
        sheet.update(dict(user=user, company=project.company, custom_date=day, parent_project=None,
                          employee=own_employee(project.company)))
    author = frappe.db.get_value("User", user, "full_name") or user
    content = "<p><strong>Today's work — " + str(day) + "</strong></p><p>" + escape(work).replace("\n", "<br>") + "</p>"
    entry = frappe.get_doc(dict(doctype="Comment", comment_type="Comment", reference_doctype="Task",
        reference_name=task.name, subject=WORK_SUBJECT, content=content, comment_email=user, comment_by=author))
    entry.insert(ignore_permissions=True, set_name=key)
    sheet.append("time_logs", dict(project=project.name, task=task.name,
        custom_reference_type="Project", custom_reference=project.name,
        description=work, custom_bs_work_date=day, custom_bs_work_entry=entry.name,
        hours=0, is_billable=0))
    # Native draft validation runs; no hours, payroll submission or billing is fabricated.
    sheet.save()
    return dict(name=entry.name, task=task.name, timesheet=sheet.name, work_date=str(day))


def normalize_closed(doc, method=None):
    if enabled() and doc.project and doc.status == "Closed":
        doc.status = "Completed"


def complete_project(doc, method=None):
    if not enabled() or doc.is_new() or doc.status == "Cancelled":
        return
    statuses = frappe.get_all("Task", filters={"project": doc.name, "is_template": 0}, pluck="status")
    if statuses and all(status in ("Completed", "Closed") for status in statuses):
        doc.status = "Completed"
        doc.percent_complete = 100
        return True


def task_updated(doc, method=None):
    if enabled() and doc.project and (doc.is_new() or doc.has_value_changed("status")):
        # Reconcile after concurrent task commits, using fresh reads in a worker.
        frappe.enqueue("bsgroup.project_daily_work.reconcile", project=doc.project,
                       enqueue_after_commit=True, queue="short")


def reconcile(project):
    if not enabled():
        return
    doc = frappe.get_doc("Project", project, for_update=True)
    if doc.status == "Cancelled":
        return
    statuses = frappe.get_all("Task", filters={"project": project, "is_template": 0}, pluck="status")
    if statuses and all(status in ("Completed", "Closed") for status in statuses) and doc.status != "Completed":
        doc.status = "Completed"
        doc.percent_complete = 100
        doc.save(ignore_permissions=True)
