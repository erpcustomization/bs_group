"""Display-name upgrade; stable app IDs, routes and permissions are preserved."""
import frappe


def install():
    for doctype, fields in (
        ('Desktop Icon', {'label': 'BS Project Support'}),
        ('Workspace Sidebar', {'title': 'BS Project Support'}),
        ('Workspace', {'label': 'BS Project Support', 'title': 'BS Project Support'}),
    ):
        if frappe.db.exists('DocType', doctype) and frappe.db.exists(doctype, 'BS Project'):
            values = {key: value for key, value in fields.items() if frappe.get_meta(doctype).has_field(key)}
            if values:
                frappe.db.set_value(doctype, 'BS Project', values, update_modified=False)
    if frappe.db.exists('DocType', 'Sidebar') and frappe.db.exists('Sidebar', 'BS Group'):
        sidebar = frappe.get_doc('Sidebar', 'BS Group')
        for row in sidebar.items:
            if row.type == 'Section Break' and row.label == 'BS Project':
                frappe.db.set_value(row.doctype, row.name, 'label', 'BS Project Support', update_modified=False)
    frappe.clear_cache()
