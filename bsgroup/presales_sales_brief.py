"""Read-only sales brief, resolved through a readable Presales Request."""
import frappe
from frappe.utils import getdate

SALES_FIELDS = (
    'opportunity', 'party_type', 'party', 'organisation_name', 'customer',
    'is_new_customer', 'subject', 'company', 'estimated_value', 'requested_by',
    'request_date', 'expected_close_date', 'custom_service_details',
    'decision_maker_known', 'competition_known', 'budget_confirmed', 'timeline_defined',
)
SOURCE_FIELDS = (
    'custom_subject', 'custom_business_type', 'custom_service_type',
    'custom_installation_type', 'custom_camera_count', 'custom_presales_support',
    'custom_service_survey', 'custom_service_details', 'custom_survey_instructions',
    'custom_survey_location', 'custom_survey_contact_name', 'custom_survey_contact_phone',
    'opportunity_amount', 'currency', 'expected_closing', 'contact_display',
    'contact_email', 'contact_mobile', 'contact_phone',
)


def sales_field_value(field, value):
    # Browser JSON supplies dates as strings; database documents use date objects.
    # Empty dates must stay empty (getdate(None) would otherwise mean today).
    if field in ('request_date', 'expected_close_date'):
        return getdate(value) if value not in (None, '') else None
    return value


def protect_sales_fields(doc):
    if doc.is_new():
        return
    roles = set(frappe.get_roles())
    if not roles.intersection({'Presales', 'BS Scoped Presales'}) or 'System Manager' in roles:
        return
    before = doc.get_doc_before_save()
    if not before:
        before = frappe.get_doc(doc.doctype, doc.name)
    changed = [f for f in SALES_FIELDS
               if sales_field_value(f, doc.get(f)) != sales_field_value(f, before.get(f))]
    if changed:
        frappe.throw('Sales request details are read-only for Presales. Ask Sales to correct the source Opportunity.', frappe.PermissionError)


@frappe.whitelist()
def get_brief(name):
    request = frappe.get_doc('Presales Request', name)
    request.check_permission('read')
    if not request.opportunity:
        return {'requirement': '', 'details': [], 'items': [], 'files': []}
    opportunity = frappe.get_doc('Opportunity', request.opportunity)
    if opportunity.company != request.company:
        frappe.throw('The source Opportunity belongs to a different company.', frappe.PermissionError)
    details = []
    for field in SOURCE_FIELDS:
        value = opportunity.get(field)
        if value not in (None, '', 0, 0.0):
            details.append({'label': opportunity.meta.get_label(field) or field, 'value': str(value)})
    items = [{f: row.get(f) for f in ('item_code', 'item_name', 'description', 'qty', 'uom', 'rate', 'amount')}
             for row in opportunity.get('items') or []]
    from bsgroup.opportunity_attachments import files
    return {'opportunity': opportunity.name, 'requirement': opportunity.get('custom_enquiry') or '',
            'details': details, 'items': items, 'files': files('Presales Request', name)}
