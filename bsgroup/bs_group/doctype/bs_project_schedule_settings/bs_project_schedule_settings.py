import frappe
from frappe.model.document import Document


class BSProjectScheduleSettings(Document):
    def validate(self):
        from bsgroup.project_schedule import validate_endpoint
        if self.enabled:
            if not self.start_date or not self.private_delivery_verified:
                frappe.throw('Set a start date and verify private Teams delivery before enabling.')
            validate_endpoint(self.get_password('individual_webhook'))
        from bsgroup.hr_email import site_profile
        for region in ('Oman', 'UAE'):
            prefix = region.lower() + '_group'
            if self.get(prefix + '_enabled'):
                if (site_profile() or {}).get('region') != region or not self.get(prefix + '_verified'):
                    frappe.throw(f'Verify the Projects Team {region} destination on the matching site before enabling group delivery.')
                validate_endpoint(self.get_password(prefix + '_webhook'))
