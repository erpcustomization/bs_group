"""Oman employee assignment eligibility and assignment-scoped read access."""
import frappe

USERS = ('amar@bitssecureit.com', 'nowfal@bitssecureit.com')
FLAG = 'custom_bs_assigned_project_access'
COMPANY = 'Bits Secure IT Infrastructure LLC - OM'
READER_ROLE = 'BS Assigned Project Reader'


def restricted(user=None):
    from bsgroup.hr_email import is_oman
    return is_oman() and (user or frappe.session.user) == 'amar@bitssecureit.com'


def assigned_condition(doctype, user=None):
    user = user or frappe.session.user
    if not restricted(user):
        return ''
    names = sorted(name for dt, name in desired(user) if dt == doctype)
    if not names:
        return '1=0'
    return f'`tab{doctype}`.name in (' + ','.join(frappe.db.escape(name) for name in names) + ')'


def project_query(user=None):
    return assigned_condition('Project', user)


def task_query(user=None):
    return assigned_condition('Task', user)


def assigned_permission(doc, user=None, permission_type=None, ptype=None):
    user = user or frappe.session.user
    if not restricted(user):
        return True
    return ((permission_type or ptype or 'read') in ('read', 'select')
            and not doc.is_new() and (doc.doctype, doc.name) in desired(user))


def install_amar_reader():
    """Open native navigation without granting general access to other records."""
    if not restricted('amar@bitssecureit.com') or not frappe.db.exists('User', 'amar@bitssecureit.com'):
        return
    if not frappe.db.exists('Role', READER_ROLE):
        frappe.get_doc(dict(doctype='Role', role_name=READER_ROLE, desk_access=1)).insert(ignore_permissions=True)
    from frappe.permissions import setup_custom_perms
    for dt in ('Project', 'Task'):
        setup_custom_perms(dt)
        filters = dict(parent=dt, role=READER_ROLE, permlevel=0, if_owner=1)
        name = frappe.db.get_value('Custom DocPerm', filters, 'name')
        rule = frappe.get_doc('Custom DocPerm', name) if name else frappe.get_doc(dict(
            doctype='Custom DocPerm', parenttype='DocType', parentfield='permissions', **filters))
        # Owner-only grants expose the app/list. Exact assigned records remain
        # readable through the existing assignment shares and query restrictions.
        rule.update(dict(read=1, select=1, write=0, create=0, delete=0, submit=0,
                         cancel=0, amend=0, report=0, export=0, share=0, print=0, email=0))
        rule.save(ignore_permissions=True)
        frappe.clear_cache(doctype=dt)
    user = frappe.get_doc('User', 'amar@bitssecureit.com')
    if READER_ROLE not in [row.role for row in user.roles]:
        user.append('roles', dict(role=READER_ROLE))
        user.save(ignore_permissions=True)
    frappe.clear_cache(user=user.name)


def employee_users():
    """Only active Oman employees with enabled desk accounts may be assigned."""
    employees = frappe.get_all('Employee', filters={'company': COMPANY, 'status': 'Active'},
        fields=['user_id', 'employee_name'])
    result = {}
    for employee in employees:
        if not employee.user_id:
            continue
        account = frappe.db.get_value('User', employee.user_id, ['enabled', 'user_type'], as_dict=True)
        if account and account.enabled and account.user_type == 'System User':
            result[employee.user_id] = employee.employee_name or employee.user_id
    return result


def applies(project):
    from bsgroup.hr_email import is_oman
    return project.company == COMPANY and is_oman()


def desired(user):
    result = set()
    for assignment in frappe.get_all('ToDo', filters={
            'allocated_to': user, 'reference_type': 'Task', 'status': 'Open'},
            fields=['reference_name']):
        task = frappe.db.get_value('Task', assignment.reference_name,
            ['name', 'project', 'status'], as_dict=True)
        if not task or not task.project or task.status in ('Completed', 'Closed', 'Cancelled', 'Template'):
            continue
        project = frappe.db.get_value('Project', task.project, ['company', 'status'], as_dict=True)
        if not project or project.company != 'Bits Secure IT Infrastructure LLC - OM' or project.status in ('Completed', 'Closed', 'Cancelled'):
            continue
        result.update({('Task', task.name), ('Project', task.project)})
    return result


def sync(doc=None, method=None):
    from bsgroup.hr_email import is_oman
    if not is_oman() or not frappe.get_meta('DocShare').has_field(FLAG):
        return
    from frappe.share import add_docshare as add, remove
    eligible = employee_users()
    managed = frappe.get_all('DocShare', filters={FLAG: 1}, pluck='user')
    for user in set(eligible) | set(managed) | set(USERS):
        wanted = desired(user) if user in eligible else set()
        for share in frappe.get_all('DocShare', filters={'user': user, FLAG: 1},
                fields=['share_doctype', 'share_name']):
            if (share.share_doctype, share.share_name) not in wanted:
                remove(share.share_doctype, share.share_name, user, flags={'ignore_permissions': True})
        for doctype, name in sorted(wanted):
            filters = {'user': user, 'share_doctype': doctype, 'share_name': name}
            # Keep independently granted/native assignment shares unchanged.
            if frappe.db.exists('DocShare', filters):
                continue
            add(doctype, name, user=user, read=1, write=0, share=0,
                flags={'ignore_share_permission': True}, notify=0)
            frappe.db.set_value('DocShare', filters, FLAG, 1, update_modified=False)
        frappe.clear_cache(user=user)


def install():
    from bsgroup.hr_email import is_oman
    if not is_oman():
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({'DocShare': [dict(fieldname=FLAG, label='Managed assigned project access',
        fieldtype='Check', read_only=1, hidden=1, no_copy=1)]}, update=True)
    sync()
    install_amar_reader()


def configure_hooks(hooks):
    for dt, query in (('Project', 'project_query'), ('Task', 'task_query')):
        hooks.setdefault('permission_query_conditions', {})[dt] = 'bsgroup.oman_assigned_project_access.' + query
        hooks.setdefault('has_permission', {})[dt] = 'bsgroup.oman_assigned_project_access.assigned_permission'
    hooks.setdefault('after_migrate', []).append('bsgroup.oman_assigned_project_access.install')
    for doctype, events in {'ToDo': ('on_update', 'after_delete'), 'Task': ('on_update',),
                            'Project': ('on_update',)}.items():
        target = hooks.setdefault('doc_events', {}).setdefault(doctype, {})
        for event in events:
            old = target.get(event, [])
            target[event] = ([old] if isinstance(old, str) else list(old)) + ['bsgroup.oman_assigned_project_access.sync']
