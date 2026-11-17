"""One delivery per new supply-only handover; procurement never proves delivery."""
from contextlib import contextmanager
from contextvars import ContextVar
from html import escape

import frappe
from frappe import _
from frappe.utils import now_datetime, strip_html, get_datetime

DT = "Delivery Request"
_internal = ContextVar("bs_delivery_internal", default=False)


@contextmanager
def writing():
    token = _internal.set(True)
    try:
        yield
    finally:
        _internal.reset(token)


def supply_only(modules):
    return set(modules or []) == {"supply"}


def procurement_stage(request):
    """Use standard MR progress; never equate purchase receipt with customer delivery."""
    if request.docstatus == 2 or request.status == "Cancelled":
        return "Cancelled", "On Hold"
    if request.status == "Stopped":
        return "Procurement stopped", "On Hold"
    if request.get("workflow_state") == "Rejected":
        return "Requisition rejected", "On Hold"
    if request.docstatus != 1 or request.get("workflow_state") != "Approved":
        return "Awaiting requisition approval", "Open"
    progress = request.status or "Pending"
    return "Approved — " + progress, "In Progress"


def assignees(task):
    return set(frappe.get_all("ToDo", filters={"reference_type": "Task",
        "reference_name": task, "status": "Open"}, pluck="allocated_to"))


def manager(project, user):
    if "BS Projects Manager" in frappe.get_roles(user or frappe.session.user):
        return True
    if user == "Administrator" or user == "mohan@bitssecureit.com":
        return True
    employee = frappe.db.get_value("Project", project, "custom_project_manager")
    return bool(employee and frappe.db.exists("Employee", {
        "name": employee, "user_id": user, "status": "Active"}))


def permission(doc, user=None, permission_type=None, **kwargs):
    user = user or frappe.session.user
    if permission_type not in (None, "read", "write", "select"):
        return False
    assigned = user in assignees(doc.task)
    # Completion remains visible to its author after native Task closes ToDos.
    if permission_type == "write":
        return assigned and doc.status != "Completed"
    return assigned or user in (doc.get("coordinator"), doc.get("delivery_person")) or manager(doc.project, user)


def query(user=None):
    user = user or frappe.session.user
    if "BS Projects Manager" in frappe.get_roles(user or frappe.session.user):
        return ""
    if user in ("Administrator", "mohan@bitssecureit.com"):
        return ""
    u = frappe.db.escape(user)
    return f"""(`tabDelivery Request`.coordinator={u} or `tabDelivery Request`.delivery_person={u} or exists (
        select 1 from `tabToDo` a where a.reference_type='Task'
        and a.reference_name=`tabDelivery Request`.task and a.status='Open' and a.allocated_to={u})
        or exists (select 1 from `tabProject` p join `tabEmployee` e
        on e.name=p.custom_project_manager where p.name=`tabDelivery Request`.project
        and e.user_id={u} and e.status='Active'))"""


def validate(doc, method=None):
    if _internal.get():
        return
    if doc.is_new():
        frappe.throw(_("Delivery Requests are created automatically from assigned Delivery activities."))
    old = doc.get_doc_before_save()
    for field in ("project", "task", "purchase_request", "company", "status", "procurement_stage",
                  "coordinator", "delivery_person", "coordinator_completed_on", "delivery_completed_on",
                  "completed_by", "completed_on"):
        if old and doc.get(field) != old.get(field):
            frappe.throw(_("Delivery links and status are controlled by the delivery process."))
    if old and old.status == "Completed":
        frappe.throw(_("Completed delivery evidence cannot be changed."))
    for role, person in (("coordinator", doc.get("coordinator")), ("delivery", doc.get("delivery_person"))):
        for field in (role + "_notes", role + "_proof"):
            if old and doc.get(field) != old.get(field) and (person != frappe.session.user or old.get(role + "_completed_on")):
                frappe.throw(_("Each person must record their own delivery work. Submitted evidence is retained."))


def protect_task(doc, method=None):
    if _internal.get():
        return
    old = doc.get_doc_before_save()
    if (doc.get("custom_bs_delivery_pr") or None) != (old.get("custom_bs_delivery_pr") or None if old else None):
        frappe.throw(_("The Delivery activity source is managed automatically."))
    if old and old.get("custom_bs_delivery_pr"):
        if any(doc.get(f) != old.get(f) for f in ("status", "project", "custom_bs_delivery_pr", "custom_bs_delivery_coordinator", "custom_bs_delivery_person")):
            frappe.throw(_("This Delivery activity follows procurement. Complete its Delivery Request with proof and notes."))


