# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.utils import getdate, today, add_days

STATUS_OPTIONS = [
    "Advance Payment - Invoice",
    "Pre-Implementation",
    "Project Planning",
    "Delivery in Progress",
    "In House Testing",
    "Implementation In Progress",
    "Project Documentation",
    "Sign-off in Progress",
    "Active 3CX AMC Clients",
    "Active Infra AMC Clients",
    "Only Delivery",
    "Pending from Implementation",
    "Pending from Sales Account",
    "Pending from Client",
    "Pending Sign-Off",
    "Pending Invoicing",
    "Completed",
]


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters or {})
    return columns, data


def get_columns():
    return [
        {"label": "Task",         "fieldname": "subject",        "fieldtype": "Data",    "width": 280},
        {"label": "Project Name", "fieldname": "project_name",   "fieldtype": "Data",    "width": 180},
        {"label": "Status",       "fieldname": "status",         "fieldtype": "Select",  "width": 200,
         "options": "\n".join(STATUS_OPTIONS)},
        {"label": "Created By",   "fieldname": "created_by",     "fieldtype": "Data",    "width": 160, "hidden": 1},
        {"label": "Assigned To",  "fieldname": "assigned_to",    "fieldtype": "Data",    "width": 160},
        {"label": "Start Date",   "fieldname": "exp_start_date", "fieldtype": "Date",    "width": 130},
        {"label": "End Date",     "fieldname": "exp_end_date",   "fieldtype": "Date",    "width": 130},
        {"label": "Progress",     "fieldname": "progress",       "fieldtype": "Percent", "width": 100},
        {"label": "Task ID",      "fieldname": "name",           "fieldtype": "Link",    "options": "Task", "hidden": 1},
    ]


def get_data(filters):
    conditions = []

    company = frappe.defaults.get_user_default("company")
    if company:
        conditions.append(["project.company", "=", company])

    if filters.get("task"):
        conditions.append(["name", "=", filters["task"]])

    if filters.get("project"):
        conditions.append(["project", "=", filters["project"]])

    if filters.get("created_by"):
        conditions.append(["custom_created_by", "=", filters["created_by"]])

    if filters.get("assigned_to"):
        conditions.append(["_assign", "like", f"%{filters['assigned_to']}%"])

    if filters.get("from_date"):
        conditions.append(["exp_end_date", ">=", filters["from_date"]])

    if filters.get("to_date"):
        conditions.append(["exp_start_date", "<=", filters["to_date"]])

    schedule = filters.get("schedule")
    if schedule:
        today_date = getdate(today())
        if schedule == "Scheduled for Today":
            conditions.append(["exp_start_date", "=", today_date])
        elif schedule == "Next Day":
            conditions.append(["exp_start_date", "=", add_days(today_date, 1)])
        elif schedule == "Week":
            conditions.append(["exp_start_date", ">=", today_date])
            conditions.append(["exp_start_date", "<=", add_days(today_date, 7)])

    task_state = filters.get("task_state")
    if task_state:
        if task_state == "Closed":
            conditions.append(["status", "in", ["Completed", "Cancelled"]])
        elif task_state == "Delayed":
            conditions.append(["exp_end_date", "<", getdate(today())])
            conditions.append(["status", "not in", ["Completed", "Cancelled"]])

    tasks = frappe.get_all(
        "Task",
        fields=[
            "name", "subject", "project", "status", "priority",
            "exp_start_date", "exp_end_date", "progress",
            "parent_task", "is_group", "lft",
            "custom_created_by", "_assign", "creation",
        ],
        filters=conditions,
        order_by="lft asc",
    )

    user_emails = set()
    for t in tasks:
        if t.get("custom_created_by"):
            user_emails.add(t["custom_created_by"])
        for email in _parse_assign(t.get("_assign")):
            user_emails.add(email)

    full_names = _get_full_names(user_emails)

    project_names = {}
    for t in tasks:
        if t.project and t.project not in project_names:
            project_names[t.project] = frappe.db.get_value("Project", t.project, "project_name") or t.project

    task_map = {t.name: t for t in tasks}
    children_of = {}
    roots = []
    for t in tasks:
        p = t.get("parent_task")
        if p and p in task_map:
            children_of.setdefault(p, []).append(t)
        else:
            roots.append(t)

    def _sort_key(t):
        return t.get("creation") or ""

    roots.sort(key=_sort_key)
    for v in children_of.values():
        v.sort(key=_sort_key)

    result = []

    def _walk(task, indent):
        assigned_emails = _parse_assign(task.get("_assign"))
        assigned_names  = ", ".join(full_names.get(e, e) for e in assigned_emails)
        created_email   = task.get("custom_created_by") or ""
        created_name    = full_names.get(created_email, created_email)

        result.append({
            "name":           task.name,
            "subject":        task.subject,
            "project_name":   project_names.get(task.project, ""),
            "status":         task.status,
            "priority":       task.priority,
            "exp_start_date": task.exp_start_date,
            "exp_end_date":   task.exp_end_date,
            "progress":       task.progress,
            "created_by":     created_name,
            "assigned_to":    assigned_names,
            "indent":         indent,
            "is_group":       task.is_group,
        })
        for child in children_of.get(task.name, []):
            _walk(child, indent + 1)

    for root in roots:
        _walk(root, 0)

    _compute_group_progress(result)
    return result


def _compute_group_progress(rows):
    for row in reversed(rows):
        if not row.get("is_group"):
            continue
        children = [r for r in rows if r.get("parent_task") == row["name"]]
        if children:
            row["progress"] = sum(_flt(c.get("progress") or 0) for c in children) / len(children)


def _flt(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _parse_assign(raw):
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (ValueError, TypeError):
        return []


def _get_full_names(emails):
    if not emails:
        return {}
    rows = frappe.get_all(
        "User",
        filters=[["name", "in", list(emails)]],
        fields=["name", "full_name"],
    )
    return {r.name: r.full_name for r in rows}
