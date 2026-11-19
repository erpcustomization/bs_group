"""Individual monthly fiscal-year target progress; no attendance/account changes."""
import calendar
from datetime import datetime, timedelta, time
from hashlib import sha256
from html import escape

import frappe
from frappe.utils import flt, getdate
from bsgroup.hr_email import site_profile
from bsgroup.dashboard_targets import progress
from bsgroup.weekly_commercial_email import people, table, TZ, MOHAN

METHOD = 'bsgroup.monthly_sales_targets_email.send_reports'
FLAG = 'custom_bs_monthly_target_reports'
CRON = '*/5 10-11 1 * *'


def due(now):
    return now.day == 1 and time(10, 30) <= now.time().replace(tzinfo=None) < time(12)


def cutoff(run_date):
    return run_date.replace(day=1) - timedelta(days=1)


def key(user, end):
    return 'monthly-target-' + sha256(f'{user}|{end}'.encode()).hexdigest()[:28]


def recipients():
    # Use the same active, linked employee population as the weekly sales report.
    for person in people():
        if person['kind'] == 'Sales':
            person['cc'] = sorted(set(person['cc'] + [MOHAN]) - {person['user']})
            yield person


def month_dates(start, end):
    cursor = start.replace(day=1)
    result = {}
    while cursor <= end:
        result[calendar.month_name[cursor.month]] = cursor
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result


def collect(person, end):
    from erpnext.accounts.utils import get_fiscal_year
    company = 'Bits Secure IT Infrastructure LLC - ' + ('OM' if site_profile()['region'] == 'Oman' else 'AE')
    employees = frappe.get_all('Employee', filters={'user_id':person['user'], 'status':'Active', 'company':company}, pluck='name')
    fy, start, finish = get_fiscal_year(end, company=company)[:3]
    start, finish = getdate(start), getdate(finish)
    result = dict(fiscal_year=fy, start=start, end=end,
        currency=frappe.db.get_value('Company', company, 'default_currency'), warnings=[], monthly=[], sales=None, gp=None)
    persons = frappe.get_all('Sales Person', filters={'employee':['in',employees], 'enabled':1}, pluck='name') if employees else []
    if len(persons) != 1:
        result['warnings'].append('Sales Person mapping is missing or ambiguous. Please ask your reporting manager to review it.')
        return result
    targets = frappe.get_all('Target Detail', filters={'parenttype':'Sales Person', 'parent':persons[0], 'fiscal_year':fy},
        fields=['target_amount','custom_invoiced_gp_target','custom_gp_target'], limit_page_length=0)
    target = targets[0] if len(targets) == 1 else {}
    if len(targets) != 1:
        result['warnings'].append('Annual target is not set or has multiple overlapping rows; no target has been assumed.')
    entries = frappe.get_all('Sales Target GP Entry', filters={'salesperson':persons[0], 'fiscal_year':fy, 'docstatus':['!=',2]}, pluck='name')
    months = month_dates(start, end)
    rows = {}
    if len(entries) == 1:
        for row in frappe.get_doc('Sales Target GP Entry', entries[0]).monthly_data:
            if row.month in months:
                if row.month in rows:
                    result['warnings'].append('Duplicate monthly performance rows require review; totals are withheld.')
                    return result
                rows[row.month] = row
    elif len(entries) > 1:
        result['warnings'].append('Multiple performance entries require review; totals are withheld.')
        return result
    revenue = gp = 0
    recorded = False
    for month in months:
        row = rows.get(month)
        available = bool(row and (row.get('status') != 'Not Entered' or flt(row.get('invoiced_sales_revenue')) or flt(row.get('invoiced_sales_gp'))))
        ir = flt(row.get('invoiced_sales_revenue')) if available else None
        ig = flt(row.get('invoiced_sales_gp')) if available else None
        result['monthly'].append((month, ir, ig, 'Recorded' if available else 'Not entered'))
        if available:
            recorded = True
            revenue += ir
            gp += ig
    if any(r[3] == 'Not entered' for r in result['monthly']):
        result['warnings'].append('Some months have no recorded performance. Totals include recorded months only and may be incomplete.')
    result['sales'] = dict(progress(target.get('target_amount'), revenue), available=recorded)
    result['gp'] = dict(progress(flt(target.get('custom_invoiced_gp_target')) or target.get('custom_gp_target'), gp), available=recorded)
    return result


