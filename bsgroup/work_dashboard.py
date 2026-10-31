"""Personal dashboard using the same permissions as each document list."""
import frappe
from bsgroup.scoped_sales_access import scope, SCREENS


def screens():
    mode = scope()
    if mode:
        result = list(SCREENS[mode])
        if 'BS Lead Intake Manager' in frappe.get_roles():
            result.append('Lead Intake')
        return result
    if frappe.session.user == 'manikandan@bitssecureit.com':
        return ['Project', 'Task', 'Timesheet', 'Tech Task Scheduler',
                'Site Survey Request', 'HD Ticket', 'HD Customer', 'HD Agent', 'Contact']
    if 'System Manager' in frappe.get_roles():
        return ['Lead', 'Opportunity', 'Presales Request', 'Deal Cost Sheet', 'Quotation']
    return []


@frappe.whitelist()
def data():
    cards = []
    for dt in screens():
        if not frappe.has_permission(dt, 'read'):
            continue
        meta = frappe.get_meta(dt)
        status = 'status' if meta.has_field('status') else 'docstatus'
        # get_list applies role, user and custom record permission filters.
        groups = frappe.get_list(dt, fields=[status, 'count(name) as total'],
                                 group_by=status, limit_page_length=0)
        recent = frappe.get_list(dt, fields=['name', 'modified'],
                                 order_by='modified desc', limit_page_length=5)
        cards.append(dict(doctype=dt, total=sum(r.total for r in groups),
                          statuses=[dict(label=str(r.get(status)) if status == 'status'
                                         else {0:'Draft',1:'Submitted',2:'Cancelled'}.get(r.docstatus, 'Other'),
                                         total=r.total) for r in groups], recent=recent))
    return dict(user=frappe.session.user, cards=cards)


@frappe.whitelist(methods=['POST'])
def setup():
    frappe.only_for('System Manager')
    frappe.reload_doc('bs_group', 'page', 'my_work_dashboard', force=True)
    return 'Dashboard installed'