def synchronize(task_name):
    if not frappe.db.exists("Task", task_name):
        return
    task = frappe.get_doc("Task", task_name, for_update=True)
    pr = task.get("custom_bs_delivery_pr")
    if not pr:
        return
    request = frappe.get_doc("Material Request", pr)
    if request.get("custom_project") != task.project or request.company != task.company:
        frappe.throw(_("Delivery source no longer matches its project."))
    name = frappe.db.get_value(DT, {"task": task.name}, "name")
    delivery = frappe.get_doc(DT, name, for_update=True) if name else None
    if delivery and delivery.status == "Completed":
        return delivery.name
    stage, status = procurement_stage(request)
    with writing():
        if task.status != status or task.get("custom_bs_status_reason") != stage:
            task.update(dict(status=status, custom_bs_status_reason=stage))
            task.save(ignore_permissions=True)
        coordinator, person = task.get("custom_bs_delivery_coordinator"), task.get("custom_bs_delivery_person")
        paired = bool(coordinator and person and coordinator != person and assignees(task.name) == {coordinator, person})
        if not delivery and paired:
            delivery = frappe.get_doc(dict(doctype=DT, task=task.name, project=task.project,
                company=task.company, purchase_request=pr, status="Open", procurement_stage=stage,
                coordinator=coordinator, delivery_person=person))
            delivery.insert(ignore_permissions=True)
        elif delivery and (delivery.procurement_stage != stage or paired and (delivery.coordinator != coordinator or delivery.delivery_person != person)):
            delivery.procurement_stage = stage
            if paired and not delivery.coordinator_completed_on and not delivery.delivery_completed_on:
                delivery.update(dict(coordinator=coordinator, delivery_person=person))
            delivery.save(ignore_permissions=True)
    return delivery.name if delivery else None


def reconcile():
    if not frappe.get_meta("Task").has_field("custom_bs_delivery_person"):
        return
    for name in frappe.get_all("Task", filters={"custom_bs_delivery_pr": ["is", "set"],
            "status": ["not in", ["Completed", "Cancelled"]]}, pluck="name"):
        frappe.enqueue("bsgroup.supply_delivery.synchronize", task_name=name, queue="short")


def protect_evidence(doc, method=None):
    if frappe.db.exists("DocType", DT):
        for role in ("coordinator", "delivery"):
            if frappe.db.exists(DT, {role + "_proof": doc.file_url, role + "_completed_on": ["is", "set"]}):
                frappe.throw(_("Submitted delivery proof must be retained."))


def protect_assignment(doc, method=None):
    if _internal.get() or doc.reference_type != "Task" or not frappe.get_meta("Task").has_field("custom_bs_delivery_person"):
        return
    if not frappe.db.get_value("Task", doc.reference_name, "custom_bs_delivery_pr"):
        return
    old = doc.get_doc_before_save()
    if doc.is_new() or method == "on_trash" or old and (old.status != doc.status or old.allocated_to != doc.allocated_to):
        frappe.throw(_("Use Choose users on the Project Plan to assign the delivery coordinator and delivery person."))


@frappe.whitelist(methods=["POST"])
def assign(project, task, coordinator, delivery_person, expected_modified):
    from bsgroup.project_plan import _project, _eligible, save_task
    p = _project(project, write=True)
    item = frappe.get_doc("Task", task, for_update=True)
    item.check_permission("write")
    if item.project != p.name or not item.get("custom_bs_delivery_pr") or item.status in ("Completed", "Cancelled"):
        frappe.throw(_("Choose an open Delivery activity in this project."))
    if not expected_modified or get_datetime(item.modified) != get_datetime(expected_modified):
        frappe.throw(_("The activity changed. Refresh the plan and try again."))
    if not coordinator or not delivery_person or coordinator == delivery_person:
        frappe.throw(_("Choose two different people: the coordinator and the delivery person."))
    if not all(_eligible(user, p, item) for user in (coordinator, delivery_person)):
        frappe.throw(_("Choose active, eligible employees."), frappe.PermissionError)
    existing = frappe.db.get_value(DT, {"task": task}, ["coordinator", "delivery_person", "coordinator_completed_on", "delivery_completed_on"], as_dict=True)
    if existing and (existing.coordinator_completed_on or existing.delivery_completed_on) and (existing.coordinator != coordinator or existing.delivery_person != delivery_person):
        frappe.throw(_("A participant has already submitted work. Keep these delivery participants to retain their accountability."))
    with writing():
        item.update(dict(custom_bs_delivery_coordinator=coordinator, custom_bs_delivery_person=delivery_person))
        item.save()
        save_task(project, task, item.subject, item.description, item.exp_start_date, item.exp_end_date,
            [coordinator, delivery_person], item.modified, sorted(assignees(task)))
    return {"delivery_request": synchronize(task)}


def changed(doc, method=None):
    if _internal.get() or not frappe.db.exists("DocType", DT) or not frappe.get_meta("Task").has_field("custom_bs_delivery_person"):
        return
    names = []
    if doc.doctype == "Task" and doc.get("custom_bs_delivery_pr"):
        names = [doc.name]
    elif doc.doctype == "ToDo" and doc.reference_type == "Task":
        names = [doc.reference_name]
    elif doc.doctype == "Material Request":
        names = frappe.get_all("Task", filters={"custom_bs_delivery_pr": doc.name}, pluck="name")
    for name in names:
        # Defer until native assignment and procurement transactions have committed.
        frappe.enqueue("bsgroup.supply_delivery.synchronize", task_name=name,
                       enqueue_after_commit=True, queue="short")


@frappe.whitelist(methods=["POST"])
def complete(name):
    task_name = frappe.db.get_value(DT, name, "task")
    if not task_name:
        frappe.throw(_("Delivery Request was not found."))
    # Same lock order as the background reconciler prevents completion races.
    task = frappe.get_doc("Task", task_name, for_update=True)
    doc = frappe.get_doc(DT, name, for_update=True)
    user = frappe.session.user
    if doc.status == "Completed":
        if permission(doc, user, "read"):
            return {"name": doc.name, "status": doc.status}
        frappe.throw(_("You cannot open this delivery."), frappe.PermissionError)
    if user not in assignees(doc.task):
        frappe.throw(_("Only a user assigned to this Delivery activity can close it."), frappe.PermissionError)
    role = "coordinator" if user == doc.coordinator else "delivery" if user == doc.delivery_person else None
    if not role or assignees(doc.task) != {doc.coordinator, doc.delivery_person}:
        frappe.throw(_("The coordinator and delivery person must both remain assigned."))
    if doc.get(role + "_completed_on"):
        return {"name": doc.name, "status": doc.status, "already_recorded": True}
    project = frappe.get_doc("Project", doc.project, for_update=True)
    request = frappe.get_doc("Material Request", doc.purchase_request, for_update=True)
    if (task.project != project.name or task.get("custom_bs_delivery_pr") != request.name
            or request.get("custom_project") != project.name or request.company != project.company):
        frappe.throw(_("The delivery links changed. Ask the project manager to review them."))
    if project.status in ("Completed", "Cancelled") or request.docstatus != 1 or request.get("workflow_state") != "Approved" or request.status in ("Stopped", "Cancelled"):
        frappe.throw(_("An active project and approved purchase requisition are required before closing delivery."))
    notes, proof = strip_html(doc.get(role + "_notes") or "").strip(), doc.get(role + "_proof")
    if not notes or len(notes) > 20000 or not proof:
        frappe.throw(_("Attach delivery proof and enter notes (up to 20,000 characters)."))
    if not frappe.db.exists("File", {"file_url": proof, "attached_to_doctype": DT,
            "attached_to_name": doc.name, "is_private": 1}):
        frappe.throw(_("Upload a private document or image to this Delivery Request as proof."))
    from bsgroup.project_daily_work import capture
    receipt = capture(project, task, notes, "delivery-" + doc.name + "-" + role, status_transition=True, check_labor=False)
    task.reload()
    with writing():
        doc.set(role + "_completed_on", now_datetime())
        both = bool(doc.coordinator_completed_on and doc.delivery_completed_on)
        doc.status = "Completed" if both else "Awaiting delivery person" if role == "coordinator" else "Awaiting coordinator"
        if both:
            doc.update(dict(completed_by=user, completed_on=now_datetime()))
        doc.save(ignore_permissions=True)
        if both:
            task.update(dict(status="Completed", progress=100, custom_bs_status_reason="Coordinator and delivery person both completed their work with proof and notes."))
            task.save(ignore_permissions=True)
        project.reload()
        statuses = frappe.get_all("Task", filters={"project": project.name, "is_template": 0}, pluck="status")
        if both and statuses and all(s in ("Completed", "Closed") for s in statuses):
            project.status = "Completed"
            project.percent_complete = 100
            project.save(ignore_permissions=True)
        project.add_comment("Info", "Delivery " + role + " work submitted by " + escape(user) + ". Request: " + escape(doc.name) + "<br>" + escape(notes))
    return {"name": doc.name, "status": doc.status, "timesheet": receipt["timesheet"]}


def plan_details(task):
    if not task.get("custom_bs_delivery_pr"):
        return {}
    return dict(can_change_status=False, delivery_managed=True, delivery_coordinator=task.get("custom_bs_delivery_coordinator"),
        delivery_person=task.get("custom_bs_delivery_person"), delivery_request=frappe.db.get_value(DT, {"task": task.name}, "name"))


def install():
    frappe.reload_doc("bs_group", "doctype", "delivery_request", force=True)
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Task": [dict(fieldname="custom_bs_delivery_pr", label="Delivery Purchase Requisition",
        fieldtype="Link", options="Material Request", read_only=1, hidden=1, no_copy=1),
        dict(fieldname="custom_bs_delivery_coordinator", label="Delivery Coordinator", fieldtype="Link", options="User", read_only=1, no_copy=1),
        dict(fieldname="custom_bs_delivery_person", label="Delivery Person", fieldtype="Link", options="User", read_only=1, no_copy=1)]}, update=False)
    for doctype in ("Sidebar", "Workspace Sidebar", "Custom Sidebar"):
        if not frappe.db.exists("DocType", doctype):
            continue
        for name in frappe.get_all(doctype, pluck="name"):
            nav = frappe.get_doc(doctype, name)
            table = "sidebar_items" if doctype == "Custom Sidebar" else "items"
            rows = nav.get(table) or []
            survey = next((r for r in rows if r.link_to == "Site Survey Request"), None)
            if not survey:
                continue
            row = next((r for r in rows if r.link_to == DT), None)
            if row and rows.index(row) == rows.index(survey) + 1:
                continue
            if not row:
                row = nav.append(table, dict(type="Link", label=DT, link_type="DocType", link_to=DT,
                    icon="truck", child=survey.child or 0, indent=survey.indent or 0, added=0))
            rows.remove(row)
            rows.insert(rows.index(survey) + 1, row)
            for idx, entry in enumerate(rows, 1):
                entry.idx = idx
            previous = frappe.flags.in_migrate
            try:
                frappe.flags.in_migrate = True
                nav.save(ignore_permissions=True)
            finally:
                frappe.flags.in_migrate = previous


def configure_hooks(hooks):
    hooks.setdefault("after_migrate", []).append("bsgroup.supply_delivery.install")
    hooks.setdefault("permission_query_conditions", {})[DT] = "bsgroup.supply_delivery.query"
    hooks.setdefault("has_permission", {})[DT] = "bsgroup.supply_delivery.permission"
    hooks.setdefault("scheduler_events", {}).setdefault("cron", {}).setdefault("*/5 * * * *", []).append("bsgroup.supply_delivery.reconcile")
    for dt, events in {"Task": {"before_validate": "protect_task", "on_update": "changed"},
                       "ToDo": {"validate": "protect_assignment", "on_trash": "protect_assignment", "on_update": "changed", "after_delete": "changed"},
                       "Material Request": {"on_update": "changed", "on_update_after_submit": "changed", "on_cancel": "changed"},
                       "File": {"on_trash": "protect_evidence"},
                       DT: {"validate": "validate"}}.items():
        target = hooks.setdefault("doc_events", {}).setdefault(dt, {})
        for event, function in events.items():
            prior = target.get(event, [])
            target[event] = ([prior] if isinstance(prior, str) else list(prior)) + ["bsgroup.supply_delivery." + function]
