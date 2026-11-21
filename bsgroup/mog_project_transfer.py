"""Audited, explicitly scoped MOG Salalah UAE -> Oman transfer tooling."""
import hashlib
import json
import base64
from copy import deepcopy
from html import escape

import frappe

SOURCE = 'PROJ-0008'
TITLE = 'MOG Salalah 7B ELV & Network Project'
AE = {'erp.bitssecureit.com', 'erp-bitssecureit.u.frappe.cloud'}
OM = {'erp-om.bitssecureit.com', 'erp-om.k.frappe.cloud'}
TARGET = 'PROJ-MOG-SALALAH-7B'
PACKAGE_SHA = '267993dc85fa1052dedb59ccba5e33097523c78196bd746b754b438a4a8cb329'
SOURCE_FINGERPRINT = 'f162fcf068a39889ad632e2a4eeecd91b7f9b484ba7651eb4faf6b924babb2d1'
COMPANY = 'Bits Secure IT Infrastructure LLC - OM'


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
    # Legacy scheduler rows sometimes only populated category_name, not project.
    schedulers = set(frappe.get_all('Tech Task Scheduler List',
        filters={'category_name':SOURCE},pluck='parent',limit_page_length=0))
    schedulers.update(d.get('scheduler') for d in records if d.doctype == 'Scheduler Execution' and d.get('scheduler'))
    for name in sorted(schedulers):
        if ('Tech Task Scheduler',name) not in linked:
            records.append(frappe.get_doc('Tech Task Scheduler',name).as_dict())
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


@frappe.whitelist(methods=['GET'])
def export_package():
    require_site(AE)
    records = source_records()
    files = []
    for row in records:
        if row.doctype != 'File' or row.is_folder:
            continue
        doc = frappe.get_doc('File', row.name)
        if not str(doc.file_url).startswith(('/files/', '/private/files/')):
            files.append(dict(name=doc.name, url=doc.file_url, external=True))
            continue
        content = doc.get_content()
        if isinstance(content,str):
            content = content.encode()
        files.append(dict(name=doc.name, url=doc.file_url, sha256=hashlib.sha256(content).hexdigest(),
                          content=base64.b64encode(content).decode()))
    meta = {}
    for record in records:
        for doc in [record] + [c for v in record.values() if isinstance(v,list) for c in v if isinstance(c,dict) and c.get('doctype')]:
            if doc.doctype not in meta:
                meta[doc.doctype] = [dict(fieldname=f.fieldname,fieldtype=f.fieldtype,options=f.options)
                                    for f in frappe.get_meta(doc.doctype).fields]
    employee = frappe.get_doc('Employee', records[0].custom_project_manager)
    return dict(source=SOURCE,source_site='https://erp.bitssecureit.com',title=TITLE,
                fingerprint=digest(records),records=records,files=files,meta=meta,
                project_manager=dict(name=employee.name,employee_name=employee.employee_name,user_id=employee.user_id),
                customer=frappe.get_doc('Customer',records[0].customer).as_dict())


def install_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({'Project':[
        dict(fieldname='custom_bs_transfer_source',label='Transferred from',fieldtype='Data',read_only=1,
             insert_after='monitor_progress_tab'),
        dict(fieldname='custom_bs_transfer_history',label='Transferred work history archive',fieldtype='Attach',
             read_only=1,insert_after='custom_bs_transfer_source'),
        dict(fieldname='custom_bs_transfer_manifest',label='Transfer verification',fieldtype='Long Text',hidden=1,read_only=1),
        dict(fieldname='custom_bs_archived',label='Archived after transfer',fieldtype='Check',hidden=1,read_only=1)
    ]},update=False)


def mapped_name(dt,name):
    if dt=='Project':
        if name!=SOURCE:
            raise ValueError('Unexpected project in transfer')
        return TARGET
    return 'MOG-AE-'+name


def native_records(package):
    records=[]
    for row in package['records']:
        dt=row['doctype']
        if dt in ('Project','Task') or (dt=='Comment' and row.get('reference_doctype') in ('Project','Task')):
            records.append(row)
        elif dt=='ToDo' and frappe.db.exists('User',row.get('allocated_to')):
            records.append(row)
        elif dt=='DocShare' and row.get('share_doctype') in ('Project','Task') and not row.get('everyone') and frappe.db.exists('User',row.get('user')):
            records.append(row)
    return records


