"""Administrator-only schema synchronization for the existing Oman bench."""
import frappe


@frappe.whitelist(methods=["POST"])
def execute():
    if frappe.session.user != "Administrator":
        frappe.throw("Only Administrator can synchronize this release.", frappe.PermissionError)
    for role in ("BS Scoped Sales", "BS Scoped Presales", "Presales"):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
    from bsgroup.lead_lifecycle import setup as lead_setup
    from bsgroup.site_survey_setup import execute as survey_setup
    from bsgroup.sales_qualification import setup as qualification_setup
    from bsgroup.opportunity_routing_setup import execute as routing_setup
    from bsgroup.presales_duration import setup as duration_setup
    from bsgroup.patches.v0_1.dcs_supplier_evidence import execute as evidence_setup
    from bsgroup.dcs.creation import install as creation_setup
    lead_setup()
    survey_setup()
    qualification_setup()
    routing_setup()
    duration_setup()
    evidence_setup()
    creation_setup()
    frappe.reload_doc("bs_group", "page", "my_work_dashboard")
    frappe.clear_cache()
    return {"status": "ready", "company_data": "preserved", "user_roles": "unchanged"}
