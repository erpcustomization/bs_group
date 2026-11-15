"""Business-language module grants. Existing roles and workflow policies are immutable here."""
import hashlib
import json
import frappe

FIELD = "custom_bs_module_grants"
MODULES = {
    "Sales": {"records": ("Lead", "Opportunity", "Deal Cost Sheet", "Quotation"), "edit": ("Sales User",)},
    "Projects": {"records": ("Project", "Task", "Timesheet", "Delivery Request"), "edit": ("Projects User",), "approve": ("Projects Manager",)},
    "HR": {"records": ("Employee", "Employee Checkin", "Leave Application", "Attendance", "Expense Claim", "Employee Advance"), "edit": ("HR User",), "approve": ("Leave Approver", "Expense Approver")},
    "Procurement": {"records": ("Material Request", "Purchase Order"), "edit": ("Purchase User",)},
}
RIGHTS = ("read", "write", "create", "submit", "cancel", "delete", "share", "export", "import", "print", "email", "report", "select", "amend")
LABELS = dict(read="View", write="Edit", create="Create", submit="Submit", cancel="Cancel", delete="Delete", share="Share", export="Export", import_="Import", print="Print", email="Email", report="Reports", select="Select", amend="Amend")


def install():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"User": [dict(fieldname=FIELD, label="BS Module Grants", fieldtype="Long Text", hidden=1, read_only=1, no_copy=1)]}, update=False)


def viewer(module):
    return "BS Console " + module + " View"


