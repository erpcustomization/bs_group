"""Apply the authorised designated-approver change to the test site only."""
import json
import frappe
from bsgroup.procurement_controls import PROCUREMENT_APPROVER, APPROVER_ROLE

frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
assert frappe.local.site == "rel1-test.local"
try:
    from bsgroup.procurement_setup import (
        install_approver_role, scope_request_transitions, route_pending_request_actions,
    )
    user = frappe.get_doc("User", PROCUREMENT_APPROVER)
    assert user.full_name == "Mohan Babu" and user.user_type == "System User"
    assert {"Purchase User", "Purchase Manager"}.issubset(r.role for r in user.roles)
    was_enabled = bool(user.enabled)
    if not user.enabled:
        user.enabled = 1
        user.send_welcome_email = 0
        user.save()
    install_approver_role()
    scope_request_transitions()
    route_pending_request_actions()
    workflow = frappe.get_doc("Workflow", "Material Request Approval")
    scoped = [r for r in workflow.transitions if r.allowed == APPROVER_ROLE]
    assert {r.action for r in scoped} == {"Approve", "Reject"}
    assert all(r.allow_self_approval and r.condition == "doc.custom_bsp_managed" for r in scoped)
    frappe.db.commit()
    frappe.clear_cache()
    print(json.dumps(dict(site=frappe.local.site, approver=PROCUREMENT_APPROVER,
                          name=user.full_name, was_enabled=was_enabled, enabled=True,
                          dedicated_role=APPROVER_ROLE, self_initiated_approval=True), indent=2))
except Exception:
    frappe.db.rollback()
    raise
finally:
    frappe.destroy()
