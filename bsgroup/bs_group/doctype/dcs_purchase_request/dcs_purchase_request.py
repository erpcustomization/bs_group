from frappe.model.document import Document
from bsgroup.dcs.procurement import guard, deny

class DCSPurchaseRequest(Document):
    def before_insert(self):
        guard(self)
    def validate(self):
        guard(self)
    def on_trash(self):
        deny("Purchase requests must be retained for the award history.")
