"""Editable project plan backed by existing Tasks and native ToDo assignments."""
import json
from html import escape

import frappe
from frappe import _
from frappe.utils import getdate, get_datetime, strip_html

PLAN_STATUSES = ("Open", "In Progress", "Delayed", "On Hold", "Completed")
WORK_SUBJECT = "Project Plan daily work"


class ProjectPlanTaskMixin:
    def update_status(self):
        # A deadline warning must not overwrite a user's execution status.
        if self.get("custom_bs_plan_status_managed") and self.status in PLAN_STATUSES:
            return
        return super().update_status()


def validate_template_status(doc, method=None):
    """Keep native template generation compatible with the site's task stages."""
    generated = doc.is_new() and doc.get("template_task") and doc.status == "Open"
    template = doc.get("is_template") and doc.status == "Template"
    if not (generated or template):
        return
    field = doc.meta.get_field("status")
    options = (field.options or "").splitlines()
    if doc.status not in options:
        if "Project Planning" not in options:
            frappe.throw(_("The Task status setup needs a Project Planning stage for template activities."))
        doc.status = "Project Planning"


def install():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    meta = frappe.get_meta("Project")
    # Insert at the end of Details, before the first existing Tab Break. Do not
    # move any existing fields into a different tab.
    previous = None
    for field in meta.fields:
        if field.fieldtype == "Tab Break":
            break
        previous = field.fieldname
    definitions = [
        dict(fieldname="custom_bs_project_plan_tab", label="Project Plan", fieldtype="Tab Break", insert_after=previous),
        dict(fieldname="custom_bs_project_plan", label="Project Plan", fieldtype="HTML", insert_after="custom_bs_project_plan_tab"),
    ]
    missing = []
    for definition in definitions:
        existing = meta.get_field(definition["fieldname"])
        if existing and existing.fieldtype != definition["fieldtype"]:
            frappe.throw(_("Project Plan field has an incompatible type: {0}").format(definition["fieldname"]))
        if not existing:
            missing.append(definition)
    if missing:
        create_custom_fields({"Project": missing}, update=False)
    if not frappe.get_meta("Task").has_field("custom_bs_plan_status_managed"):
        create_custom_fields({"Task": [dict(fieldname="custom_bs_plan_status_managed", label="Project Plan Status Managed",
            fieldtype="Check", insert_after="status", hidden=1, read_only=1, default="0")]}, update=False)
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    options = [value for value in (frappe.get_meta("Task").get_field("status").options or "").splitlines() if value]
    combined = options + [value for value in PLAN_STATUSES if value not in options]
    if combined != options:
        make_property_setter("Task", "status", "options", "\n".join(combined), "Text")
    frappe.clear_cache(doctype="Project")
    frappe.clear_cache(doctype="Task")
    return {"installed": True}


@frappe.whitelist(methods=["POST"])
def setup():
    frappe.only_for("System Manager")
    return install()


def _project(name, write=False):
    if not name:
        frappe.throw(_("Save and open a project first."))
    doc = frappe.get_doc("Project", name)
    doc.check_permission("write" if write else "read")
    if write and doc.status in {"Completed", "Cancelled"}:
        frappe.throw(_("Completed or cancelled projects cannot be replanned."))
    return doc


def _users(value):
    values = frappe.parse_json(value) if isinstance(value, str) else value
    if not isinstance(values, list) or len(values) > 50 or any(not isinstance(v, str) or not v for v in values):
        frappe.throw(_("Choose valid assigned users."))
    return sorted(set(values))


def _assigned(value):
    try:
        values = json.loads(value or "[]")
        return sorted(set(v for v in values if isinstance(v, str))) if isinstance(values, list) else []
    except (TypeError, ValueError):
        return []


def _editable(task):
    return task.status not in {"Completed", "Cancelled", "Template"}


def _dated_value(original, value):
    # Some sites store expected dates as Datetime. Preserve an existing time of
    # day when moving its calendar date from this date-only planning screen.
    if not value:
        return None
    date = getdate(value)
    if original and (hasattr(original, "hour") or " " in str(original)):
        return get_datetime(original).replace(year=date.year, month=date.month, day=date.day)
    return date


