"""Operational dates for quotation BOQ lines, governed by native Project access."""
from contextlib import contextmanager
from contextvars import ContextVar

import frappe
from frappe import _
from frappe.utils import getdate, strip_html

FIELD = "custom_bs_boq_schedule"
CHILD = "BS Project BOQ Line"
SOURCE_FIELDS = ("source_quotation", "source_item", "item_code", "item_name", "description", "qty", "uom")
_importing = ContextVar("project_boq_importing", default=False)


@contextmanager
def importing():
    token = _importing.set(True)
    try:
        yield
    finally:
        _importing.reset(token)


def install():
    if not frappe.db.exists("DocType", "Project"):
        return
    frappe.reload_doc("bs_group", "doctype", "bs_project_boq_line", force=True)
    existing = frappe.get_meta("Project").get_field(FIELD)
    if existing and (existing.fieldtype != "Table" or existing.options != CHILD):
        frappe.throw(_("The project BOQ schedule field has an incompatible configuration."))
    if not existing:
        from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
        create_custom_fields({"Project": [dict(fieldname=FIELD, label="BOQ Line Schedule",
            fieldtype="Table", options=CHILD, insert_after="custom_boq", no_copy=1,
            description="Set a start and end date for each quotation BOQ line. Save the project to keep your changes.")]}, update=False)
    frappe.clear_cache(doctype="Project")


@frappe.whitelist(methods=["POST"])
def setup():
    frappe.only_for("System Manager")
    install()
    return {"installed": True}


def append_quotation(project, quotation):
    if not frappe.get_meta("Project").has_field(FIELD):
        frappe.throw(_("Install the BOQ line schedule before sending this handover."))
    existing = {(row.source_quotation, row.source_item) for row in project.get(FIELD) or []}
    for line in quotation.items:
        key = (quotation.name, line.name)
        if key in existing:
            continue  # Preserve previously planned dates if the same source is encountered again.
        project.append(FIELD, dict(source_quotation=quotation.name, source_item=line.name,
            item_code=line.get("item_code"), item_name=line.get("item_name"),
            description=strip_html(line.get("description") or ""), qty=line.qty, uom=line.get("uom")))
        existing.add(key)


def validate(doc, method=None):
    rows = doc.get(FIELD) or []
    for row in rows:
        if row.start_date and row.end_date and getdate(row.end_date) < getdate(row.start_date):
            frappe.throw(_("BOQ row {0}: End Date cannot be before Start Date.").format(row.idx))
    if _importing.get():
        return
    old = doc.get_doc_before_save()
    before = {r.name: r for r in (old.get(FIELD) or [])} if old else {}
    current = {r.name: r for r in rows}
    for name, original in before.items():
        updated = current.get(name)
        if not updated or any(original.get(key) != updated.get(key) for key in SOURCE_FIELDS):
            frappe.throw(_("Quotation BOQ details are managed by the sales handover. Only the line schedule dates can be edited here."))
    if any(row.name not in before for row in rows):
        frappe.throw(_("BOQ schedule lines are added automatically when Sales sends the quotation to Procurement."))
