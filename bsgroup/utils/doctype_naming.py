import frappe
import re
from frappe.model.naming import make_autoname

def opportunity_autoname(doc, method=None):
    if doc.party_name and doc.opportunity_from == "Lead":
        if doc.custom_contact_person_name:
            lead_name = re.sub(r'[^a-zA-Z0-9\s]', '', doc.custom_contact_person_name)
            lead_name = re.sub(r'\s+', '-', lead_name.strip())
            doc.name = frappe.model.naming.make_autoname(f"OPP-{lead_name}-.###")
    elif doc.party_name and doc.opportunity_from == "Customer":
        customer_name = re.sub(r'[^a-zA-Z0-9\s]', '', doc.party_name)
        customer_name = re.sub(r'\s+', '-', customer_name.strip())
        doc.name = frappe.model.naming.make_autoname(f"OPP-{customer_name}-.###")

