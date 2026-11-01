"""Only approved server workflows may insert a Deal Cost Sheet."""
from contextvars import ContextVar
import frappe
from frappe import _

_allowed_sheet = ContextVar("workflow_dcs", default=None)


def insert_from_workflow(sheet):
    token = _allowed_sheet.set(sheet)
    try:
        return sheet.insert(ignore_permissions=True)
    finally:
        _allowed_sheet.reset(token)


def guard_creation(doc):
    if _allowed_sheet.get() is not doc:
        frappe.throw(_("Deal Cost Sheets are created automatically from the Opportunity or submitted Presales Request. Manual creation and duplication are not allowed."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def install():
    if frappe.session.user != "Administrator":
        frappe.throw("Only Administrator can configure DCS creation permissions.", frappe.PermissionError)
    for dt in ("DocPerm", "Custom DocPerm"):
        for row in frappe.get_all(dt, filters={"parent":"Deal Cost Sheet"}, pluck="name"):
            frappe.db.set_value(dt, row, {"create":0,"import":0})
    frappe.db.set_value("DocType", "Deal Cost Sheet", "allow_import", 0)
    frappe.clear_cache()
    return {"manual_creation": False}