"""Opt-in mid-month (15th) and month-end sales/presales work reports."""
import calendar
from datetime import datetime, date, time, timedelta
from hashlib import sha256
from html import escape
import frappe
from bsgroup.weekly_commercial_email import people, collect_range, report, TZ
from bsgroup.hr_email import site_profile

METHOD = 'bsgroup.periodic_commercial_email.send_reports'
CRON = '*/5 9-10,17-18 * * *'
FLAG = 'custom_bs_periodic_work_reports'
ANCHOR = 'custom_bs_periodic_report_anchor'


def periods(now, anchor):
    """Fixed cutoffs; recovery ticks do not expand a report's range."""
    today = now.date()
    if today < anchor:
        return []
    clock = now.time().replace(tzinfo=None)
    result = []
    if today.day == 15 and time(9, 30) <= clock < time(11):
        end = datetime.combine(today, time(9, 30))
        result.append(('Mid-Month', datetime.combine(today.replace(day=1), time()), end))
    if today.day == calendar.monthrange(today.year, today.month)[1] and time(17, 30) <= clock < time(19):
        end = datetime.combine(today, time(17, 30))
        result.append(('Month-End', datetime.combine(today.replace(day=1), time()), end))
    return result


def key(user, kind, cadence, end):
    return 'periodic-work-' + sha256(f'{user}|{kind}|{cadence}|{end}'.encode()).hexdigest()[:28]


def compose(person, data, cadence, end):
    data = dict(data, display_end=end.date())
    subject, body = report(person, data, cadence=cadence)
    note = f'<p>Activity window: {data["start"]:%d %b %Y %H:%M} to {end:%d %b %Y %H:%M} (Oman/UAE time, UTC+4). Activity at or after the cutoff is not included.</p>'
    return subject, note + body


def send_reports():
    now = datetime.now(TZ)
    if not site_profile() or not frappe.db.get_single_value('Selling Settings', FLAG):
        return 0
    anchor = frappe.db.get_single_value('Selling Settings', ANCHOR)
    if not anchor:
        return 0
    windows = periods(now, date.fromisoformat(str(anchor)))
    sent = 0
    for cadence, start, end in windows:
        data = collect_range(start, end)
        for person in people():
            marker = key(person['user'], person['kind'], cadence, end)
            if frappe.db.exists('Notification Log', marker):
                continue
            frappe.db.savepoint('periodic_commercial')
            try:
                subject, body = compose(person, data, cadence, end)
                frappe.get_doc(dict(doctype='Notification Log', name=marker, type='Alert',
                    for_user=person['user'], from_user='Administrator', subject=subject,
                    email_content=body, document_type='User', document_name=person['user'])).db_insert()
                queue = frappe.sendmail(recipients=[person['user']], cc=person['cc'],
                    expose_recipients='header', subject=subject, message=body,
                    reference_doctype='User', reference_name=person['user'],
                    message_id=f'<{marker}@bitssecureit.com>', delayed=True, now=False,
                    add_unsubscribe_link=False, is_notification=True)
                if not queue:
                    frappe.throw('No Email Queue entry was created.')
                frappe.db.commit()
                sent += 1
            except frappe.DuplicateEntryError:
                frappe.db.rollback(save_point='periodic_commercial')
            except Exception:
                frappe.db.rollback(save_point='periodic_commercial')
                frappe.log_error(title='Periodic commercial email failed', message=frappe.get_traceback())
    return sent


def install():
    if not site_profile():
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({'Selling Settings': [
        dict(fieldname=FLAG, label='Mid-month and month-end work reports', fieldtype='Check', default='0'),
        dict(fieldname=ANCHOR, label='Periodic work reports enabled from', fieldtype='Date'),
    ]}, update=False)
    from frappe.core.doctype.scheduled_job_type.scheduled_job_type import insert_single_event
    insert_single_event('Cron', METHOD, CRON)


@frappe.whitelist(methods=['POST'])
def enable():
    frappe.only_for('System Manager')
    if not site_profile():
        frappe.throw('Unsupported site.')
    install()
    # Apply the requested weekly time change as part of this reviewed setup.
    from bsgroup.weekly_commercial_email import install as install_weekly
    install_weekly()
    if not frappe.db.get_single_value('Selling Settings', ANCHOR):
        frappe.db.set_single_value('Selling Settings', ANCHOR, datetime.now(TZ).date())
    frappe.db.set_single_value('Selling Settings', FLAG, 1)
    return dict(enabled=True, anchor=str(frappe.db.get_single_value('Selling Settings', ANCHOR)))


@frappe.whitelist(methods=['GET'])
def preview():
    """Render representative reports without queues, markers or settings writes."""
    frappe.only_for('System Manager')
    now=datetime.now(TZ)
    roster=people()
    output=[]
    for cadence,start in [('Mid-Month',datetime.combine(now.date().replace(day=1),time())),('Month-End',datetime.combine(now.date().replace(day=1),time()))]:
        end=datetime.combine(now.date(),time(9,30) if cadence=='Mid-Month' else time(17,30))
        data=collect_range(start,end)
        for kind in ('Sales','Presales'):
            person=next((p for p in roster if p['kind']==kind),None)
            if person:
                subject,body=compose(person,data,cadence,end)
                output.append(dict(cadence=cadence,kind=kind,to=person['user'],cc=person['cc'],subject=subject,
                    body_length=len(body),has_details='<table' in body or 'No activity recorded' in body,
                    test_records_excluded=len(data['excluded'])))
    return dict(read_only=True,emails_sent=0,samples=output)


@frappe.whitelist(methods=['GET'])
def page():
    frappe.only_for('System Manager')
    from frappe.sessions import get_csrf_token
    enabled = frappe.db.get_single_value('Selling Settings', FLAG)
    anchor = frappe.db.get_single_value('Selling Settings', ANCHOR)
    job = frappe.db.get_value('Scheduled Job Type', {'method':METHOD}, ['stopped','cron_format','last_execution'], as_dict=True)
    roster = ''.join(f'<li>{escape(p["name"])} — {p["kind"]}: {escape(p["user"])}; CC: {escape(", ".join(p["cc"]) or "none (self)")}</li>' for p in people())
    html = f'<h2>{escape(site_profile()["region"])} — Periodic sales and presales reports</h2><p>Enabled: {bool(enabled)} · Enabled from: {anchor} · Job: {escape(str(job))}</p><p>Weekly: Monday 09:30. Mid-month: 15th at 09:30, work from the 1st to the cutoff. Month-end: last day at 17:30, work from the 1st to the cutoff. All times UTC+4. Monthly target reports remain unchanged. Test transactions excluded. Current reporting manager in CC; Mohan fallback.</p><ul>{roster}</ul>'
    html += '<form id="enable"><button>Enable periodic reports</button></form><pre id="result"></pre><script>document.getElementById("enable").onsubmit=async function(e){e.preventDefault();const b=this.querySelector("button");b.disabled=true;try{const r=await fetch("/api/method/bsgroup.periodic_commercial_email.enable",{method:"POST",headers:{"X-Frappe-CSRF-Token":"TOKEN"}});document.getElementById("result").textContent=JSON.stringify(await r.json(),null,2);}finally{b.disabled=false;}};</script>'
    frappe.respond_as_web_page('Periodic work reports', html.replace('TOKEN', escape(get_csrf_token(),quote=True)))
