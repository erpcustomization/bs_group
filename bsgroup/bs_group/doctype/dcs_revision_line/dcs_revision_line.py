import frappe
from frappe.model.document import Document


class DCSRevisionLine(Document):
    def validate(self):
        # Parent revision insertion uses db_insert on its children; standalone
        # child insert/save APIs must not forge or edit recorded line history.
        frappe.throw("BOQ history can only be recorded through its parent revision service; standalone writes are forbidden.")

    def on_trash(self):
        frappe.throw("BOQ revision line history is append-only and cannot be deleted.")
