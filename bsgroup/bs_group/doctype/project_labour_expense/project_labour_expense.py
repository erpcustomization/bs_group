import frappe
from frappe.model.document import Document

class ProjectLabourExpense(Document):
    def validate(self):
        if not self.flags.bs_daily_labor:
            frappe.throw("Record or correct daily labour through the Project Plan work dialog.")
    def on_trash(self):
        frappe.throw("Recorded labour expenses cannot be deleted. Retain the audit history.")
