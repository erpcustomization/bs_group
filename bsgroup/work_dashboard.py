"""Personal dashboard using the same permissions as each document list."""
import frappe
from bsgroup.scoped_sales_access import scope, SCREENS, show_lead_intake_navigation


@frappe.whitelist()
def navigation_script():
    """Serve navigation from the app when patched static assets are unavailable."""
    from pathlib import Path
    content = Path(frappe.get_app_path('bsgroup', 'public', 'js', 'scoped_sales_access.js')).read_text()
    content += '\n' + Path(frappe.get_app_path('bsgroup', 'public', 'js', 'personal_column_widths.js')).read_text()
    content += '\n' + Path(frappe.get_app_path('bsgroup', 'public', 'js', 'sales_list_search.js')).read_text()
    content += '\n' + Path(frappe.get_app_path('bsgroup', 'public', 'js', 'user_first_names.js')).read_text()
    import json
    style = Path(frappe.get_app_path('bsgroup', 'public', 'css', 'portal_finish.css')).read_text()
    content += '\n(() => { const s=document.createElement("style"); s.id="bs-portal-theme"; s.textContent=' + json.dumps(style) + '; document.getElementById(s.id)?.remove(); document.head.append(s); document.body.classList.add("bs-premium"); })();'
    frappe.local.response.update(type='download', filename='scoped_sales_access.js',
                                 filecontent=content, content_type='application/javascript',
                                 display_content_as='inline')


def screens():
    mode = scope()
    if mode:
        result = list(SCREENS[mode])
        if show_lead_intake_navigation():
            result.append('Lead Intake')
        return result
    if frappe.session.user == 'manikandan@bitssecureit.com':
        return ['Project', 'Task', 'Timesheet', 'Tech Task Scheduler',
                'Site Survey Request', 'HD Ticket', 'HD Customer', 'HD Agent', 'Contact']
    if 'System Manager' in frappe.get_roles():
        return ['Lead', 'Opportunity', 'Presales Request', 'Deal Cost Sheet', 'Quotation']
    return []


@frappe.whitelist()
def data(month=None):
    from datetime import date
    import calendar
    month = month or str(frappe.utils.today())[:7]
    try:
        start = date.fromisoformat(month + '-01')
    except (ValueError, TypeError):
        frappe.throw('Choose a valid month (YYYY-MM).')
    end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    days = calendar.monthrange(start.year, start.month)[1]
    daily = [0] * days
    totals = dict(created=0, updated=0, active=0)
    cards = []
    for dt in screens():
        if not frappe.has_permission(dt, 'read'):
            continue
        meta = frappe.get_meta(dt)
        status = 'status' if meta.has_field('status') else 'docstatus'
        # get_list applies role, user and custom record permission filters.
        fields = ['name', status, 'creation', 'modified']
        created = frappe.get_list(dt, fields=fields,
            filters=[['creation', '>=', str(start)], ['creation', '<', str(end)]], limit_page_length=0)
        updated = frappe.get_list(dt, fields=fields,
            filters=[['modified', '>=', str(start)], ['modified', '<', str(end)]], limit_page_length=0)
        rows = list({row.name: row for row in created + updated}.values())
        for row in created:
            daily[frappe.utils.getdate(row.creation).day - 1] += 1
        totals['created'] += len(created)
        totals['updated'] += len(updated)
        totals['active'] += len(rows)
        counts = {}
        for row in rows:
            value = row.get(status)
            counts[value] = counts.get(value, 0) + 1
        recent = sorted(rows, key=lambda row: str(row.modified), reverse=True)[:5]
        cards.append(dict(doctype=dt, total=len(rows), created=len(created), updated=len(updated),
                          statuses=[dict(label=str(value) if status == 'status'
                                         else {0:'Draft',1:'Submitted',2:'Cancelled'}.get(value, 'Other'),
                                         total=count) for value, count in counts.items()], recent=recent))
    return dict(user=frappe.session.user, cards=cards, month=month, totals=totals,
                daily=daily, start=str(start), end=str(end))


@frappe.whitelist(methods=['POST'])
def setup():
    frappe.only_for('System Manager')
    frappe.reload_doc('bs_group', 'page', 'my_work_dashboard', force=True)
    return 'Dashboard installed'