def transformed(row,mapping):
    def convert(value):
        if isinstance(value,dict):
            return {k:convert(v) for k,v in value.items() if not k.startswith('_') or k=='_assign'}
        if isinstance(value,list):
            return [convert(v) for v in value]
        return mapping.get(value,value) if isinstance(value,str) else value
    result=convert(deepcopy(row))
    if row['doctype']=='Task':
        result['lft']=0
        result['rgt']=0
    if row['doctype']=='Project':
        result.update(company=COMPANY,custom_project_manager='HR-EMP-00012',
            custom_bs_supply_projects=0,custom_bs_elv_projects=1,custom_bs_infra_projects=0,custom_bs_3cx_projects=0,
            custom_bs_category_review_note='',collect_progress=0,
            custom_bs_transfer_source='UAE / PROJ-0008',custom_bs_archived=0)
    return result


def make_plan(package):
    if package.get('source')!=SOURCE or package.get('fingerprint')!=SOURCE_FINGERPRINT:
        frappe.throw('Source package identity or fingerprint differs from the reviewed snapshot.')
    records=native_records(package)
    mapping={SOURCE:TARGET,'Bits Secure IT Infrastructure LLC - AE':COMPANY,'HRM4':'HR-EMP-00012'}
    for row in records:
        mapping[row['name']]=mapped_name(row['doctype'],row['name'])
        for value in row.values():
            if isinstance(value,list):
                for child in value:
                    if isinstance(child,dict) and child.get('name'):
                        mapping[child['name']]='mog-'+hashlib.sha256(child['name'].encode()).hexdigest()[:24]
    docs=[transformed(row,mapping) for row in records]
    expected={ (d['doctype'],d['name']) for d in docs }
    missing=[]
    for doc in docs:
        for item in [doc]+[x for v in doc.values() if isinstance(v,list) for x in v if isinstance(x,dict) and x.get('doctype')]:
            meta=frappe.get_meta(item['doctype'])
            columns=set(frappe.db.get_table_columns(item['doctype']))
            for key,value in item.items():
                if key not in columns and key!='doctype' and not isinstance(value,list) and value not in (None,'',0,False) and key not in ('custom_bs_transfer_source',):
                    missing.append(f"Schema field {item['doctype']}.{key}")
            for f in meta.fields:
                value=item.get(f.fieldname)
                dt=f.options if f.fieldtype=='Link' else item.get(f.options) if f.fieldtype=='Dynamic Link' else None
                if not dt or not value or (dt,str(value)) in expected:
                    continue
                if dt=='Customer' and value==package['customer']['name']:
                    continue
                if not frappe.db.exists(dt,value):
                    missing.append(f"{item['doctype']} {item.get('name')} / {f.fieldname}: {dt} {value}")
    if missing:
        frappe.throw('Unresolved linked records: '+ '; '.join(sorted(set(missing))))
    if len([d for d in docs if d['doctype']=='Task'])!=110:
        frappe.throw('Expected exactly 110 project tasks.')
    for doc in docs:
        if frappe.db.exists(doc['doctype'],doc['name']):
            frappe.throw('Destination already exists: '+doc['doctype']+' '+doc['name'])
    return docs,mapping


def clean_hash(doc):
    data=doc.as_dict() if hasattr(doc,'as_dict') else deepcopy(doc)
    # Nested-set positions are rebuilt by Frappe and do not change task content.
    data.pop('lft',None);data.pop('rgt',None)
    return digest(data)


def load_package():
    upload=frappe.request.files.get('package')
    if not upload:
        frappe.throw('Select the reviewed transfer package.')
    raw=upload.read()
    if hashlib.sha256(raw).hexdigest()!=PACKAGE_SHA:
        frappe.throw('Package checksum does not match the reviewed MOG transfer.')
    return json.loads(raw),raw


