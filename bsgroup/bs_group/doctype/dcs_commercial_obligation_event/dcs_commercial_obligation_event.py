from frappe.model.document import Document
from bsgroup.dcs.obligation import guard_write, guard_delete

class DCSCommercialObligationEvent(Document):
    def validate(self):
        guard_write(self)

    def on_trash(self):
        guard_delete(self)