def stored(doc):
    try:
        value = json.loads(doc.get(FIELD) or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        frappe.throw("The recorded module grants need administrator review before editing.")


def effective_rules():
    fields = ["parent", "role", "permlevel", "if_owner", *RIGHTS]
    custom = frappe.get_all("Custom DocPerm", fields=fields, limit_page_length=0)
    overridden = {r.parent for r in custom}
    standard = frappe.get_all("DocPerm", fields=fields, limit_page_length=0)
    disabled = set(frappe.get_all('Role', filters={'disabled':1}, pluck='name'))
    return [dict(r) for r in custom if r.role not in disabled] + [dict(r) for r in standard if r.parent not in overridden and r.role not in disabled]


def all_rules_with_viewers(rules, available):
    result = list(rules)
    for module, records in available.items():
        role = viewer(module)
        existing = [r for r in rules if r['role'] == role]
        expected = [dict(parent=dt, role=role, permlevel=0, if_owner=0, **{a:int(a in ('read','select')) for a in RIGHTS}) for dt in records]
        if existing:
            def signature(rows):
                return sorted((r['parent'], int(r.get('permlevel') or 0), int(r.get('if_owner') or 0), tuple(int(bool(r.get(a))) for a in RIGHTS)) for r in rows)
            if signature(existing) != signature(expected):
                frappe.throw("The dedicated " + module + " viewing permission was changed outside this console. Ask an administrator to review it.")
        else:
            if frappe.db.exists('Role', role):
                frappe.throw('The dedicated '+module+' viewing permission exists without its expected access rules. Ask an administrator to review it.')
            result.extend(expected)
    return result


def rights_for(rules, roles):
    result = {}
    for rule in rules:
        if rule['role'] not in roles:
            continue
        # Include every field level and owner condition in preview; never claim record-wide access.
        key = (rule['parent'], int(rule.get('permlevel') or 0), int(rule.get('if_owner') or 0))
        result.setdefault(key, set()).update(a for a in RIGHTS if rule.get(a))
    return result


def workflow_roles(records):
    result = set()
    for name in frappe.get_all("Workflow", filters={"is_active":1, "document_type":["in",list(records)]}, pluck="name"):
        workflow = frappe.get_doc("Workflow", name)
        for row in workflow.transitions:
            if str(row.action or '').strip().lower() in ('approve', 'approve request', 'approve leave'):
                result.add(row.allowed)
    return result


def approval(module, user, roles, context):
    if module == 'Sales':
        if context['fixed_sales']:
            return user == 'mohan@bitssecureit.com', "Sales approvals remain assigned to Mohan."
        return False, "Sales approval depends on the request's assigned manager."
    if module == 'Procurement':
        return (user == 'mohan@bitssecureit.com' and {'BS Procurement Approver','Purchase Manager'} <= roles), "Purchase approvals remain assigned to Mohan."
    eligible = context['approval_roles'][module]
    return bool(roles & eligible), "Only assigned, eligible requests can be approved; workflow and self-approval checks still apply."


def blocked_reason(doc, roles, module):
    if doc.name in ('Administrator','Guest'):
        return "This system account is protected."
    if doc.get('role_profiles') or doc.get('role_profile_name'):
        return "Existing access is controlled by an access profile."
    if doc.user_type != 'System User':
        return "This is a portal account; ERP module grants require an ERP account."
    scoped = 'BS Scoped Sales' in roles or 'BS Scoped Presales' in roles
    if scoped and module != 'Sales':
        return "This account has an existing Sales-only workspace."
    if module == 'HR' and doc.name not in ('muskan@bitssecureit.com','Administrator') and 'System Manager' not in roles:
        return "BS HR management is restricted to Muskan and administrators. Employee self-service is unchanged."
    if module == 'Projects' and doc.name == 'amar@bitssecureit.com':
        from bsgroup.hr_email import is_oman
        if is_oman():
            return "Oman assignment-only project access is protected."
    return ''


def context_for(doc):
    available = {m:[dt for dt in spec['records'] if frappe.db.exists('DocType',dt)] for m,spec in MODULES.items()}
    rules = all_rules_with_viewers(effective_rules(), available)
    assigned = {r.role for r in doc.get('roles',[])}
    state = stored(doc)
    owned = set(state.get('owned_roles',[])) & assigned
    base = assigned - owned
    implicit = set(frappe.get_roles(doc.name)) - assigned
    approvals = {m:workflow_roles(records) for m,records in available.items() if m in ('Projects','HR')}
    # Native HR leave approval also requires an assigned leave approver, independent of Workflow.
    if frappe.db.exists('Role',{'name':'Leave Approver','disabled':0}):
        approvals['HR'].add('Leave Approver')
    # In native Leave Application, submitting Approved/Rejected is the decision.
    # Active workflows instead retain their own explicit approval transitions.
    if not frappe.db.exists('Workflow', {'document_type':'Leave Application','is_active':1}):
        approvals['HR'].update(r['role'] for r in rules if r['parent']=='Leave Application' and not r.get('permlevel') and r.get('submit'))
    return dict(available=available, rules=rules, assigned=assigned, base=base, implicit=implicit,
        state=state, owned=owned, approval_roles=approvals,
        fixed_sales=frappe.db.get_single_value('BS Group Settings','dcs_approval_policy')=='Mohan')


def grant_roles(module, action, context):
    if action == 'view':
        return {viewer(module)}
    candidates = MODULES[module].get(action,())
    if action == 'approve':
        candidates = [r for r in candidates if r in context['approval_roles'].get(module,set())]
    return {r for r in candidates if frappe.db.exists('Role',{'name':r,'disabled':0})}


def summarize(doc, context, roles=None):
    roles = (context['assigned'] | context['implicit']) if roles is None else roles | context['implicit']
    baseline = rights_for(context['rules'],context['base'] | context['implicit'])
    current = rights_for(context['rules'],roles)
    result=[]
    grants = context['state'].get('grants',{})
    for module,records in context['available'].items():
        row=dict(module=module, records=records, cells={}, note=blocked_reason(doc,roles,module))
        for action,right in (('view','read'),('edit','write'),('approve',None)):
            if right:
                allowed = [dt for dt in records if any(key[0]==dt and key[1]==0 and right in value for key,value in current.items())]
                inherited = [dt for dt in records if any(key[0]==dt and key[1]==0 and right in value for key,value in baseline.items())]
                inherited_full = bool(records) and len(inherited)==len(records)
                status = 'Available' if records and len(allowed)==len(records) else 'Limited' if allowed else 'Not granted'
                if doc.name == 'Administrator':
                    inherited_full = True
                    status = 'Available'
                note = 'Applies only to accessible records. Company, ownership and assignment restrictions remain.'
            else:
                enabled,note=approval(module,doc.name,roles,context)
                inherited_full=approval(module,doc.name,context['base'] | context['implicit'],context)[0]
                status='Eligible requests' if enabled else 'Not granted'
            managed = bool(grants.get(module+'.'+action)) and set(grants[module+'.'+action]) <= roles
            reason = row['note']
            if action=='approve' and module in ('Sales','Procurement'):
                reason=note
            elif inherited_full:
                reason='Included in existing access; protected from removal here.'
            elif status in ('Available','Eligible requests') and not managed:
                reason='Included in another new grant. Remove that grant first to change this option.'
            elif not grant_roles(module,action,context):
                reason='No compatible permission is configured for this option.'
            if not records:
                reason='This module is not installed.'
            row['cells'][action]=dict(status=status, managed=managed, inherited=inherited_full,
                checked=managed or inherited_full or status in ('Available','Eligible requests'), partial=status=='Limited' and not managed,
                editable=not bool(reason), reason=reason, note=note)
        result.append(row)
    return result


def public_details(doc):
    context=context_for(doc)
    return summarize(doc,context)


def plan(doc, changes):
    if not isinstance(changes,dict):
        frappe.throw('Choose valid module permissions.')
    context=context_for(doc)
    rows={r['module']:r for r in summarize(doc,context)}
    grants={k:list(v) for k,v in context['state'].get('grants',{}).items() if isinstance(v,list) and set(v)<=context['assigned']}
    for key,enabled in changes.items():
        parts=key.split('.')
        if len(parts)!=2 or parts[0] not in MODULES or parts[1] not in ('view','edit','approve') or type(enabled) is not bool:
            frappe.throw('Choose valid module permissions.')
        module,action=parts
        cell=rows[module]['cells'][action]
        if enabled==cell['managed']:
            continue
        # Removal is allowed only for tracked grants, never baseline roles.
        if not cell['editable'] and (enabled or not cell['managed']):
            frappe.throw(module+': '+cell['reason'])
        if enabled:
            grants[key]=sorted(grant_roles(module,action,context))
        else:
            grants.pop(key,None)
    needed={role for values in grants.values() for role in values}
    after=context['base'] | needed
    before_rights=rights_for(context['rules'],context['assigned'] | context['implicit'])
    after_rights=rights_for(context['rules'],after | context['implicit'])
    impact=[]
    for key in sorted(before_rights.keys() | after_rights.keys()):
        before=before_rights.get(key,set());after_actions=after_rights.get(key,set())
        added=after_actions-before; removed=before-after_actions
        if added or removed:
            impact.append(dict(record=key[0],field_level=key[1],own_records=bool(key[2]),
                added=[LABELS.get(a,a.title()) for a in sorted(added)], removed=[LABELS.get(a,a.title()) for a in sorted(removed)]))
    payload=dict(user=doc.name,modified=str(doc.modified),changes=changes,roles=sorted(after),
        state=dict(grants=grants,owned_roles=sorted(after-context['base'])),impact=impact,
        policy=dict(fixed_sales=context['fixed_sales'],approval_roles={m:sorted(v) for m,v in context['approval_roles'].items()}),
        rules=sorted(context['rules'],key=lambda r:json.dumps(r,sort_keys=True,default=str)))
    token=hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()
    public=dict(token=token,changes=[dict(module=k.split('.')[0],permission=k.split('.')[1].title(),enabled=v) for k,v in changes.items()],
        impact=impact,has_changes=bool(changes) and (after!=context['assigned'] or payload['state']!=context['state']),
        note='Existing roles, assigned records and approval policies are preserved. The listed record permissions are the complete role-grant changes, including any effects outside the selected module.')
    return payload,public,context


def ensure_viewers(roles,context):
    from frappe.permissions import setup_custom_perms
    for module,records in context['available'].items():
        role=viewer(module)
        if role not in roles or frappe.db.exists('Role',role):
            continue
        frappe.get_doc(dict(doctype='Role',role_name=role,desk_access=1)).insert()
        for dt in records:
            setup_custom_perms(dt)
            rule=dict(doctype='Custom DocPerm',parent=dt,parenttype='DocType',parentfield='permissions',
                role=role,permlevel=0,if_owner=0,**{a:int(a in ('read','select')) for a in RIGHTS})
            frappe.get_doc(rule).insert()
            frappe.clear_cache(doctype=dt)


def load_target(user,expected_modified):
    from bsgroup.user_management import require_manager
    require_manager()
    doc=frappe.get_doc('User',user)
    doc.check_permission('write')
    if str(doc.modified)!=str(expected_modified):
        frappe.throw('This account changed. Refresh and review it again before saving.')
    return doc


@frappe.whitelist(methods=['POST'])
def preview(user,expected_modified,changes):
    doc=load_target(user,expected_modified)
    changes=frappe.parse_json(changes) if isinstance(changes,str) else changes
    return plan(doc,changes)[1]


@frappe.whitelist(methods=['POST'])
def save(user,expected_modified,changes,preview_token):
    doc=load_target(user,expected_modified)
    changes=frappe.parse_json(changes) if isinstance(changes,str) else changes
    payload,public,context=plan(doc,changes)
    if not preview_token or preview_token!=public['token']:
        frappe.throw('Access rules changed since the preview. Review the updated changes before saving.')
    if not public['has_changes']:
        return dict(saved=False)
    # No mutation is performed by details/preview/install. Only an explicit reviewed Save gets here.
    ensure_viewers(payload['roles'],context)
    retained=[r for r in doc.get('roles',[]) if r.role in payload['roles']]
    old={r.role for r in retained}
    doc.set('roles',retained)
    for role in payload['roles']:
        if role not in old:doc.append('roles',dict(role=role))
    doc.set(FIELD,json.dumps(payload['state'],sort_keys=True))
    doc.save()
    if {r.role for r in doc.roles}!=set(payload['roles']):
        frappe.throw('An existing account rule changed the proposed access. No changes were saved; review the account profile.')
    doc.add_comment('Info','Module permissions updated after preview: '+', '.join(
        r['module']+' '+r['permission']+(' added' if r['enabled'] else ' removed') for r in public['changes']))
    frappe.clear_cache(user=user)
    return dict(saved=True)