def report(person, end):
    data = collect(person, end)
    subject = f'Your Monthly Sales Target Progress | {site_profile()["region"]} | {end:%B %Y}'
    body = f'<p>Dear {escape(person["name"])},</p><p>Your annual sales and gross-profit target progress as at <b>{end:%d %B %Y}</b> is below. Fiscal year: <b>{escape(str(data["fiscal_year"]))}</b>.</p>'
    money = lambda n: f'{escape(data["currency"] or "")} {n:,.2f}' if n is not None else 'Not entered'
    summary = []
    for label, field in [('Sales revenue','sales'), ('Gross profit','gp')]:
        v = data[field]
        if v is None:
            summary.append((label,'Requires review','Unavailable','—','—'))
        else:
            summary.append((label,money(v['target']) if v['target'] > 0 else 'Not set',
                money(v['achieved']) if v['available'] else 'Not entered',
                f'{v["percent"]:.1f}%' if v['available'] and v['percent'] is not None else '—',
                money(v['remaining']) if v['available'] and v['target'] > 0 else '—'))
    body += table(['Measure','Annual target','Recorded achievement to date','Achievement %','Remaining target'], summary)
    body += '<h3>Monthly performance</h3>' + table(['Month','Invoiced sales','Invoiced GP','Data status'],
        [(m,money(s),money(g),status) for m,s,g,status in data['monthly']])
    for warning in data['warnings']:
        body += '<p><b>Data note:</b> ' + escape(warning) + '</p>'
    body += '<p>Targets are annual, not quarterly. Achievement uses Monthly Sales Performance Entry from the fiscal-year start through the previous month. Quotations and open pipeline are not included. Later months are excluded.</p><p>Please review your progress and ensure your monthly performance entries are up to date.</p><p>Regards,<br><b>BITS Secure IT</b></p>'
    return subject, body


def send_reports():
    now = datetime.now(TZ)
    if not site_profile() or not due(now) or not frappe.db.get_single_value('Selling Settings', FLAG):
        return 0
    end = cutoff(now.date())
    sent = 0
    for person in recipients():
        marker = key(person['user'], end)
        if frappe.db.exists('Notification Log', marker):
            continue
        frappe.db.savepoint('monthly_targets')
        try:
            subject, body = report(person, end)
            frappe.get_doc(dict(doctype='Notification Log', name=marker, type='Alert', for_user=person['user'],
                from_user='Administrator', subject=subject, email_content=body, document_type='User', document_name=person['user'])).db_insert()
            queue = frappe.sendmail(recipients=[person['user']], cc=person['cc'], expose_recipients='header', subject=subject,
                message=body, reference_doctype='User', reference_name=person['user'], message_id=f'<{marker}@bitssecureit.com>',
                delayed=True, now=False, add_unsubscribe_link=False, is_notification=True)
            if not queue:
                frappe.throw('No Email Queue entry was created.')
            frappe.db.commit()
            sent += 1
        except frappe.DuplicateEntryError:
            frappe.db.rollback(save_point='monthly_targets')
        except Exception:
            frappe.db.rollback(save_point='monthly_targets')
            frappe.log_error(title='Monthly sales target email failed', message=frappe.get_traceback())
    return sent


def install():
    if not site_profile():
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    if not frappe.get_meta('Selling Settings').has_field(FLAG):
        create_custom_fields({'Selling Settings':[dict(fieldname=FLAG, label='Monthly sales target progress reports', fieldtype='Check', default='0',
            description='1st of each month at 10:30 AM UTC+4; previous-month cutoff; CC reporting manager and Mohan.')]}, update=False)
        frappe.db.set_single_value('Selling Settings', FLAG, 1)
    from frappe.core.doctype.scheduled_job_type.scheduled_job_type import insert_single_event
    insert_single_event('Cron', METHOD, CRON)


@frappe.whitelist(methods=['GET'])
def page():
    frappe.only_for('System Manager')
    now = datetime.now(TZ)
    next_run = (now.date().replace(day=28) + timedelta(days=4)).replace(day=1)
    end = cutoff(next_run)
    content = []
    for person in recipients():
        subject, body = report(person, end)
        content.append(f'<h3>{escape(person["name"])}</h3><p>To: {escape(person["user"])} · CC: {escape(", ".join(person["cc"]))}</p><details><summary>{escape(subject)}</summary>{body}</details>')
    job = frappe.db.get_value('Scheduled Job Type', {'method':METHOD}, ['cron_format','stopped','last_execution'], as_dict=True)
    enabled = frappe.db.get_single_value('Selling Settings', FLAG)
    frappe.respond_as_web_page('Monthly sales target reports', f'<h2>{site_profile()["region"]} — Monthly Sales Target Progress</h2><p>Enabled: {bool(enabled)} · Next run: {next_run} 10:30 AM UTC+4 · Job: {escape(str(job))}</p><p>Read-only preview; current recorded values may change before the month closes. No emails sent by this page.</p>' + ''.join(content))
