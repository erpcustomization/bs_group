import frappe
from erpnext.crm.doctype.opportunity.opportunity import make_quotation as _make_quotation


@frappe.whitelist()
def make_quotation(source_name, target_doc=None):
	quotation = _make_quotation(source_name, target_doc)

	opportunity = frappe.db.get_value(
		"Opportunity",
		source_name,
		["opportunity_from", "custom_contact_person_name", "custom_organization_name"],
		as_dict=True,
	)

	if opportunity:
		display_name = opportunity.custom_contact_person_name or ""
		quotation.custom_contact_person_name = display_name
		quotation.custom_organization_name = opportunity.custom_organization_name or ""
		if opportunity.opportunity_from == "Lead" and display_name:
			quotation.customer_name = display_name

	return quotation
