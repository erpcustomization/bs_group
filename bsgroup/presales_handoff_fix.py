"""Idempotent repair for reference selection and submitted presales handoffs."""
import frappe


@frappe.whitelist(methods=['POST'])
def install():
    if frappe.session.user != 'Administrator':
        frappe.throw('Administrator required', frappe.PermissionError)
    from frappe.permissions import setup_custom_perms
    setup_custom_perms('Territory')
    for role in ('BS Scoped Sales', 'BS Scoped Presales'):
        name = frappe.db.get_value('Custom DocPerm', {'parent':'Territory', 'role':role, 'permlevel':0})
        rule = frappe.get_doc('Custom DocPerm', name) if name else frappe.get_doc({
            'doctype':'Custom DocPerm', 'parent':'Territory', 'parenttype':'DocType',
            'parentfield':'permissions', 'role':role, 'permlevel':0})
        rule.select = 1
        rule.save()
    frappe.clear_cache(doctype='Territory')
    repaired = []
    for row in frappe.get_all('Presales Request', filters={'docstatus':1, 'status':['in',['Draft','Open','Assigned','In Progress']]}, fields=['name']):
        sheets = frappe.get_all('Deal Cost Sheet', filters={'presales_request':row.name,'docstatus':0}, fields=['custom_record_authority'])
        if any(s.custom_record_authority != 'Superseded' for s in sheets):
            doc = frappe.get_doc('Presales Request', row.name)
            doc.db_set('status', 'Costing in Progress')
            doc.add_comment('Info', 'Status corrected: submitted Presales Request has an active draft Deal Cost Sheet.')
            repaired.append(row.name)
    return {'repaired':repaired, 'territory_select_roles':['BS Scoped Sales','BS Scoped Presales']}
