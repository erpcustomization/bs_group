"""Administrator-only, backed-up cleanup through normal document lifecycle checks."""
import base64
import json
from collections import Counter
import frappe

ALLOWED = {'Lead', 'Opportunity', 'Deal Cost Sheet', 'Quotation', 'Presales Request',
           'Site Survey Request', 'Material Request', 'DCS Purchase Request'}
SYSTEM_REFERENCES = {'Comment', 'Communication', 'Version', 'ToDo', 'DocShare',
                     'File', 'Activity Log', 'Notification Log', 'View Log',
                     'Document Follow', 'Energy Point Log'}


def admin():
    if frappe.session.user != 'Administrator':
        frappe.throw('Only Administrator can run reviewed test cleanup.', frappe.PermissionError)


def incoming(targets):
    """Include standard/custom fields, child rows and Dynamic Links."""
    fields = frappe.get_all('DocField', filters={'fieldtype':['in',['Link','Dynamic Link']]},
                            fields=['parent','fieldname','fieldtype','options'])
    for f in frappe.get_all('Custom Field', filters={'fieldtype':['in',['Link','Dynamic Link']]},
                            fields=['dt','fieldname','fieldtype','options']):
        f.parent = f.dt
        fields.append(f)
    found = []
    seen = set()
    for f in fields:
        if (f.parent, f.fieldname) in seen or f.parent in SYSTEM_REFERENCES:
            continue
        seen.add((f.parent, f.fieldname))
        if f.fieldtype == 'Link' and f.options not in targets:
            continue
        meta = frappe.get_meta(f.parent)
        if meta.issingle or meta.is_virtual or not frappe.db.table_exists(f.parent):
            continue
        if f.fieldtype == 'Dynamic Link' and not meta.has_field(f.options):
            continue
        for dt in ([f.options] if f.fieldtype == 'Link' else targets):
            if not targets[dt]:
                continue
            filters = {f.fieldname:['in',targets[dt]]}
            if f.fieldtype == 'Dynamic Link':
                filters[f.options] = dt
            selected = ['name', f.fieldname] + (['parent','parenttype'] if meta.istable else [])
            for r in frappe.get_all(f.parent, filters=filters, fields=selected, limit_page_length=0):
                source = [r.parenttype,r.parent] if meta.istable else [f.parent,r.name]
                found.append(dict(source=source,target=[dt,r.get(f.fieldname)],field=f.fieldname))
    return found


@frappe.whitelist(methods=['POST'])
def prepare(targets):
    admin()
    targets = frappe.parse_json(targets)
    if not isinstance(targets,dict) or not set(targets).issubset(ALLOWED):
        frappe.throw('Invalid cleanup scope')
    records = []
    files = []
    for dt,names in targets.items():
        if not isinstance(names,list):
            frappe.throw('Explicit names are required')
        for name in names:
            if frappe.db.exists(dt,name):
                records.append(frappe.get_doc(dt,name).as_dict())
                for row in frappe.get_all('File',filters={'attached_to_doctype':dt,'attached_to_name':name},pluck='name'):
                    doc = frappe.get_doc('File',row)
                    content = doc.get_content()
                    if isinstance(content,str):
                        content = content.encode()
                    files.append(dict(document=doc.as_dict(),content_base64=base64.b64encode(content).decode()))
    links = incoming(targets)
    payload = dict(purpose='reviewed-test-cleanup',created=frappe.utils.now(),targets=targets,
                   records=records,attachments=files,links=links)
    backup = frappe.get_doc(dict(doctype='File',file_name='test-cleanup-20261031-'+frappe.generate_hash(length=8)+'.json',
                                 is_private=1,content=frappe.as_json(payload))).insert()
    external = [r for r in links if r['source'][1] not in targets.get(r['source'][0],[])]
    return dict(backup=backup.name,url=backup.file_url,counts=dict(Counter(r.doctype for r in records)),external_links=external)


@frappe.whitelist(methods=['POST'])
def execute(backup_name):
    admin()
    backup = frappe.get_doc('File',backup_name)
    if not backup.is_private or not backup.file_name.startswith('test-cleanup-20261031-') or backup.owner != 'Administrator':
        frappe.throw('Use the private reviewed cleanup backup')
    payload = json.loads(backup.get_content())
    if payload.get('purpose') != 'reviewed-test-cleanup':
        frappe.throw('Invalid backup')
    if frappe.utils.getdate(payload['created']) != frappe.utils.getdate():
        frappe.throw('Prepare a fresh backup before cleanup')
    targets = payload['targets']
    if not set(targets).issubset(ALLOWED):
        frappe.throw('Invalid scope')
    originals = {(r['doctype'],r['name']):r for r in payload['records']}
    nodes = {key for key in originals if frappe.db.exists(*key)}
    changed = [key for key in nodes if str(frappe.db.get_value(*key,'modified')) != str(originals[key]['modified'])]
    if changed:
        frappe.throw('Records changed after backup: '+str(changed))
    links = incoming(targets)
    edges = {key:set() for key in nodes}
    external = {}
    for link in links:
        target, source = tuple(link['target']),tuple(link['source'])
        if target not in nodes:
            continue
        if source in nodes:
            edges[target].add(source)
            edges[source].add(target)
        else:
            external.setdefault(target,[]).append(link)
    remaining = set(nodes)
    deleted, blocked = [], []
    while remaining:
        component, queue = set(), [next(iter(remaining))]
        while queue:
            key = queue.pop()
            if key in component:
                continue
            component.add(key)
            queue.extend(edges[key]-component)
        remaining -= component
        blockers = [link for key in component for link in external.get(key,[])]
        if blockers:
            blocked.append(dict(records=sorted(component),external_links=blockers))
            continue
        savepoint = 'cleanup_component'
        frappe.db.savepoint(savepoint)
        todo = set(component)
        failures = {}
        for attempt in range(len(component)+1):
            progress = False
            for dt,name in sorted(todo):
                frappe.db.savepoint('cleanup_record')
                try:
                    doc = frappe.get_doc(dt,name)
                    if doc.docstatus == 1:
                        doc.cancel()
                    frappe.delete_doc(dt,name)
                    todo.remove((dt,name))
                    progress = True
                except Exception as exc:
                    frappe.db.rollback(save_point='cleanup_record')
                    failures[dt+'/'+name] = str(exc)
            if not todo or not progress:
                break
        if todo:
            frappe.db.rollback(save_point=savepoint)
            blocked.append(dict(records=sorted(component),errors={dt+'/'+name:failures.get(dt+'/'+name) for dt,name in todo}))
        else:
            deleted.extend(sorted(component))
    report = dict(backup=backup.name,deleted=deleted,counts=dict(Counter(dt for dt,name in deleted)),blocked=blocked)
    frappe.get_doc(dict(doctype='File',file_name='test-cleanup-result-'+frappe.generate_hash(length=8)+'.json',
                        is_private=1,content=frappe.as_json(report))).insert()
    return report