@frappe.whitelist(methods=['POST'])
def import_package(mode='preview'):
    require_site(OM)
    package,raw=load_package()
    if frappe.db.exists('Project',TARGET):
        return verify()
    docs,mapping=make_plan(package)
    counts={}
    for d in docs:counts[d['doctype']]=counts.get(d['doctype'],0)+1
    result=dict(target=TARGET,native_records=counts,history_records=len(package['records']),
        attachments=len(package['files']),protected_project='PROJ-0078',
        missing_historical_users=sorted({r.get('allocated_to') for r in package['records'] if r['doctype']=='ToDo'
            and not frappe.db.exists('User',r.get('allocated_to'))}),
        note='Related historical workflows remain read-only; no financial posting, historical approval, notification or unrelated scheduler work is replayed.')
    if mode=='preview':return result
    if mode!='apply':frappe.throw('Unsupported transfer operation.')
    protected=clean_hash(frappe.get_doc('Project','PROJ-0078'))
    install_fields()
    if not frappe.db.exists('Customer',package['customer']['name']):
        cust=package['customer']
        frappe.get_doc(dict(doctype='Customer',customer_name=cust['customer_name'],customer_type=cust['customer_type'],
            customer_group=frappe.db.get_single_value('Selling Settings','customer_group') or 'All Customer Groups',
            territory=frappe.db.get_single_value('Selling Settings','territory') or 'All Territories'))\
            .insert(ignore_permissions=True,set_name=cust['name'])
    # Original timestamps and statuses are imported without replaying historical workflows.
    for item in docs:
        doc=frappe.get_doc(item)
        doc.db_insert()
        for child in doc.get_all_children():child.db_insert()
    # Check the mapped source content, not just record counts.
    def comparable(value):
        if value is None:return ''
        if isinstance(value,(float,int)):return float(value)
        return str(value)
    for item in docs:
        saved=frappe.get_doc(item['doctype'],item['name']).as_dict()
        for key,value in item.items():
            if key in ('lft','rgt') or isinstance(value,list):continue
            if comparable(saved.get(key))!=comparable(value):
                frappe.throw('Transferred field mismatch: '+item['doctype']+' '+item['name']+' '+key)
        for key,children in item.items():
            if not isinstance(children,list):continue
            actual={c.name:c for c in saved.get(key,[])}
            if len(actual)!=len(children):frappe.throw('Transferred child count mismatch.')
            for child in children:
                if any(comparable(actual[child['name']].get(k))!=comparable(v) for k,v in child.items()):
                    frappe.throw('Transferred task dependency mismatch.')
    from frappe.utils.nestedset import rebuild_tree
    rebuild_tree('Task','parent_task')
    from frappe.utils.file_manager import save_file
    archive=save_file('MOG-Salalah-UAE-transfer-history.json',raw,'Project',TARGET,is_private=1)
    files=[]
    file_records={r['name']:r for r in package['records'] if r['doctype']=='File'}
    for f in package['files']:
        if f.get('external'):
            files.append(dict(source=f['name'],url=f['url'],external=True));continue
        content=base64.b64decode(f['content'],validate=True)
        if hashlib.sha256(content).hexdigest()!=f['sha256']:frappe.throw('Attachment checksum mismatch.')
        record=file_records[f['name']]
        saved=save_file(f['name']+'-'+record['file_name'],content,'Project',TARGET,is_private=1)
        files.append(dict(source=f['name'],url=saved.file_url,sha256=f['sha256'],file=saved.name))
    frappe.db.set_value('Project',TARGET,'custom_bs_transfer_history',archive.file_url,update_modified=False)
    expected=[]
    for item in docs:
        if item['doctype']=='Project':continue
        expected.append(dict(doctype=item['doctype'],name=item['name'],sha256=clean_hash(frappe.get_doc(item['doctype'],item['name']))))
    manifest=dict(result,package_sha=PACKAGE_SHA,source_fingerprint=SOURCE_FINGERPRINT,
        protected_sha=protected,mapping=mapping,files=files,expected=expected,archive_file=archive.name,
        archive_sha=hashlib.sha256(raw).hexdigest(),project_expected={k:docs[0].get(k) for k in
            ('project_name','status','percent_complete','expected_start_date','notes','custom_latest_update','company','custom_project_manager')})
    frappe.db.set_value('Project',TARGET,'custom_bs_transfer_manifest',json.dumps(manifest),update_modified=False)
    result=verify()
    if not result['verified']:frappe.throw('Transfer verification failed: '+frappe.as_json(result))
    return result