def _eligible(user, project, task):
    account = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(account and account.enabled and account.user_type == "System User"
                and frappe.has_permission("Project", "read", doc=project, user=user)
                and frappe.has_permission("Task", "read", doc=task, user=user))


@frappe.whitelist()
def get_plan(project):
    doc = _project(project)
    can_edit = bool(doc.status not in {"Completed", "Cancelled"} and frappe.has_permission("Project", "write", doc=doc)
                    and frappe.has_permission("Task", "write"))
    rows = frappe.get_list("Task", filters={"project": doc.name, "is_template": 0},
        fields=["name", "subject", "description", "exp_start_date", "exp_end_date", "status", "parent_task", "is_group", "_assign", "modified"],
        order_by="lft asc, creation asc", limit_page_length=0) if frappe.has_permission("Task", "read") else []
    assigned = set()
    for row in rows:
        row["assigned_to"] = _assigned(row.pop("_assign", None))
        if row.status == "Completed" and not row["assigned_to"]:
            row["assigned_to"] = sorted(set(frappe.get_all("ToDo", filters={"reference_type": "Task",
                "reference_name": row.name, "status": "Closed"}, pluck="allocated_to")))
        row["description_text"] = strip_html(row.description or "")
        for field in ("exp_start_date", "exp_end_date"):
            row[field] = str(getdate(row[field])) if row[field] else None
        row["can_edit"] = can_edit and _editable(row)
        item = frappe.get_doc("Task", row.name)
        row["can_edit"] = row["can_edit"] and frappe.has_permission("Task", "write", doc=item)
        row["can_log_work"] = doc.status != "Cancelled" and row.status not in {"Cancelled", "Template"} and _is_assigned(item, closed=True)
        from bsgroup.project_daily_work import enabled, TERMINAL
        if enabled() and (row.status in TERMINAL or doc.status == "Completed"):
            row["can_log_work"] = False
        project_status_editable = doc.status != "Cancelled" and (doc.status != "Completed" or frappe.has_permission("Project", "write", doc=doc))
        row["can_change_status"] = project_status_editable and row.status not in {"Cancelled", "Template"} and (
            frappe.has_permission("Task", "write", doc=item) or (row.status != "Completed" and _is_assigned(item)))
        row["overdue"] = bool(row.exp_end_date and getdate(row.exp_end_date) < getdate() and row.status not in {"Completed", "Cancelled"})
        assigned.update(row["assigned_to"])
    names = {r.name: r.full_name or r.name for r in frappe.get_all("User", filters={"name": ["in", sorted(assigned)]},
             fields=["name", "full_name"])} if assigned else {}
    ai_plan = {"installed": False, "runs": []}
    if frappe.db.exists("DocType", "BS Project Plan Run"):
        from bsgroup.project_ai_plan import summary
        ai_plan = summary(doc.name)
    return dict(project=doc.name, project_name=doc.project_name, rows=rows, user_names=names,
                ai_plan=ai_plan,
                can_create=bool(doc.status not in {"Completed", "Cancelled"} and frappe.has_permission("Project", "write", doc=doc)
                                and frappe.has_permission("Task", "create")), company=doc.company,
                can_read_tasks=bool(frappe.has_permission("Task", "read")), status_options=list(PLAN_STATUSES),
                work_updates_ready=frappe.get_meta("Task").has_field("custom_bs_plan_status_managed"))


def _is_assigned(item, closed=False):
    return bool(frappe.db.exists("ToDo", {"reference_type": "Task", "reference_name": item.name,
        "allocated_to": frappe.session.user, "status": ["in", ["Open", "Closed"] if closed and item.status == "Completed" else ["Open"]]}))


def _read_task(project, task, lock=False):
    doc = _project(project)
    item = frappe.get_doc("Task", task, for_update=lock)
    item.check_permission("read")
    if item.project != doc.name:
        frappe.throw(_("The task must belong to this project."), frappe.PermissionError)
    return doc, item


