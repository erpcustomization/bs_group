"""Labour decisions use the native workflow, with Mohan as the named approver."""
import frappe
from frappe.utils import get_datetime
from bsgroup.dcs.manager_approval import FIXED_APPROVER


def guard_decision(doc, method=None):
    if doc.workflow_state in ("Approved", "Rejected") and doc.has_value_changed("workflow_state"):
        if frappe.session.user != FIXED_APPROVER:
            frappe.throw("Labour requests must be approved or rejected by Mohan.", frappe.PermissionError)


def load(name, lock=False):
    from bsgroup.approval_requests import require_mohan
    require_mohan()
    doc = frappe.get_doc("Labor Preapproval", name, for_update=lock)
    doc.check_permission("read")
    from bsgroup.procurement_lists import visible_company_names
    if not visible_company_names(doc.doctype, [doc.name]):
        frappe.throw("This labour request is outside your company access.", frappe.PermissionError)
    if doc.docstatus != 0 or doc.workflow_state != "Pending Approval":
        frappe.throw("This labour request is no longer pending approval. Refresh the inbox.")
    return doc


def review(name):
    from frappe.model.workflow import get_transitions
    doc = load(name)
    return dict(kind="labour", name=doc.name, modified=str(doc.modified), source=doc.source,
        reference=doc.reference, task=doc.task, company=doc.company,
        currency=frappe.get_cached_value("Company", doc.company, "default_currency"),
        total=doc.total_labor_cost, person_days=doc.approved_person_days,
        actions=[r.action for r in get_transitions(doc) if r.action in ("Approve", "Reject")],
        items=[dict(skill=r.role__skill, persons=r.no_of_persons, days=r.days,
                    rate=r.rate, total=r.total_cost) for r in doc.labor_line_items])


def decide(name, modified, action, reason):
    if action not in ("Approve", "Reject"):
        frappe.throw("Labour requests support Approve or Reject.")
    if action == "Reject" and not str(reason or "").strip():
        frappe.throw("Enter a reason for rejection.")
    doc = load(name, lock=True)
    if not modified or get_datetime(modified) != get_datetime(doc.modified):
        frappe.throw("This labour request changed after you opened it. Refresh and review it again.", frappe.TimestampMismatchError)
    from frappe.model.workflow import apply_workflow
    result = apply_workflow(doc.as_dict(), action)
    if reason:
        result.add_comment("Comment", frappe.utils.escape_html(str(reason)))
    return dict(saved=True, state=result.workflow_state)


def install():
    """Narrow native approval transitions; preserve roles and all existing decisions."""
    for name in frappe.get_all("Workflow", filters={"document_type":"Labor Preapproval", "is_active":1}, pluck="name"):
        workflow = frappe.get_doc("Workflow", name)
        changed = False
        condition = 'frappe.session.user == "mohan@bitssecureit.com"'
        for row in workflow.transitions:
            if row.state == "Pending Approval" and row.next_state in ("Approved", "Rejected"):
                if condition not in (row.condition or ""):
                    row.condition = f"({row.condition}) and ({condition})" if row.condition else condition
                    changed = True
        if changed:
            workflow.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Labor Preapproval")
