"""Personal dashboard using the same permissions as each document list."""
import frappe
from bsgroup.scoped_sales_access import scope, SCREENS


@frappe.whitelist()
def navigation_script():
    """Serve navigation from the app when patched static assets are unavailable."""
    from pathlib import Path
    content = Path(frappe.get_app_path('bsgroup', 'public', 'js', 'scoped_sales_access.js')).read_text()
    import json
    style = Path(frappe.get_app_path('bsgroup', 'public', 'css', 'portal_finish.css')).read_text()
    content += '\n(() => { const s=document.createElement("style"); s.textContent=' + json.dumps(style) + '; document.head.append(s); const sync=()=>{const r=document.body.dataset.route||"";document.body.classList.toggle("bs-premium", /^(List|Form)\\/(Lead|Project|Task|Timesheet|Tech Task Scheduler|Site Survey Request)(\\/|$)/.test(r)||r==="my-work-dashboard");};new MutationObserver(sync).observe(document.body,{attributes:true,attributeFilter:["data-route"]});sync();})();'
    frappe.local.response.update(type='download', filename='scoped_sales_access.js',
                                 filecontent=content, content_type='application/javascript',
                                 display_content_as='inline')


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
        rows = frappe.get_list(dt, fields=['name', status], limit_page_length=0)
        counts = {}
        for row in rows:
            value = row.get(status)
            counts[value] = counts.get(value, 0) + 1
        recent = frappe.get_list(dt, fields=['name', 'modified'],
                                 order_by='modified desc', limit_page_length=5)
        cards.append(dict(doctype=dt, total=len(rows),
                          statuses=[dict(label=str(value) if status == 'status'
                                         else {0:'Draft',1:'Submitted',2:'Cancelled'}.get(value, 'Other'),
                                         total=count) for value, count in counts.items()], recent=recent))
    return dict(user=frappe.session.user, cards=cards)


@frappe.whitelist(methods=['POST'])
def setup():
    frappe.only_for('System Manager')
    frappe.reload_doc('bs_group', 'page', 'my_work_dashboard', force=True)
    return 'Dashboard installed'