@frappe.whitelist(methods=['GET'])
def verify():
    require_site(OM)
    project=frappe.get_doc('Project',TARGET)
    manifest=json.loads(project.custom_bs_transfer_manifest or '{}')
    if manifest.get('package_sha')!=PACKAGE_SHA:frappe.throw('Transfer marker is missing or mismatched.')
    failures=[]
    for row in manifest['expected']:
        if not frappe.db.exists(row['doctype'],row['name']) or clean_hash(frappe.get_doc(row['doctype'],row['name']))!=row['sha256']:
            failures.append(row['doctype']+' '+row['name'])
    for k,v in manifest['project_expected'].items():
        actual=project.get(k)
        if str(actual or '')!=str(v or ''):failures.append('Project '+k)
    if clean_hash(frappe.get_doc('Project','PROJ-0078'))!=manifest['protected_sha']:
        failures.append('Protected PROJ-0078 changed')
    for file in manifest['files']:
        if file.get('external'):continue
        content=frappe.get_doc('File',file['file']).get_content()
        if isinstance(content,str):content=content.encode()
        if hashlib.sha256(content).hexdigest()!=file['sha256']:failures.append('Attachment '+file['source'])
    content=frappe.get_doc('File',manifest['archive_file']).get_content()
    if isinstance(content,str):content=content.encode()
    if hashlib.sha256(content).hexdigest()!=PACKAGE_SHA:failures.append('History package checksum')
    tasks=frappe.get_all('Task',filters={'project':TARGET},fields=['name','status','parent_task'],limit_page_length=0)
    if len(tasks)!=110:failures.append('Task count')
    names={t.name for t in tasks}
    if any(t.parent_task and t.parent_task not in names for t in tasks):failures.append('Task hierarchy')
    return dict(verified=not failures,failures=failures,target=TARGET,task_count=len(tasks),
                native_records=manifest['native_records'],history_records=manifest['history_records'],
                attachments=len(manifest['files']),protected_project_unchanged='Protected PROJ-0078 changed' not in failures,
                package_sha=PACKAGE_SHA,source_fingerprint=SOURCE_FINGERPRINT)


@frappe.whitelist(methods=['GET'])
def transfer_page():
    require_site(OM)
    from frappe.sessions import get_csrf_token
    form='''<h2>MOG Salalah — Oman ELV transfer</h2><p>Separate project; PROJ-0078 is protected. Preview before importing. Historical workflows are retained as a read-only archive, not replayed.</p>
    <form id="transfer"><input type="file" name="package" accept=".json" required><input type="hidden" name="csrf_token" value="TOKEN">
    <button type="submit" name="mode" value="preview">Preview transfer</button><button type="submit" name="mode" value="apply">Import verified project and tasks</button></form><pre id="result"></pre>
    <script>document.getElementById('transfer').onsubmit=async function(e){e.preventDefault();const data=new FormData(this);data.set('mode',e.submitter.value);const buttons=[...this.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);try{const r=await fetch('/api/method/bsgroup.mog_project_transfer.import_package',{method:'POST',credentials:'same-origin',headers:{'X-Frappe-CSRF-Token':this.elements.csrf_token.value},body:data});document.getElementById('result').textContent=JSON.stringify(await r.json(),null,2);}catch(e){document.getElementById('result').textContent=e.message;}finally{buttons.forEach(b=>b.disabled=false);}};</script>'''
    frappe.respond_as_web_page('MOG project transfer',form.replace('TOKEN',escape(get_csrf_token(),quote=True)))


@frappe.whitelist(methods=['GET'])
def history(project):
    if frappe.local.site not in OM or project!=TARGET:frappe.throw('Unknown transfer history.')
    doc=frappe.get_doc('Project',project);doc.check_permission('read')
    manifest=json.loads(doc.custom_bs_transfer_manifest)
    package=json.loads(frappe.get_doc('File',manifest['archive_file']).get_content())
    html='<h2>MOG Salalah — transferred UAE history</h2><p>Original dates, authors, statuses and amounts. Historical entries do not submit approvals, send messages or create expenses. Shared schedules include only this project’s rows.</p>'
    for f in manifest['files']:
        html+='<p><a href="'+escape(f['url'],quote=True)+'">Attachment '+escape(f['source'])+'</a></p>'
    for row in sorted(package['records'],key=lambda r:(r.get('creation') or '',r['doctype'],r['name'])):
        html+='<details><summary>'+escape(str(row.get('creation') or '')+' · '+row['doctype']+' · '+row['name'])+'</summary><pre style="white-space:pre-wrap">'+escape(json.dumps(row,ensure_ascii=False,indent=2))+'</pre></details>'
    frappe.respond_as_web_page('Transferred project history',html)
