"""Designated-approver integration tests; all business changes roll back."""
import json
import frappe
from frappe.model.workflow import apply_workflow, get_transitions
from bsgroup.procurement_controls import APPROVER_ROLE, PROCUREMENT_APPROVER, approval_allowed
from test_standard_documents import (
    RESULTS, BUYER, check, blocked, new_request, new_order, payload, action, po_action,
)
from qc_fixtures import MANAGER2, cleanup_files


def run():
    from bsgroup import procurement as p
    from bsgroup.tests.dcs_fixtures import make_user
    from bsgroup.procurement_setup import install_approver_role, scope_request_transitions, route_pending_request_actions
    check("Mohan's real test-site account is enabled",
          frappe.db.get_value("User", PROCUREMENT_APPROVER, "enabled") == 1)
    check("Mohan has the dedicated approval role", APPROVER_ROLE in frappe.get_roles(PROCUREMENT_APPROVER))
    before = frappe.get_doc("Workflow", "Material Request Approval").as_dict()
    install_approver_role()
    scope_request_transitions()
    route_pending_request_actions()
    check("Repeated routing setup leaves workflow unchanged",
          before == frappe.get_doc("Workflow", "Material Request Approval").as_dict())
    make_user(BUYER, ["Purchase User"])
    make_user(MANAGER2, ["Purchase User", "Purchase Manager"])
    for initiator in (BUYER, MANAGER2, "Administrator", PROCUREMENT_APPROVER):
        frappe.set_user(initiator)
        r = new_request(p)
        r = action(p, r, "Send for Approval")
        check("PR identifies Mohan for initiator " + initiator, r["approver"]["user"] == PROCUREMENT_APPROVER)
        queues = frappe.get_all("Workflow Action", filters={
            "reference_doctype": "Material Request", "reference_name": r["id"],
            "workflow_state": "Pending Approval", "status": "Open"}, pluck="name")
        check("PR review is routed exclusively to Mohan's role for " + initiator,
              bool(queues) and all(
                  {x.role for x in frappe.get_doc("Workflow Action", n).permitted_roles} == {APPROVER_ROLE}
                  for n in queues))
        for denied in (BUYER, MANAGER2, "Administrator"):
            frappe.set_user(denied)
            check("PR hides decisions from " + denied + " / " + initiator,
                  not {"Approve", "Reject"}.intersection(p.get_request(r["id"])["actions"]))
            blocked("PR API refuses " + denied + " / " + initiator,
                    lambda: action(p, r, "Approve"), "Only Mohan")
        frappe.set_user(MANAGER2)
        blocked("Native PR workflow refuses another manager / " + initiator,
                lambda: apply_workflow(frappe.get_doc("Material Request", r["id"]), "Approve"))
        frappe.set_user(PROCUREMENT_APPROVER)
        check("Mohan can see PR decisions for " + initiator,
              {"Approve", "Reject"}.issubset(p.get_request(r["id"])["actions"]))
        r = action(p, r, "Reject", "QC revise and resubmit to the same approver")
        frappe.set_user(initiator)
        r = action(p, r, "Send for Approval")
        frappe.set_user(PROCUREMENT_APPROVER)
        r = action(p, r, "Approve")
        check("Mohan approves PR and retains actor for " + initiator,
              r["approval"] == "Approved" and r["history"][-1]["actor"] == PROCUREMENT_APPROVER)
        frappe.set_user(initiator)
        po = new_order(p, r)
        po = p.save_order(po["id"], po["modified"], payload(po))
        po = po_action(p, po, "Send for Approval")
        check("PO identifies Mohan for initiator " + initiator, po["approver"]["user"] == PROCUREMENT_APPROVER)
        for denied in (BUYER, MANAGER2, "Administrator"):
            frappe.set_user(denied)
            check("PO hides decisions from " + denied + " / " + initiator,
                  not p.order_data(frappe.get_doc("Purchase Order", po["id"]))["canApprove"])
            blocked("PO API refuses " + denied + " / " + initiator,
                    lambda: po_action(p, po, "Approve"), "Only Mohan")
        def native_submit():
            d = frappe.get_doc("Purchase Order", po["id"])
            d.custom_bsp_approval_state = "Approved"
            d.submit()
        blocked("Native PO state forgery refuses Administrator / " + initiator, native_submit, "Only Mohan")
        frappe.set_user(PROCUREMENT_APPROVER)
        check("Mohan can see PO decisions for " + initiator,
              p.order_data(frappe.get_doc("Purchase Order", po["id"]))["canApprove"])
        po = po_action(p, po, "Reject", "QC revise commercial terms")
        frappe.set_user(initiator)
        po = p.save_order(po["id"], po["modified"], payload(po, 85))
        po = po_action(p, po, "Send for Approval")
        frappe.set_user(PROCUREMENT_APPROVER)
        po = po_action(p, po, "Approve")
        check("Mohan approves PO and retains actor for " + initiator,
              po["docstatus"] == 1 and po["history"][-1]["actor"] == PROCUREMENT_APPROVER)
    # A role accidentally granted to someone else cannot override fixed identity.
    frappe.set_user("Administrator")
    make_user(MANAGER2, ["Purchase User", "Purchase Manager", APPROVER_ROLE])
    frappe.set_user(MANAGER2)
    managed = frappe.get_doc("Purchase Order", po["id"])
    blocked("Dedicated role alone does not allow another user to decide",
            lambda: approval_allowed(managed, throw=True), "Only Mohan")
    # Invoice separation remains in force even for Mohan.
    frappe.set_user(PROCUREMENT_APPROVER)
    invoice = frappe.new_doc("Purchase Invoice")
    invoice.owner = PROCUREMENT_APPROVER
    invoice.custom_bsp_managed = 1
    blocked("Mohan cannot approve his own supplier invoice",
            lambda: approval_allowed(invoice, throw=True), "different authorised")
    frappe.set_user(MANAGER2)
    plain = frappe.get_doc(dict(doctype="Material Request", name="QC-only-unsaved", owner=BUYER,
                               workflow_state="Pending Approval", custom_bsp_managed=0))
    # Evaluate the ordinary workflow without inserting a business record.
    from frappe.model.workflow import is_transition_condition_satisfied
    ordinary = [t for t in frappe.get_doc("Workflow", "Material Request Approval").transitions
                if t.action in ("Approve", "Reject") and is_transition_condition_satisfied(t, plain)]
    check("Ordinary MR still uses Purchase Manager without self approval",
          len(ordinary) == 2 and all(t.allowed == "Purchase Manager" and not t.allow_self_approval for t in ordinary))
    print(json.dumps(dict(passed=len(RESULTS), tests=RESULTS), indent=2), flush=True)


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    try:
        run()
    finally:
        frappe.db.rollback()
        cleanup_files()
        frappe.clear_cache(user=MANAGER2)
        frappe.clear_cache(user=PROCUREMENT_APPROVER)
        frappe.destroy()