@frappe.whitelist()
def work_history(project, task):
    _read_task(project, task)
    rows = frappe.get_all("Comment", filters={"reference_doctype": "Task", "reference_name": task,
        "comment_type": "Comment", "subject": WORK_SUBJECT}, fields=["name", "creation", "comment_by", "comment_email", "content"],
        order_by="creation desc", limit_page_length=100)
    for row in rows:
        row["text"] = strip_html(row.pop("content") or "")
    return rows


@frappe.whitelist(methods=["POST"])
def save_work(project, task, work, request_id=None):
    doc, item = _read_task(project, task, lock=True)
    if doc.status == "Cancelled" or item.status in {"Cancelled", "Template"} or not _is_assigned(item, closed=True):
        frappe.throw(_("Only users assigned to this task can enter today's work."), frappe.PermissionError)
    text = (work or "").strip()
    if not text or len(text) > 20000:
        frappe.throw(_("Enter the work completed today (up to 20,000 characters)."))
    from bsgroup.project_daily_work import enabled, capture
    if enabled():
        return capture(doc, item, text, request_id)
    author = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
    content = "<p><strong>Today's work — " + str(getdate()) + "</strong></p><p>" + escape(text).replace("\n", "<br>") + "</p>"
    # Comments are the native Task activity history. The caller and task are
    # checked above; users cannot supply an author, date, reference or HTML.
    entry = frappe.get_doc(dict(doctype="Comment", comment_type="Comment", reference_doctype="Task",
        reference_name=item.name, subject=WORK_SUBJECT, content=content,
        comment_email=frappe.session.user, comment_by=author)).insert(ignore_permissions=True)
    return {"name": entry.name, "task": item.name}


@frappe.whitelist(methods=["POST"])
def set_task_status(project, task, status, expected_modified):
    from bsgroup.project_daily_work import enabled
    if enabled() and status == "Closed":
        status = "Completed"
    savepoint = "plan_status_" + frappe.generate_hash(length=10)
    frappe.db.savepoint(savepoint)
    try:
        doc, item = _read_task(project, task, lock=True)
        writable = frappe.has_permission("Task", "write", doc=item)
        assigned = item.status != "Completed" and _is_assigned(item)
        project_locked = doc.status == "Cancelled" or (doc.status == "Completed" and not (writable and frappe.has_permission("Project", "write", doc=doc)))
        if project_locked or item.status in {"Cancelled", "Template"} or not (writable or assigned):
            frappe.throw(_("You cannot change this task's status."), frappe.PermissionError)
        if status not in PLAN_STATUSES:
            frappe.throw(_("Choose Open, In Progress, Delayed, On Hold or Completed."))
        if not item.meta.has_field("custom_bs_plan_status_managed"):
            frappe.throw(_("The Project Plan work screen must be enabled by an administrator first."))
        if not expected_modified or get_datetime(item.modified) != get_datetime(expected_modified):
            frappe.throw(_("This task changed. Refresh the row before changing its status."))
        if item.status == "Completed" and status != "Completed":
            item.progress = 0
            item.completed_on = None
            item.completed_by = None
        item.status = status
        item.custom_bs_plan_status_managed = 1
        # The assigned-user exception is limited to this status-only endpoint.
        # Native validation, dependencies, assignment closure and audit run.
        item.save(ignore_permissions=not writable)
        return {"name": item.name, "status": item.status, "modified": item.modified}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


@frappe.whitelist()
def assignment_choices(project, task):
    doc = _project(project, write=True)
    item = frappe.get_doc("Task", task)
    item.check_permission("write")
    if item.project != doc.name:
        frappe.throw(_("The task must belong to this project."), frappe.PermissionError)
    users = frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"},
                           fields=["name", "full_name"], order_by="full_name asc")
    return [dict(value=u.name, label=u.full_name or u.name, description=u.name)
            for u in users if _eligible(u.name, doc, item)]


