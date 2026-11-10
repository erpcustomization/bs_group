"""Project copy of an awarded quotation: operational scope only, never commercial values.

Called inside the existing locked procurement transaction, after source authorisation.
Direct calls retain native Project permissions. A checked sales handover may
write only its linked project's BOQ; mandatory-field and company checks apply.
"""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from html import escape

import frappe
from frappe import _
from frappe.utils import getdate, strip_html
from bsgroup.project_modules import MODULES


_sales_handover = ContextVar("sales_project_handover", default=None)


def _source_key(q, sheet):
    return (q.name, sheet.name, sheet.company, sheet.get("project"))


@contextmanager
def sales_handover(q, sheet):
    """Authorise only the linked project's BOQ step inside a checked sales send.

    Callers must first validate the current quotation/award. No general Project
    role, document share or approval permission is granted to the sender.
    """
    from bsgroup.dcs.sales_handover_access import AWARD_ROLES
    if frappe.session.user != "Administrator" and not set(frappe.get_roles()) & AWARD_ROLES:
        frappe.throw(_("Sales handover access is required."), frappe.PermissionError)
    q.check_permission("write")
    sheet.check_permission("write")
    if q.get("custom_deal_cost_sheet") != sheet.name or q.company != sheet.company:
        frappe.throw(_("The project handover must use the quotation's linked costing sheet and company."))
    token = _sales_handover.set(_source_key(q, sheet))
    try:
        yield
    finally:
        _sales_handover.reset(token)


def _scoped_handover(q, sheet):
    return _sales_handover.get() == _source_key(q, sheet)


def selections(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            value = None
    if not isinstance(value, list) or not value or any(not isinstance(k, str) or k not in MODULES for k in value):
        frappe.throw(_("Choose at least one valid project module."))
    return list(dict.fromkeys(value))


def boq_html(quotation):
    """Explicit field allowlist; no prices, totals, discounts, taxes or priced files."""
    e = lambda value: escape(str(value if value is not None else ""))
    rows = []
    for row in quotation.items:
        rows.append("<tr>" + "".join("<td>" + e(value) + "</td>" for value in (
            row.get("item_code"), row.get("item_name"), strip_html(row.get("description") or ""),
            row.get("qty"), row.get("uom"))) + "</tr>")
    if not rows:
        frappe.throw(_("The quotation has no BOQ items to send to the project."))
    return ("<h3>Quotation BOQ: " + e(quotation.name) + "</h3>"
            "<table><thead><tr><th>Item</th><th>Item Name</th><th>Description</th>"
            "<th>Quantity</th><th>UOM</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>")


def context(q, sheet):
    project = sheet.get("project")
    selected = []
    if project:
        doc = frappe.get_doc("Project", project)
        if not _scoped_handover(q, sheet):
            doc.check_permission("read")
        if doc.company != sheet.company:
            frappe.throw(_("The linked project must belong to the quotation company."))
        selected = [key for key, (_, field) in MODULES.items() if doc.get(field)]
    return dict(project=project, project_modules=selected,
                project_customer=q.party_name if q.quotation_to == "Customer" else sheet.get("customer"),
                project_description=sheet.get("subject") or "")


def save_project(q, sheet, modules, details=None):
    scoped = _scoped_handover(q, sheet)
    selected = selections(modules)
    if isinstance(details, str):
        details = json.loads(details)
    details = details or {}
    if not isinstance(details, dict):
        frappe.throw(_("Invalid project details."))
    meta = frappe.get_meta("Project")
    if any(not meta.has_field(field) for _, field in MODULES.values()) or not meta.has_field("custom_boq"):
        frappe.throw(_("Install the project modules before sending this handover."))
    scope = boq_html(q)
    if sheet.get("project"):
        project = frappe.get_doc("Project", sheet.project, for_update=True)
        if not scoped:
            project.check_permission("write")
        if project.company != sheet.company:
            frappe.throw(_("The linked project must belong to the quotation company."))
        if project.status in ("Completed", "Cancelled"):
            frappe.throw(_("The linked project is closed. Resolve the project link before handover."))
    else:
        project = frappe.new_doc("Project")
        if not scoped:
            project.check_permission("create")
        required = ("project_type", "custom_project_manager", "expected_start_date", "expected_end_date")
        if any(not details.get(field) for field in required):
            frappe.throw(_("Complete the project type, project manager and start/end dates."))
        if getdate(details["expected_end_date"]) < getdate(details["expected_start_date"]):
            frappe.throw(_("Project end date cannot be before its start date."))
        project.update({field: details[field] for field in required})
        project.update(dict(project_name=(sheet.get("subject") or "Project") + " - " + q.name,
            company=sheet.company, status="Open",
            customer=q.party_name if q.quotation_to == "Customer" else sheet.get("customer") or details.get("customer"),
            custom_project_description=details.get("custom_project_description") or sheet.get("subject")))
        if details.get("project_template"):
            project.project_template = details["project_template"]
    # Add memberships; never clear another module or overwrite existing scope.
    for key in selected:
        project.set(MODULES[key][1], 1)
    project.custom_boq = (project.get("custom_boq") or "") + scope
    from bsgroup.project_boq_schedule import append_quotation, importing
    append_quotation(project, q)
    with importing():
        if scoped:
            project.save(ignore_permissions=True)
        else:
            project.save()
    return project.name
