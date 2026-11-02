"""Supporting files shared only through the linked, readable presales request."""
import frappe


def source(doctype, name):
    if frappe.session.user == 'Guest' or doctype not in ('Opportunity', 'Presales Request'):
        frappe.throw('Not permitted.', frappe.PermissionError)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission('read')
    return doc.name if doctype == 'Opportunity' else doc.get('opportunity')


@frappe.whitelist()
def files(doctype, name):
    opportunity = source(doctype, name)
    if not opportunity:
        return []
    return frappe.get_all('File', filters={'attached_to_doctype': 'Opportunity',
        'attached_to_name': opportunity, 'is_folder': 0},
        fields=['name', 'file_name', 'file_size'], order_by='creation asc', limit_page_length=0)


@frappe.whitelist()
def download(doctype, name, file):
    opportunity = source(doctype, name)
    attachment = frappe.get_doc('File', file)
    if not opportunity or attachment.attached_to_doctype != 'Opportunity' or attachment.attached_to_name != opportunity or attachment.is_folder:
        frappe.throw('This file is not attached to the linked Opportunity.', frappe.PermissionError)
    if not (attachment.file_url or '').startswith(('/private/files/', '/files/')):
        frappe.throw('Only uploaded files can be downloaded here.')
    frappe.local.response.update(type='download', filename=attachment.file_name,
        filecontent=attachment.get_content(), display_content_as='attachment')
