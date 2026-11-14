"""Oman employee assignment eligibility and assignment-scoped read access."""
import frappe

USERS = ('amar@bitssecureit.com', 'nowfal@bitssecureit.com')
FLAG = 'custom_bs_assigned_project_access'
COMPANY = 'Bits Secure IT Infrastructure LLC - OM'


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


def configure_hooks(hooks):
    hooks.setdefault('after_migrate', []).append('bsgroup.oman_assigned_project_access.install')
    for doctype, events in {'ToDo': ('on_update', 'after_delete'), 'Task': ('on_update',),
                            'Project': ('on_update',)}.items():
        target = hooks.setdefault('doc_events', {}).setdefault(doctype, {})
        for event in events:
            old = target.get(event, [])
            target[event] = ([old] if isinstance(old, str) else list(old)) + ['bsgroup.oman_assigned_project_access.sync']
