import frappe
from frappe.model.document import Document


class BSProjectScheduleSettings(Document):
    def validate(self):
        from bsgroup.project_schedule import validate_endpoint
        if self.enabled:
            if not self.start_date or not self.private_delivery_verified:
                frappe.throw('Set a start date and verify private Teams delivery before enabling.')
            validate_endpoint(self.get_password('individual_webhook'))
