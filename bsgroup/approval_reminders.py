"""One daily digest of Mohan's current overdue approvals, using his inbox access."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from html import escape
from hashlib import sha256
import json

import frappe
from frappe.utils import get_datetime
from bsgroup.hr_email import site_profile
from bsgroup.approval_requests import pending, require_mohan
from bsgroup.dcs.manager_approval import FIXED_APPROVER

TZ = ZoneInfo('Asia/Dubai')
METHOD = 'bsgroup.approval_reminders.send_reminder'
CRON = '*/5 9 * * *'
TYPES = {'sales': 'Deal Cost Sheet', 'purchase': 'Material Request', 'labour': 'Labor Preapproval'}
LABELS = {'sales': 'Sales', 'purchase': 'Purchase requisition', 'labour': 'Labour'}


def due(now):
    return time(9) <= now.time().replace(tzinfo=None) < time(10)


def overdue(since, now):
    return now.replace(tzinfo=None) - get_datetime(since) > timedelta(days=2)


def marker(day):
    return 'approval-digest-' + sha256(f'{frappe.local.site}|{day}'.encode()).hexdigest()[:28]


def pending_since(row):
    doc = frappe.get_doc(TYPES[row['kind']], row['name'])
    if row['kind'] == 'sales' and doc.get('custom_revision_reference'):
        revision = frappe.db.get_value('DCS Revision', doc.custom_revision_reference,
            ['dcs', 'changed_on', 'creation'], as_dict=True)
        if revision and revision.dcs == doc.name:
            return revision.changed_on or revision.creation, 'Current revision'
    field = 'custom_approval_state' if row['kind'] == 'sales' else 'workflow_state'
    for version in frappe.get_all('Version', filters={'ref_doctype': doc.doctype, 'docname': doc.name},
            fields=['creation', 'data'], order_by='creation desc', limit_page_length=0):
        for change in json.loads(version.data or '{}').get('changed', []):
            if len(change) >= 3 and change[0] == field and change[1] != change[2]:
                if change[2] == row['state']:
                    return version.creation, 'Approval requested'
                # Never use an older request if the latest recorded transition differs.
                return doc.modified, 'Latest update (legacy record)'
    # Conservative legacy fallback: never assume the original creation was submission.
    return doc.modified, 'Latest update (legacy record)'


def collect(now):
    original = frappe.session.user
    try:
        frappe.set_user(FIXED_APPROVER)
        rows = []
        for row in pending()['requests']:
            since, basis = pending_since(row)
            if overdue(since, now):
                rows.append(dict(row, since=str(since), age_basis=basis,
                    days=round((now.replace(tzinfo=None)-get_datetime(since)).total_seconds()/86400, 1)))
        return sorted(rows, key=lambda r: r['since'])
    finally:
        frappe.set_user(original)


def compose(rows, now):
    region = site_profile()['region']
    host = 'https://erp-om.bitssecureit.com' if region == 'Oman' else 'https://erp.bitssecureit.com'
    subject = f'{region} | Approvals pending over 2 days | {now:%d %b %Y}'
    body = (f'<p>Dear Mohan,</p><p><b>{len(rows)} approval request(s)</b> in {region} have been pending '
        'for more than 48 hours. Please review them in your Approval Request tab.</p>'
        '<table style="border-collapse:collapse;width:100%"><tr>' +
        ''.join(f'<th style="background:#16385e;color:white;padding:10px;text-align:left">{h}</th>'
            for h in ['Type', 'Request / project', 'Requested by', 'Pending since', 'Days pending']) + '</tr>')
    for row in rows:
        cells = [LABELS[row['kind']], row['name']+' — '+str(row.get('subject') or ''),
            row.get('requested_by'), row['since'][:16]+' ('+row['age_basis']+')', row['days']]
        body += '<tr>'+''.join('<td style="border-bottom:1px solid #dbe4ef;padding:10px">'+escape(str(c or '—'))+'</td>' for c in cells)+'</tr>'
    body += (f'</table><p><a href="{host}/desk/bs-group/bs-approval-request">Open Approval Request</a></p>'
        '<p>This reminder does not approve or change any request.</p><p>Regards,<br><b>BITS Secure IT</b></p>')
    return subject, body


def send_reminder():
    now = datetime.now(TZ)
    if not site_profile() or not due(now):
        return 0
    key = marker(now.date())
    if frappe.db.exists('Notification Log', key):
        return 0
    rows = collect(now)
    if not rows:
        return 0
    subject, body = compose(rows, now)
    frappe.db.savepoint('approval_digest')
    try:
        # Unique marker and queue commit together; concurrent runs cannot send twice.
        frappe.get_doc(dict(doctype='Notification Log', name=key, type='Alert', for_user=FIXED_APPROVER,
            from_user='Administrator', subject=subject, email_content=body,
            document_type='User', document_name=FIXED_APPROVER)).db_insert()
        queue = frappe.sendmail(recipients=[FIXED_APPROVER], subject=subject, message=body,
            reference_doctype='User', reference_name=FIXED_APPROVER,
            message_id=f'<{key}@bitssecureit.com>', delayed=True, now=False,
            add_unsubscribe_link=False, is_notification=True)
        if not queue:
            frappe.throw('No reminder Email Queue entry was created.')
        frappe.db.commit()
        return 1
    except frappe.DuplicateEntryError:
        frappe.db.rollback(save_point='approval_digest')
        return 0
    except Exception:
        frappe.db.rollback(save_point='approval_digest')
        raise


def install():
    if site_profile():
        from frappe.core.doctype.scheduled_job_type.scheduled_job_type import insert_single_event
        insert_single_event('Cron', METHOD, CRON)


@frappe.whitelist(methods=['POST'])
def enable():
    frappe.only_for('System Manager')
    install()
    return {'enabled': True, 'time': '09:00 Asia/Dubai', 'recipient': FIXED_APPROVER}


@frappe.whitelist(methods=['GET'])
def page():
    require_mohan()
    now = datetime.now(TZ)
    rows = collect(now)
    job = frappe.db.get_value('Scheduled Job Type', {'method': METHOD},
        ['cron_format', 'stopped', 'last_execution'], as_dict=True)
    subject, body = compose(rows, now)
    setup = ''
    if 'System Manager' in frappe.get_roles():
        from frappe.sessions import get_csrf_token
        setup = '''<form action="/api/method/bsgroup.approval_reminders.enable" method="post" onsubmit="event.preventDefault();const f=this,b=f.querySelector('button'),o=document.getElementById('activation');b.disabled=true;fetch(f.action,{method:'POST',credentials:'same-origin',body:new URLSearchParams(new FormData(f))}).then(async r=>{const data=await r.json();if(!r.ok)throw new Error(data.exception||'Activation failed');o.textContent='Enabled: daily at 9:00 AM. Refresh to view schedule.';}).catch(e=>{o.textContent=e.message;}).finally(()=>{b.disabled=false;});">
        <input type="hidden" name="csrf_token" value="TOKEN"><button type="submit">Enable daily 9 AM reminder</button></form><p id="activation"></p>'''.replace('TOKEN',escape(get_csrf_token(),quote=True))
    frappe.respond_as_web_page('Daily approval reminders',
        f'<h2>{escape(site_profile()["region"])} — Daily approval reminder</h2>'
        f'<p>To: {FIXED_APPROVER} · Every day at 9:00 AM (UTC+4). More than 48 hours pending.</p>'
        f'<p>Schedule: {escape(str(job))}</p><p>One digest per site per day; no email when there are no overdue requests. '
        'This preview sends no email. Five-minute recovery checks run until 10 AM without duplicate emails.</p>'
        + setup + f'<h3>{escape(subject)}</h3>' + body)
