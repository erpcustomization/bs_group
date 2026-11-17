"""Explicit project operations role. Never assign users or grant approval powers."""
import frappe

ROLE = "BS Projects Manager"
OPERATIONS = ("Project", "Task", "Project Template", "Project Type", "Timesheet",
              "Tech Task Scheduler", "Site Survey Request", "AMC Contract", "PPM Plan", "PPM Visit")
READ_ONLY = ("Delivery Request", "Project Labour Expense", "BS Project Plan Run")
REQUESTS = ("Labor Preapproval",)
OWN_REQUESTS = ("Expense Claim", "Employee Advance")
SCREENS = OPERATIONS + READ_ONLY + REQUESTS + OWN_REQUESTS
LINKS = ("Company", "Customer", "User", "Employee", "Activity Type", "Cost Center",
         "Expense Claim Type", "Account", "Item", "UOM")


def enabled(user=None):
    return ROLE in frappe.get_roles(user or frappe.session.user)


def sync_user(doc, method=None):
    """Keep the native requester role needed by labour workflow, with provenance."""
    field = 'custom_bs_project_manager_base_role'
    if not doc.meta.has_field(field):
        return
    roles = {r.role for r in doc.roles}
    if ROLE in roles and doc.user_type == 'System User':
        if 'Projects User' not in roles:
            doc.append('roles', dict(role='Projects User'))
            doc.set(field, 1)
    elif doc.get(field):
        doc.set('roles', [r for r in doc.roles if r.role != 'Projects User'])
        doc.set(field, 0)


def install():
    from bsgroup.hr_email import site_profile
    if not site_profile():
        return
    from frappe.permissions import setup_custom_perms
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({'User': [dict(fieldname='custom_bs_project_manager_base_role',
        label='Project Manager Managed Base Role', fieldtype='Check', hidden=1,
        read_only=1, no_copy=1, default='0')]}, update=True)
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc(dict(doctype="Role", role_name=ROLE, desk_access=1)).insert(ignore_permissions=True)
    for dt in SCREENS + LINKS:
        if not frappe.db.exists("DocType", dt):
            continue
        setup_custom_perms(dt)
        values = dict(read=1, select=1, print=1, report=1, write=int(dt not in READ_ONLY),
                      create=int(dt not in READ_ONLY), submit=int(dt in OPERATIONS and frappe.get_meta(dt).is_submittable),
                      delete=0, cancel=0, amend=0, share=0, export=0, import_=0, email=0)
        values['import'] = values.pop('import_')
        if dt in LINKS:
            values = {key: int(key == 'select') for key in values}
        filters = dict(parent=dt, role=ROLE, permlevel=0, if_owner=int(dt in OWN_REQUESTS))
        name = frappe.db.get_value("Custom DocPerm", filters, "name")
        rule = frappe.get_doc("Custom DocPerm", name) if name else frappe.get_doc(dict(
            doctype="Custom DocPerm", parenttype="DocType", parentfield="permissions", **filters))
        rule.update(values)
        rule.save(ignore_permissions=True)
        frappe.clear_cache(doctype=dt)
    # Reports retain their own record filters and company restrictions.
    for name in ("Task Summary Report", "Task Scheduler Report", "Tech Task Scheduler Report"):
        if frappe.db.exists("Report", name):
            report = frappe.get_doc("Report", name)
            if ROLE not in {r.role for r in report.roles}:
                report.append("roles", dict(role=ROLE))
                report.save(ignore_permissions=True)
    frappe.clear_cache()
