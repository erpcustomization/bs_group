# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.utils import getdate, today

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

ACTIVE_AMC_STATUSES = ["Active 3CX AMC Clients", "Active Infra AMC Clients"]
COMPLETED_STATUS    = "Completed"


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": "Task",         "fieldname": "subject",       "fieldtype": "Data",    "width": 300},
        # {"label": "Project Name", "fieldname": "project_name",  "fieldtype": "Data",    "width": 180},
        {"label": "Status",       "fieldname": "status",        "fieldtype": "Select",  "width": 200,
        "options": "\n".join(STATUS_OPTIONS)},
        {"label": "Priority",     "fieldname": "priority",      "fieldtype": "Select",  "width": 110,
        "options": "Low\nMedium\nHigh\nUrgent"},
        {"label": "Start Date",   "fieldname": "exp_start_date","fieldtype": "Date",    "width": 130},
        {"label": "End Date",     "fieldname": "exp_end_date",  "fieldtype": "Date",    "width": 130},
        {"label": "Progress",     "fieldname": "progress",      "fieldtype": "Percent", "width": 100},
        {"label": "Task ID",      "fieldname": "name",          "fieldtype": "Link",    "options": "Task", "hidden": 1},
        {"label": "Assigned To",  "fieldname": "assigned_to",   "fieldtype": "Data",    "width": 160},
    ]


def get_data(filters):
    conditions = []

    company = frappe.defaults.get_user_default("company")
    if company:
        conditions.append(["project.company", "=", company])

    if filters.get("project"):
        conditions.append(["project", "=", filters["project"]])

    if filters.get("parent_task"):
        conditions.append(["parent_task", "=", filters["parent_task"]])

    if filters.get("priority"):
        conditions.append(["priority", "=", filters["priority"]])

    # status / active / active_amc are mutually exclusive — status takes priority
    if filters.get("status"):
        conditions.append(["status", "=", filters["status"]])
    elif filters.get("active_amc"):
        conditions.append(["status", "in", ACTIVE_AMC_STATUSES])
    elif filters.get("active"):
        conditions.append(["status", "!=", COMPLETED_STATUS])

    if filters.get("assigned_to"):
        conditions.append(["_assign", "like", f"%{filters['assigned_to']}%"])

    tasks = frappe.get_all(
        "Task",
        fields=[
            "name", "subject", "project", "project.project_name as project_name",
            "status", "priority",
            "exp_start_date", "exp_end_date", "progress",
            "parent_task", "is_group", "lft", "_assign", "creation",
        ],
        filters=conditions,
        order_by="creation asc",
    )

    # Resolve assigned-to display names
    user_emails = set()
    for t in tasks:
        for email in _parse_assign(t.get("_assign")):
            user_emails.add(email)
    full_names = _get_full_names(user_emails)

    for t in tasks:
        if t.project:
            t.project_name = frappe.db.get_value("Project", t.project, "project_name")
        assigned_emails = _parse_assign(t.get("_assign"))
        t["assigned_to"] = ", ".join(full_names.get(e, e) for e in assigned_emails)

    # Date-range filter
    from_date = filters.get("from_date")
    to_date   = filters.get("to_date")
    if from_date or to_date:
        filtered = []
        for t in tasks:
            start = t.get("exp_start_date")
            end   = t.get("exp_end_date")
            if from_date and end   and end   < frappe.utils.getdate(from_date):
                continue
            if to_date   and start and start > frappe.utils.getdate(to_date):
                continue
            filtered.append(t)
        tasks = filtered

    # Build hierarchy: DFS with siblings sorted by creation asc (oldest first, newest last)
    task_map   = {t.name: t for t in tasks}
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

    def _walk(node, indent):
        node["indent"] = indent
        result.append(node)
        for child in children_of.get(node.name, []):
            _walk(child, indent + 1)

    for root in roots:
        _walk(root, 0)

    _compute_group_progress(result)
    return result


def _compute_group_progress(rows):
    """Set each group task's progress to the average of its direct children."""
    # Process in reverse order so deeper groups are resolved first
    name_to_row = {r["name"]: r for r in rows}
    for row in reversed(rows):
        if not row.get("is_group"):
            continue
        children = [r for r in rows if r.get("parent_task") == row["name"]]
        if children:
            row["progress"] = sum(flt(c.get("progress") or 0) for c in children) / len(children)


def flt(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def get_print_context(filters, data, columns):
    """Extra context injected into the Jinja print template."""
    project_doc = None
    if filters.get("project"):
        project_doc = frappe.db.get_value(
            "Project",
            filters["project"],
            [
                "name", "project_name", "customer", "project_manager",
                "expected_start_date", "expected_end_date",
                "customer_progress", "current_stage", "customer_remarks",
                "status", "company",
            ],
            as_dict=True,
        )

    total   = len(data)
    done    = sum(1 for r in data if r.get("status") == "Completed")
    overdue = sum(
        1 for r in data
        if r.get("status") not in ("Completed", "Cancelled")
        and r.get("exp_end_date")
        and frappe.utils.getdate(r["exp_end_date"]) < frappe.utils.getdate(frappe.utils.today())
    )

    return {
        "project_doc":   project_doc,
        "total_tasks":   total,
        "done_tasks":    done,
        "overdue_tasks": overdue,
        "report_date":   frappe.utils.formatdate(frappe.utils.today(), "dd MMM yyyy"),
    }


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