@frappe.whitelist(methods=["POST"])
def autosave_task(project, task, changes, expected_modified, expected_assignees):
    """Serialize one row's field changes using the existing guarded save paths."""
    changes = frappe.parse_json(changes) if isinstance(changes, str) else changes
    allowed = {"subject", "description", "start_date", "end_date", "assigned_to", "status"}
    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
        frappe.throw(_("Choose valid Project Plan fields to update."))
    savepoint = "plan_autosave_" + frappe.generate_hash(length=10)
    frappe.db.savepoint(savepoint)
    try:
        doc, item = _read_task(project, task, lock=True)
        if not expected_modified or get_datetime(item.modified) != get_datetime(expected_modified):
            frappe.throw(_("This task changed elsewhere. Reload the row before editing it again."))
        details = {key: value for key, value in changes.items() if key != "status"}
        if details:
            save_task(project, task,
                subject=details.get("subject", item.subject),
                description=details.get("description", item.description),
                start_date=details.get("start_date", str(getdate(item.exp_start_date)) if item.exp_start_date else None),
                end_date=details.get("end_date", str(getdate(item.exp_end_date)) if item.exp_end_date else None),
                assigned_to=details.get("assigned_to", expected_assignees),
                expected_modified=expected_modified, expected_assignees=expected_assignees)
            expected_modified = frappe.db.get_value("Task", task, "modified")
        if "status" in changes:
            set_task_status(project, task, changes["status"], expected_modified)
        # Read the receipt in this transaction, including native assignment and
        # permission changes. The next queued save uses this exact version.
        plan = get_plan(project)
        row = next((row for row in plan["rows"] if row.name == task), None)
        if not row:
            frappe.throw(_("The saved task is no longer accessible in this project."))
        return {"row": row, "user_names": plan["user_names"]}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


@frappe.whitelist(methods=["POST"])
def save_task(project, task, subject, description, start_date, end_date, assigned_to, expected_modified, expected_assignees):
    from frappe.desk.form import assign_to
    doc = _project(project, write=True)
    savepoint = "project_plan_" + frappe.generate_hash(length=10)
    frappe.db.savepoint(savepoint)
    try:
        item = frappe.get_doc("Task", task, for_update=True)
        item.check_permission("write")
        if item.project != doc.name:
            frappe.throw(_("The task must belong to this project."), frappe.PermissionError)
        if not _editable(item):
            frappe.throw(_("Completed, cancelled or template tasks cannot be replanned."))
        if not expected_modified or get_datetime(item.modified) != get_datetime(expected_modified):
            frappe.throw(_("This task changed. Refresh the plan before editing it."))
        selected = _users(assigned_to)
        todos = frappe.get_all("ToDo", filters={"reference_type": "Task", "reference_name": item.name, "status": "Open"},
                               fields=["name", "allocated_to", "date", "description"])
        current = sorted({todo.allocated_to for todo in todos})
        if current != _users(expected_assignees):
            frappe.throw(_("Task assignments changed. Refresh the plan before editing them."))
        title = (subject or "").strip()
        if not title:
            frappe.throw(_("An activity name is required."))
        start = getdate(start_date) if start_date else None
        end = getdate(end_date) if end_date else None
        if start and end and end < start:
            frappe.throw(_("End Date cannot be before Start Date."))
        for user in set(selected) - set(current):
            if not _eligible(user, doc, item):
                frappe.throw(_("Choose an active user who already has access to this project and task."), frappe.PermissionError)
        item.subject = title
        item.description = description or ""
        item.exp_start_date = _dated_value(item.exp_start_date, start)
        item.exp_end_date = _dated_value(item.exp_end_date, end)
        # Save the same Task through native validation, dependencies and audit hooks.
        item.save()
        end = getdate(item.exp_end_date) if item.exp_end_date else None
        for user in set(current) - set(selected):
            assign_to.remove("Task", item.name, user)
        added = sorted(set(selected) - set(current))
        if added:
            assign_to.add(dict(doctype="Task", name=item.name, assign_to=added,
                               description=title, date=end, priority=item.priority or "Medium"))
        # Like the native assignment API, task-write permission authorizes changes
        # to its ToDos. Only the retained assignment's text and due date are touched.
        for row in todos:
            if row.allocated_to in selected and (str(row.date or "") != str(end or "") or row.description != title):
                todo = frappe.get_doc("ToDo", row.name)
                todo.date = end
                todo.description = title
                todo.save(ignore_permissions=True)
        return {"name": item.name, "project": doc.name, "assigned_to": selected}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise
