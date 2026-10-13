"""Immediate-manager approval routing. Reporting lines are snapshotted per revision."""
import frappe
from html import escape
from urllib.parse import quote

ROUTE_FIELDS = ["approval_policy", "submitter_employee", "manager_employee",
                "approval_manager", "approval_routing_error", "manager_dcs_share"]
FINAL_STATES = ("Approved", "Rejected", "Returned for Rework", "Not Required")

def resolve_manager(user):
    out = {"approval_policy": "Immediate Manager", "approval_manager": "",
           "submitter_employee": "", "manager_employee": "", "approval_routing_error": ""}
    employees = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"},
                               fields=["name", "reports_to"], limit_page_length=2)
    if len(employees) != 1:
        out["approval_routing_error"] = "The submitter must have exactly one active Employee linked to their user."
        return out
    employee = employees[0]
    out["submitter_employee"] = employee.name
    if not employee.reports_to or employee.reports_to == employee.name:
        out["approval_routing_error"] = "Set a distinct immediate manager in the submitter's Employee Reports To field."
        return out
    manager = frappe.db.get_value("Employee", employee.reports_to, ["name", "user_id", "status"], as_dict=True)
    if not manager or manager.status != "Active" or not manager.user_id:
        out["approval_routing_error"] = "The immediate manager must be an active Employee with a linked user."
        return out
    if manager.user_id == user or manager.user_id in ("Administrator", "Guest"):
        out["approval_routing_error"] = "The submitter cannot approve their own revision. Link a distinct manager user."
        return out
    if not frappe.db.get_value("User", manager.user_id, "enabled"):
        out["approval_routing_error"] = "The immediate manager's user is disabled. Update the Employee reporting line."
        return out
    out.update(manager_employee=manager.name, approval_manager=manager.user_id)
    return out

def route_for(sheet):
    if isinstance(sheet, str):
        sheet = frappe.get_doc("Deal Cost Sheet", sheet)
    name = sheet.get("custom_revision_reference")
    if not name:
        return frappe._dict()
    route = frappe.db.get_value("DCS Revision", name,
        ["dcs", "revision_no", "changed_by"] + ROUTE_FIELDS, as_dict=True) or frappe._dict()
    if route.get("dcs") != sheet.name or route.get("revision_no") != sheet.get("custom_dcs_revision_no"):
        return frappe._dict()
    if route.get("approval_manager"):
        route["approval_manager_name"] = frappe.db.get_value("User",route.approval_manager,"full_name") or route.approval_manager
    return route

def is_assigned_manager(sheet, user=None):
    user = user or frappe.session.user
    if user in ("Guest", "Administrator"):
        return False
    route = route_for(sheet)
    return bool(route.get("approval_policy") == "Immediate Manager"
        and route.get("approval_manager") == user and route.get("changed_by") != user
        and not route.get("approval_routing_error")
        and frappe.db.get_value("User", user, "enabled"))

def prepare_revision(revision):
    if revision.approval_requirement in ("Manager", "Blocked"):
        revision.update(resolve_manager(revision.changed_by))

def close_review(revision_name):
    for name in frappe.get_all("ToDo", filters={"reference_type":"DCS Revision",
            "reference_name":revision_name, "status":"Open"}, pluck="name"):
        todo = frappe.get_doc("ToDo", name)
        if not (todo.description or "").startswith("Manager approval: "):
            continue
        todo.status = "Closed"
        todo.save(ignore_permissions=True)

def queue_review(revision):
    """In-app task only; no email and no global role changes."""
    previous = frappe.db.get_value("Deal Cost Sheet", revision.dcs, "custom_revision_reference")
    if previous and previous != revision.name:
        old = frappe.db.get_value("DCS Revision", previous,
            ["approval_policy","approval_manager","manager_dcs_share"], as_dict=True)
        if old and old.approval_policy == "Immediate Manager":
            close_review(previous)
            if old.manager_dcs_share and frappe.db.exists("DocShare", old.manager_dcs_share):
                share = frappe.get_doc("DocShare", old.manager_dcs_share)
                if share.share_doctype == "Deal Cost Sheet" and share.share_name == revision.dcs and share.user == old.approval_manager and share.read and not (share.write or share.share or share.submit):
                    share.flags.ignore_share_permission = True
                    share.delete(ignore_permissions=True)
    if revision.approval_requirement not in ("Manager", "Blocked") or revision.approval_state in FINAL_STATES or not revision.approval_manager:
        return
    user = revision.approval_manager
    if not frappe.has_permission("Deal Cost Sheet", "read", doc=revision.dcs, user=user):
        share = frappe.share.add("Deal Cost Sheet", revision.dcs, user, read=1, write=0, share=0,
                                 notify=0, flags={"ignore_share_permission":True})
        share_name = share.name if hasattr(share, "name") else frappe.db.get_value("DocShare",
            {"share_doctype":"Deal Cost Sheet","share_name":revision.dcs,"user":user}, "name")
        frappe.db.set_value("DCS Revision", revision.name, "manager_dcs_share", share_name, update_modified=False)
    if not frappe.has_permission("DCS Revision","read",doc=revision.name,user=user):
        frappe.share.add("DCS Revision",revision.name,user,read=1,write=0,share=0,notify=0,
                         flags={"ignore_share_permission":True})
    if not frappe.db.exists("ToDo", {"reference_type":"DCS Revision","reference_name":revision.name,
                                     "allocated_to":user,"status":"Open"}):
        frappe.get_doc({"doctype":"ToDo","reference_type":"DCS Revision","reference_name":revision.name,
            "allocated_to":user,"assigned_by":revision.changed_by,"description":\
                'Manager approval: <a href="/desk/deal-cost-sheet/'+quote(revision.dcs,safe="")+'">Review '+escape(revision.dcs)+'</a> · revision '+str(revision.revision_no),
            "status":"Open","priority":"Medium"}).insert(ignore_permissions=True)
        notification = frappe.get_doc({"doctype":"Notification Log","type":"Alert","for_user":user,
            "from_user":revision.changed_by,"subject":"DCS manager approval requested",
            "document_type":"Deal Cost Sheet","document_name":revision.dcs,
            "description":"Review the current commercial position. Approval and delivery release remain separate.",
            "email_content":"Review the current commercial position. Approval and delivery release remain separate."})
        # Trusted in-app log: db_insert deliberately avoids Notification Log.after_insert,
        # which can send email according to each user\'s personal settings.
        notification.db_insert()
        from frappe.desk.doctype.notification_log.notification_log import set_notifications_as_unseen
        set_notifications_as_unseen(user)
        frappe.publish_realtime("notification", after_commit=True, user=user)

from bsgroup.api.dcs._common import governed_endpoint

@governed_endpoint("dcs_refresh_manager_route", ptype="write")
def dcs_refresh_manager_route(args):
    sheet=frappe.get_doc("Deal Cost Sheet",args.get("dcs"),for_update=True)
    sheet.check_permission("write")
    route=route_for(sheet)
    if sheet.docstatus!=1 or sheet.custom_approval_state in ("Approved","Rejected","Returned for Rework") or sheet.custom_approval_required not in ("Manager","Blocked"):
        return {"ok":0,"error":"Only a pending manager approval may be routed."}
    if route.get("changed_by")!=frappe.session.user:
        return {"ok":0,"error":"Only the submitter of the current revision may refresh a missing or disabled manager route."}
    if route.get("approval_manager") and not route.get("approval_routing_error") and frappe.db.get_value("User",route.approval_manager,"enabled"):
        return {"ok":1,"no_change":1,"note":"The current revision already has a valid assigned manager."}
    values=resolve_manager(frappe.session.user)
    if values["approval_routing_error"]:
        return {"ok":0,"error":values["approval_routing_error"]}
    close_review(sheet.custom_revision_reference)
    if route.get("manager_dcs_share") and frappe.db.exists("DocShare",route.manager_dcs_share):
        share=frappe.get_doc("DocShare",route.manager_dcs_share)
        if share.share_doctype=="Deal Cost Sheet" and share.share_name==sheet.name and share.user==route.get("approval_manager") and not (share.write or share.share or share.submit):
            share.flags.ignore_share_permission = True
            share.delete(ignore_permissions=True)
    values["manager_dcs_share"]=""
    frappe.db.set_value("DCS Revision",sheet.custom_revision_reference,values,update_modified=True)
    revision=frappe.get_doc("DCS Revision",sheet.custom_revision_reference)
    revision.approval_requirement=sheet.custom_approval_required
    queue_review(revision)
    from bsgroup.api.dcs._common import audit_event
    event=audit_event(sheet.name,"DCS_MANAGER_ROUTE_REPAIRED","Route pending revision to immediate manager",
        "dcs_refresh_manager_route","Reporting line corrected by the current revision submitter.",
        sheet.custom_dcs_revision_no,sheet.custom_revision_reference,sheet.custom_revision_reference,
        [{"dt":"DCS Revision","dn":sheet.custom_revision_reference,"field":key,"old":route.get(key),"new":value} for key,value in values.items()])
    return {"ok":1,"approval_manager":values["approval_manager"],"governance_event":event}
