"""Individual Monday sales/presales reports. No record or mail-account changes."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from hashlib import sha256
from html import escape
import json
import re
import frappe
from bsgroup.hr_email import site_profile

TZ = ZoneInfo('Asia/Dubai')
METHOD = 'bsgroup.weekly_commercial_email.send_reports'
FLAG = 'custom_bs_weekly_commercial_reports'
CRON = '*/5 10-11 * * 1'  # 10:30 first send; subsequent ticks recover failures only.
MOHAN = 'mohan@bitssecureit.com'
KINDS = {'Sales': {'Sales User', 'Sales Manager', 'Sales Master Manager', 'BS Scoped Sales'},
         'Presales': {'Presales', 'BS Scoped Presales'}}
TYPES = ('Lead', 'Opportunity', 'Presales Request', 'Deal Cost Sheet', 'Quotation')
TEST = re.compile(r'(?i)(\btest\b|\be2e\b|do[\s_-]*not[\s_-]*use|donotuse|\bzz[\s_-]*test\b)')


def period(monday):
    if monday.weekday() != 0:
        raise ValueError('Reports run on Monday.')
    return monday - timedelta(days=7), monday


def due(now):
    return now.weekday() == 0 and time(10, 30) <= now.time().replace(tzinfo=None) < time(12)


def key(user, kind, monday):
    return 'weekly-commercial-' + sha256(f'{user}|{kind}|{monday}'.encode()).hexdigest()[:28]


def people():
    profile = site_profile()
    if not profile:
        return []
    company = 'Bits Secure IT Infrastructure LLC - ' + ('OM' if profile['region'] == 'Oman' else 'AE')
    employees = frappe.get_all('Employee', filters={'status': 'Active', 'company': company},
        fields=['name', 'employee_name', 'user_id', 'reports_to'], limit_page_length=0)
    result, seen = [], set()
    for employee in employees:
        user = employee.user_id
        if not user or user in seen or user in ('Administrator', 'Guest'):
            continue
        if not frappe.db.get_value('User', user, 'enabled') or not frappe.utils.validate_email_address(user):
            continue
        seen.add(user)
        roles = set(frappe.get_roles(user))
        manager = frappe.db.get_value('Employee', employee.reports_to, ['user_id', 'status'], as_dict=True) if employee.reports_to else None
        cc = manager.user_id if manager and manager.status == 'Active' else None
        if not cc or cc == user or not frappe.db.get_value('User', cc, 'enabled') or not frappe.utils.validate_email_address(cc):
            cc = MOHAN
        if not frappe.db.get_value('User', cc, 'enabled'):
            frappe.throw('Reporting-manager fallback Mohan must have an enabled account.')
        for kind, allowed in KINDS.items():
            if roles & allowed:
                result.append(dict(user=user, name=frappe.db.get_value('User', user, 'first_name') or employee.employee_name,
                    kind=kind, cc=[] if cc == user else [cc]))
    return result


def collect(monday):
    start, end = period(monday)
    records = {dt: {r.name: r for r in frappe.get_all(dt, fields=['*'], limit_page_length=0)} for dt in TYPES}
    # Trace test ancestry so renamed/ordinary-looking downstream records stay excluded.
    def parents(dt, r):
        refs = [('Opportunity', r.get('opportunity')), ('Presales Request', r.get('presales_request')),
                ('Deal Cost Sheet', r.get('custom_deal_cost_sheet')), ('Lead', r.get('lead'))]
        if dt == 'Opportunity' and r.get('opportunity_from') == 'Lead':
            refs.append(('Lead', r.get('party_name')))
        if dt == 'Quotation' and r.get('quotation_to') == 'Lead':
            refs.append(('Lead', r.get('party_name')))
        return [(a, b) for a, b in refs if b and b in records[a]]
    excluded = {(dt, name) for dt, rows in records.items() for name, r in rows.items()
                if any(TEST.search(str(r.get(f) or '')) for f in ('name', 'subject', 'lead_name', 'customer',
                    'customer_name', 'company_name', 'party_name', 'organisation_name', 'organization_name'))}
    while True:
        more = {(dt, name) for dt, rows in records.items() for name, r in rows.items()
                if any(p in excluded for p in parents(dt, r))}
        if more <= excluded:
            break
        excluded |= more
    events = {}
    def add(dt, name, actor, stamp, label, changes=None):
        if (dt, name) in excluded or name not in records.get(dt, {}):
            return
        events.setdefault((dt, name), []).append(dict(actor=actor, stamp=str(stamp), label=label, changes=changes or []))
    for dt, rows in records.items():
        for name, r in rows.items():
            if str(start) <= str(r.creation) < str(end):
                add(dt, name, r.owner, r.creation, 'Created')
            if str(start) <= str(r.modified) < str(end) and r.modified != r.creation:
                add(dt, name, r.modified_by, r.modified, 'Updated')
    for v in frappe.get_all('Version', filters=[['ref_doctype', 'in', list(TYPES)],
            ['creation', '>=', str(start)], ['creation', '<', str(end)]],
            fields=['ref_doctype', 'docname', 'owner', 'creation', 'data'], limit_page_length=0):
        payload = json.loads(v.data or '{}')
        changes = payload.get('changed', [])
        revision = payload.get('oman_quotation_revision') or {}
        if revision.get('event') == 'After DCS revision':
            changes.append(['custom_oman_revision_no', None, revision.get('revision')])
        labels = [f'{x[0].replace("_", " ")}: {x[1]} → {x[2]}' for x in changes
                  if x[0] in ('status', 'workflow_state', 'custom_pipeline_stage', 'custom_dcs_revision_no', 'custom_oman_revision_no')]
        add(v.ref_doctype, v.docname, v.owner, v.creation, '; '.join(labels) or 'Record updated', changes)
    for c in frappe.get_all('Comment', filters=[['reference_doctype', 'in', list(TYPES)],
            ['creation', '>=', str(start)], ['creation', '<', str(end)], ['comment_type', 'in', ['Comment', 'Submitted']]],
            fields=['reference_doctype', 'reference_name', 'owner', 'creation', 'comment_type'], limit_page_length=0):
        add(c.reference_doctype, c.reference_name, c.owner, c.creation,
            'Submitted' if c.comment_type == 'Submitted' else 'Work comment recorded')
    employees = {r.name:r.user_id for r in frappe.get_all('Employee',fields=['name','user_id'],limit_page_length=0)}
    records['_sales_people'] = {r.name:employees.get(r.employee) for r in frappe.get_all('Sales Person',fields=['name','employee'],limit_page_length=0)}
    return dict(start=start, end=end, records=records, events=events, excluded=excluded)


def sales_owner(dt, r, records):
    if dt == 'Lead':
        return r.get('lead_owner') or r.owner
    if dt == 'Opportunity':
        return r.get('opportunity_owner') or r.owner
    sheet = records['Deal Cost Sheet'].get(r.get('custom_deal_cost_sheet')) if dt == 'Quotation' else r
    opp = records['Opportunity'].get(r.get('opportunity') or (sheet or {}).get('opportunity'))
    return (opp or {}).get('opportunity_owner') or (sheet or {}).get('deal_owner') or records.get('_sales_people',{}).get(r.get('custom_sales_person')) or r.owner


def table(headings, rows):
    if not rows:
        return '<p>No activity recorded for this period.</p>'
    cell = lambda text: '<td style="border:1px solid #dbe3ef;padding:8px">' + escape(str(text or '—')) + '</td>'
    return '<table style="border-collapse:collapse;width:100%"><tr>' + ''.join('<th>'+escape(h)+'</th>' for h in headings) + '</tr>' + ''.join('<tr>'+''.join(cell(x) for x in row)+'</tr>' for row in rows) + '</table>'


def report(person, data):
    user, kind = person['user'], person['kind']
    rows, selected = [], {}
    for (dt, name), events in data['events'].items():
        r = data['records'][dt][name]
        if kind == 'Presales':
            if dt not in ('Presales Request', 'Deal Cost Sheet'):
                continue
            events = [e for e in events if e['actor'] == user]
            if not events:
                continue
        elif dt == 'Presales Request' or sales_owner(dt, r, data['records']) != user:
            continue
        # Explicit record permission check: do not email otherwise inaccessible data.
        if not frappe.has_permission(dt, 'read', doc=frappe.get_doc(dt, name), user=user):
            continue
        selected[(dt, name)] = events
        customer = r.get('customer_name') or r.get('customer') or r.get('lead_name') or r.get('party_name') or r.get('organisation_name')
        activity = '\n'.join(sorted({e['stamp'][:16] + ' — ' + e['label'] for e in events}))
        status = r.get('custom_pipeline_stage') or r.get('status') or r.get('workflow_state') or {0:'Draft',1:'Submitted',2:'Cancelled'}.get(r.docstatus)
        rows.append((dt, name, customer, activity, r.get('custom_dcs_revision_no') or r.get('custom_oman_revision_no') or '—', status))
    start, last = data['start'], data['end'] - timedelta(days=1)
    subject = f'Your Weekly {kind} Report | {start:%d %b}–{last:%d %b %Y}'
    body = f'<p>Dear {escape(person["name"])},</p><p>Please find your weekly {kind.lower()} work summary for <b>{start:%d %B %Y}–{last:%d %B %Y}</b>.</p>'
    if kind == 'Presales':
        for dt, heading in (('Presales Request','Presales Requests Worked On'), ('Deal Cost Sheet','Costing Sheets Worked On')):
            part = [r for r in rows if r[0] == dt]
            body += f'<h3>{heading} ({len(part)})</h3>' + table(['Reference','Customer','Work Recorded Last Week','Revision','Current Status'], [r[1:] for r in part])
    else:
        def count(dt, predicate):
            return sum(any(predicate(e) for e in es) for (d, n), es in selected.items() if d == dt)
        def transition(e, field, values):
            return any(x[0] == field and str(x[2]) in values and x[1] != x[2] for x in e['changes'])
        stats = []
        for dt, label in (('Lead','Leads created / updated'),('Opportunity','Opportunities created / progressed')):
            stats.append((label, f'{count(dt,lambda e:e["label"]=="Created")} / {count(dt,lambda e:e["label"]!="Created")}'))
        stats += [('Costing sheets submitted / revised', f'{count("Deal Cost Sheet",lambda e:e["label"]=="Submitted" or transition(e,"docstatus",{"1"}))} / {count("Deal Cost Sheet",lambda e:any(x[0]=="custom_dcs_revision_no" and x[1]!=x[2] for x in e["changes"]))}'),
                  ('Quotations issued / revised', f'{count("Quotation",lambda e:transition(e,"custom_pipeline_stage",{"Quote sent","Quote Sent"}))} / {count("Quotation",lambda e:any(x[0] in ("custom_oman_revision_no","custom_dcs_revision_reference") and x[1]!=x[2] for x in e["changes"]))}')]
        for outcome in ('Won','Lost'):
            matches = [n for (d,n),es in selected.items() if d=='Quotation' and any(transition(e,'custom_pipeline_stage',{outcome}) for e in es)]
            amounts = {}
            for n in matches:
                r=data['records']['Quotation'][n]; currency=r.get('currency') or 'Currency not recorded'
                amounts[currency]=amounts.get(currency,0)+float(r.get('grand_total') or 0)
            stats.append(('Quotations '+outcome.lower(),str(len(matches))+' — '+(', '.join(f'{c} {v:,.2f}' for c,v in amounts.items()) or '—')))
        stats.append(('Quotations handed over to procurement',count('Quotation',lambda e:any(x[0]=='custom_bsp_material_request' and not x[1] and x[2] for x in e['changes']))))
        body += '<h3>Your Weekly Summary</h3>'+table(['Activity','This week'],stats)
        body += '<h3>Weekly Record Details</h3>'+table(['Type','Reference','Customer','Activity Recorded Last Week','Revision','Current Status'],rows)
        # Outstanding work is a current snapshot, distinct from the week's activity.
        pending=[]
        for dt in ('Lead','Opportunity','Deal Cost Sheet','Quotation'):
            for name,r in data['records'][dt].items():
                if (dt,name) in data['excluded'] or sales_owner(dt,r,data['records'])!=user or r.get('docstatus')==2:
                    continue
                status=r.get('custom_pipeline_stage') or r.get('status') or r.get('workflow_state') or 'Draft'
                if status in ('Won','Lost','Cancelled','Closed','Converted','Ordered','Completed'):
                    continue
                if not frappe.has_permission(dt,'read',doc=frappe.get_doc(dt,name),user=user):
                    continue
                deadline=r.get('next_contact_date') or r.get('custom_next_follow_up_date') or r.get('due_date')
                pending.append((name,r.get('customer_name') or r.get('customer') or r.get('lead_name') or r.get('party_name'),status,'Review and update next action',deadline or 'Not recorded'))
        body += '<h3>Items Requiring Your Attention — Current Outstanding Work</h3>'+table(['Reference','Customer','Current Status','Pending Action','Due Date'],pending)
    host = 'https://erp-om.bitssecureit.com' if site_profile()['region']=='Oman' else 'https://erp.bitssecureit.com'
    body += '<p>Counts use recorded ERP activity; current status is shown separately. Test records and linked test transactions are excluded.</p><p>Please review your outstanding items and keep your progress and next follow-up date updated in ERP.</p>'
    body += f'<p><a href="{host}/desk/my-work-dashboard">Open Your ERP Dashboard</a></p><p>Regards,<br><b>BITS Secure IT</b></p>'
    return subject, body


def send_reports():
    now=datetime.now(TZ)
    if not site_profile() or not due(now) or not frappe.db.get_single_value('Selling Settings',FLAG):
        return 0
    data=collect(now.date()); sent=0
    for person in people():
        marker=key(person['user'],person['kind'],now.date())
        if frappe.db.exists('Notification Log',marker):
            continue
        frappe.db.savepoint('weekly_commercial')
        try:
            subject,body=report(person,data)
            frappe.get_doc(dict(doctype='Notification Log',name=marker,type='Alert',for_user=person['user'],
                from_user='Administrator',subject=subject,email_content=body,document_type='User',document_name=person['user'])).db_insert()
            queue=frappe.sendmail(recipients=[person['user']],cc=person['cc'],expose_recipients='header',subject=subject,
                message=body,reference_doctype='User',reference_name=person['user'],message_id=f'<{marker}@bitssecureit.com>',
                delayed=True,now=False,add_unsubscribe_link=False,is_notification=True)
            if not queue:
                frappe.throw('No Email Queue entry was created.')
            frappe.db.commit();sent+=1
        except frappe.DuplicateEntryError:
            frappe.db.rollback(save_point='weekly_commercial')
        except Exception:
            frappe.db.rollback(save_point='weekly_commercial')
            frappe.log_error(title='Weekly commercial email failed',message=frappe.get_traceback())
    return sent


def install():
    if not site_profile():
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    if not frappe.get_meta('Selling Settings').has_field(FLAG):
        create_custom_fields({'Selling Settings':[dict(fieldname=FLAG,label='Weekly sales and presales reports',fieldtype='Check',default='0',
            description='Monday 10:30 AM UTC+4; previous Monday–Sunday; CC reporting manager or Mohan. Test records excluded.')]},update=False)
        frappe.db.set_single_value('Selling Settings',FLAG,1)
    from frappe.core.doctype.scheduled_job_type.scheduled_job_type import insert_single_event
    insert_single_event('Cron',METHOD,CRON)


@frappe.whitelist(methods=['GET'])
def page():
    frappe.only_for('System Manager')
    now=datetime.now(TZ); monday=now.date()-timedelta(days=now.weekday())
    data=collect(monday); rows=[]
    for person in people():
        subject,body=report(person,data)
        status='Queued' if frappe.db.exists('Notification Log',key(person['user'],person['kind'],monday)) else 'Not queued'
        rows.append(f'<h3>{escape(person["name"])} — {person["kind"]}</h3><p>To: {escape(person["user"])} · CC: {escape(", ".join(person["cc"]) or "Self; no duplicate CC")} · {status}</p><details><summary>{escape(subject)}</summary>{body}</details>')
    job=frappe.db.get_value('Scheduled Job Type',{'method':METHOD},['cron_format','stopped','last_execution'],as_dict=True)
    enabled=frappe.db.get_single_value('Selling Settings',FLAG)
    frappe.respond_as_web_page('Weekly sales and presales reports',f'<h2>Monday 10:30 AM — {escape(site_profile()["region"])}</h2><p>Enabled: {bool(enabled)} · Job: {escape(str(job))}</p><p>Period: {data["start"]} to {data["end"]-timedelta(days=1)}. Read-only preview; no emails sent by this page.</p>'+''.join(rows))
