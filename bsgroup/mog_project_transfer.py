"""Audited, explicitly scoped MOG Salalah UAE -> Oman transfer tooling."""
import hashlib
import json

import frappe

SOURCE = 'PROJ-0008'
TITLE = 'MOG Salalah 7B ELV & Network Project'
AE = {'erp.bitssecureit.com', 'erp-bitssecureit.u.frappe.cloud'}
OM = {'erp-om.bitssecureit.com', 'erp-om.k.frappe.cloud'}


def require_site(sites):
    frappe.only_for('System Manager')
    if frappe.local.site not in sites:
        frappe.throw('This transfer operation is not enabled on this site.')


def digest(value):
    return hashlib.sha256(frappe.as_json(value).encode()).hexdigest()


def source_records():
    project = frappe.get_doc('Project', SOURCE).as_dict()
    if project.project_name != TITLE:
        frappe.throw('Source project identity does not match.')
    tasks = [frappe.get_doc('Task', n).as_dict() for n in frappe.get_all(
        'Task', filters={'project': SOURCE}, pluck='name', order_by='name', limit_page_length=0)]
    roots = {'Project': [SOURCE], 'Task': [t.name for t in tasks]}
    linked = {}
    # Discover ordinary and custom Link fields, including child-table links.
    fields = frappe.get_all('DocField', filters={'fieldtype': 'Link', 'options': ['in', list(roots)]},
                            fields=['parent', 'fieldname', 'options'], limit_page_length=0)
    fields += [frappe._dict(parent=f.dt, fieldname=f.fieldname, options=f.options) for f in
               frappe.get_all('Custom Field', filters={'fieldtype': 'Link', 'options': ['in', list(roots)]},
                              fields=['dt', 'fieldname', 'options'], limit_page_length=0)]
    for f in fields:
        if f.parent in roots or not frappe.db.table_exists(f.parent):
            continue
        meta = frappe.get_meta(f.parent)
        if meta.issingle or getattr(meta, 'is_virtual', False):
            continue
        for row in frappe.get_all(f.parent, filters={f.fieldname: ['in', roots[f.options]]},
                                 fields=['name', 'parent', 'parenttype'] if meta.istable else ['name'],
                                 limit_page_length=0):
            dt, name = (row.parenttype, row.parent) if meta.istable else (f.parent, row.name)
            if dt in roots or not name or not frappe.db.exists(dt, name):
                continue
            linked[(dt, name)] = frappe.get_doc(dt, name).as_dict()
    # Dynamic references used by project requests, labour approvals and work records.
    dynamic = [('ToDo','reference_type','reference_name'),('Labor Preapproval','source','reference'),
               ('Scheduler Execution','reference_doctype','reference_name')]
    for dt, type_field, name_field in dynamic:
        if not frappe.db.exists('DocType', dt):
            continue
        meta = frappe.get_meta(dt)
        if not all(meta.has_field(f) for f in (type_field,name_field)):
            continue
        for target, names in roots.items():
            for name in frappe.get_all(dt, filters={type_field:target,name_field:['in',names]},
                                      pluck='name', limit_page_length=0):
                linked[(dt,name)] = frappe.get_doc(dt,name).as_dict()
    records = [project] + tasks + list(linked.values())
    refs = {}
    for record in records:
        refs.setdefault(record.doctype, []).append(record.name)
    history = {}
    for dt, type_field, name_field in [('Comment','reference_doctype','reference_name'),
            ('Version','ref_doctype','docname'),('Communication','reference_doctype','reference_name'),
            ('File','attached_to_doctype','attached_to_name'),('DocShare','share_doctype','share_name')]:
        for target,names in refs.items():
            for name in frappe.get_all(dt,filters={type_field:target,name_field:['in',names]},
                                      pluck='name',limit_page_length=0):
                history[(dt,name)] = frappe.get_doc(dt,name).as_dict()
    return records + list(history.values())


@frappe.whitelist(methods=['GET'])
def inventory():
    require_site(AE)
    records = source_records()
    counts = {}
    for doc in records:
        counts[doc.doctype] = counts.get(doc.doctype,0)+1
    return dict(source=SOURCE, title=TITLE, counts=counts, fingerprint=digest(records),
                related=[dict(doctype=d.doctype,name=d.name,docstatus=d.docstatus)
                         for d in records if d.doctype not in ('Task','Comment','Version','DocShare')])
