import frappe
from frappe.model.document import Document
from bsgroup.project_ai_plan import _writing


class BSProjectPlanRun(Document):
    def validate(self):
        if not _writing.get():
            frappe.throw("Automatic planning records are managed by the sales handover service.", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Retain the automatic planning audit record.", frappe.PermissionError)
