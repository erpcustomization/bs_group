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
    content += '\n' + Path(frappe.get_app_path('bsgroup', 'public', 'js', 'workday_reminder.js')).read_text()
    content += '\n' + Path(frappe.get_app_path('bsgroup', 'public', 'js', 'attendance_widget.js')).read_text()
    content += '\n' + Path(frappe.get_app_path('bsgroup', 'public', 'js', 'opportunity_attachments.js')).read_text()
    import json
    style = Path(frappe.get_app_path('bsgroup', 'public', 'css', 'portal_finish.css')).read_text()
    style += '\n' + Path(frappe.get_app_path('bsgroup', 'public', 'css', 'attendance_widget.css')).read_text()
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
    roles = set(frappe.get_roles())
    result = []
    for allowed_roles, doctypes in (
        ({'Sales User', 'Sales Manager', 'Sales Master Manager'},
         ['Lead', 'Opportunity', 'Deal Cost Sheet', 'Quotation']),
        ({'Presales'}, ['Presales Request', 'Deal Cost Sheet', 'Quotation']),
        ({'Projects User', 'Projects Manager'},
         ['Project', 'Task', 'Timesheet', 'Tech Task Scheduler', 'Site Survey Request']),
        ({'Purchase User', 'Purchase Manager'},
         ['Material Request', 'Purchase Order', 'Purchase Receipt']),
    ):
        if roles & allowed_roles:
            result.extend(dt for dt in doctypes if dt not in result)
    return result


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
    presales = presales_summary(start, end) if scope() == 'BS Scoped Presales' else None
    sales_roles = {'BS Scoped Sales', 'Sales User', 'Sales Manager', 'Sales Master Manager'}
    sales = sales_summary(start, end) if not presales and sales_roles.intersection(frappe.get_roles()) else None
    return dict(user=frappe.session.user, cards=cards, month=month, totals=totals, presales=presales, sales=sales,
                daily=daily, start=str(start), end=str(end))


def aggregate_sales(rows, currencies):
    result = {key: dict(count=0, amounts={}) for key in ('quoted', 'won', 'lost')}
    for row in rows:
        currency = currencies[row.company]
        stage = row.get('custom_pipeline_stage') or row.get('status')
        keys = ['quoted']
        if stage in ('Won', 'Ordered'):
            keys.append('won')
        elif stage == 'Lost':
            keys.append('lost')
        for key in keys:
            result[key]['count'] += 1
            amounts = result[key]['amounts']
            amounts[currency] = amounts.get(currency, 0) + float(row.base_grand_total or 0)
    return result


def sales_summary(start, end):
    """Own submitted quotations dated in the month, with their current outcomes.

    Won/Lost are subsets of the quoted cohort, not outcome-event month totals.
    Revisions cancelled in ERPNext and draft quotes are excluded.
    """
    if not frappe.has_permission('Quotation', 'read'):
        return aggregate_sales([], {})
    own_opportunities = set(frappe.get_list('Opportunity',
        filters={'opportunity_owner': frappe.session.user}, pluck='name',
        limit_page_length=0)) if frappe.has_permission('Opportunity', 'read') else set()
    fields = ['name', 'owner', 'opportunity', 'company', 'base_grand_total', 'status']
    if frappe.get_meta('Quotation').has_field('custom_pipeline_stage'):
        fields.append('custom_pipeline_stage')
    rows = frappe.get_list('Quotation', fields=fields, filters=[
        ['docstatus', '=', 1], ['transaction_date', '>=', str(start)],
        ['transaction_date', '<', str(end)]], limit_page_length=0)
    rows = [row for row in rows if row.opportunity in own_opportunities or
            (not row.opportunity and row.owner == frappe.session.user)]
    currencies = {row.company: frappe.get_cached_value('Company', row.company, 'default_currency')
                  for row in rows}
    return aggregate_sales(rows, currencies)


def presales_summary(start, end):
    """All-time workload and dated submission events, limited to readable records."""
    closed = {'Submitted to Sales', 'Completed', 'Won', 'Lost', 'Cancelled'}
    requests = frappe.get_list('Presales Request', fields=['name', 'status', 'docstatus'],
                               limit_page_length=0) if frappe.has_permission('Presales Request', 'read') else []
    sheets = frappe.get_list('Deal Cost Sheet', fields=['name', 'docstatus', 'custom_deal_status'],
                            limit_page_length=0) if frappe.has_permission('Deal Cost Sheet', 'read') else []
    open_requests = sum(row.docstatus != 2 and row.status not in closed for row in requests)
    pending_dcs = sum(row.docstatus == 0 and row.custom_deal_status not in {'Won', 'Lost', 'Cancelled'} for row in sheets)
    submitted = set()
    # Query audit events only for documents already returned by permission-filtered get_list.
    # A later edit or quotation must not move the submission into another month.
    names = [row.name for row in sheets]
    for offset in range(0, len(names), 500):
        events = frappe.get_all('Comment', filters=[
            ['reference_doctype', '=', 'Deal Cost Sheet'],
            ['reference_name', 'in', names[offset:offset + 500]],
            ['comment_type', '=', 'Submitted'],
            ['creation', '>=', str(start)], ['creation', '<', str(end)]
        ], fields=['reference_name'], limit_page_length=0)
        submitted.update(row.reference_name for row in events)
    return dict(open_requests=open_requests, pending_dcs=pending_dcs, submitted=len(submitted))


@frappe.whitelist(methods=['POST'])
def setup():
    frappe.only_for('System Manager')
    frappe.reload_doc('bs_group', 'page', 'my_work_dashboard', force=True)
    return 'Dashboard installed'
