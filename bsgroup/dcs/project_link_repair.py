"""Audited repair of an unsent quotation's stale link to a closed project."""
from html import escape
from urllib.parse import quote

import frappe


def _unsent_source(quotation, lock=False):
    frappe.only_for("System Manager")
    from bsgroup.dcs.procurement import source_documents
    q, sheet = source_documents(quotation, lock=lock)
    if (q.get("custom_bsp_material_request") or q.get("custom_purchase_request")
            or frappe.db.exists("Material Request", {"custom_deal_cost_sheet": sheet.name})
            or (frappe.db.exists("DocType", "DCS Purchase Request")
                and frappe.db.exists("DCS Purchase Request", {"dcs": sheet.name}))):
        frappe.throw("This deal already has a procurement handover. Its project link cannot be cleared here.")
    return q, sheet


@frappe.whitelist(methods=["POST"])
def clear_closed_project_link(quotation, expected_project):
    """Only changes the exact DCS link; never saves the linked Project or its tasks."""
    from bsgroup.dcs.presales_lineage import atomic_lifecycle

    def apply():
        q, sheet = _unsent_source(quotation, lock=True)
        if not sheet.get("project"):
            return  # Safe retry: no extra audit or changes.
        if not expected_project or sheet.project != expected_project:
            frappe.throw("The project link changed. Refresh and review it before correcting it.")
        project = frappe.get_doc("Project", expected_project, for_update=True)
        project.check_permission("read")
        if project.company != sheet.company or project.status not in ("Completed", "Cancelled"):
            frappe.throw("Only a stale link to a closed project in the same company can be cleared here.")
        from bsgroup.dcs.governance import record_governance_event
        frappe.db.set_value("Deal Cost Sheet", sheet.name, "project", None)
        record_governance_event(sheet.name, "DCS_PROJECT_LINK_CORRECTED",
            action_label="Clear stale project link before first procurement handover",
            source_endpoint="project_link_repair", revision_no=sheet.custom_dcs_revision_no,
            revision_reference=sheet.custom_revision_reference, evidence_reference=q.name,
            reason="Prepare a new project for quotation " + q.name + ". Closed project "
                + expected_project + " and its records remain unchanged.",
            changes=[dict(dt="Deal Cost Sheet", dn=sheet.name, field="project",
                          old=expected_project, new="")])
        q.add_comment("Info", "Cleared the costing sheet's stale link to " + expected_project
            + ". A new project and planning request will be created when this quotation is sent to Procurement.")

    atomic_lifecycle(apply)
    return page(quotation, expected_project)


@frappe.whitelist()
def page(quotation, expected_project):
    q, sheet = _unsent_source(quotation)
    project = frappe.get_doc("Project", expected_project)
    project.check_permission("read")
    from frappe.sessions import get_csrf_token
    e = lambda value: escape(str(value or ""), quote=True)
    cleared = not sheet.get("project")
    action = "" if cleared else f'''<form method="post" action="/api/method/bsgroup.dcs.project_link_repair.clear_closed_project_link">
        <input type="hidden" name="csrf_token" value="{e(get_csrf_token())}">
        <input type="hidden" name="quotation" value="{e(q.name)}">
        <input type="hidden" name="expected_project" value="{e(expected_project)}">
        <button type="submit" class="btn btn-primary">Clear this stale project link</button></form>'''
    body = f'''<h2>{"Ready for a new project" if cleared else "Correct quotation project link"}</h2>
        <p><b>Quotation:</b> {e(q.name)} — {e(q.get("custom_subject"))}</p>
        <p><b>Costing sheet:</b> {e(sheet.name)}</p>
        <p><b>Current project link:</b> {e(sheet.project) if sheet.get("project") else "None — a new project will be created at handover"}</p>
        <p><b>Previous project:</b> {e(project.name)} — {e(project.project_name)}<br>
        Status: {e(project.status)} · Last modified: {e(project.modified)}</p>
        <p>The completed project, its activities and its history are preserved.
        Sending this quotation to Procurement will create a new project, a Purchase Requisition
        and an automatic planning request. Enter its category, manager and expected completion date.</p>
        {action}<p><a href="/desk/quotation/{quote(q.name, safe='')}">Open quotation</a></p>'''
    frappe.respond_as_web_page("Quotation project link", body, indicator_color="green" if cleared else "orange")
