"""One combined Oman group summary per task date, independent of private sends."""
from datetime import datetime, timedelta
from html import escape

import frappe

TARGET = 'Projects Team Oman'


def compose(day, candidates):
    parts = [f'<p><b>These are the tasks scheduled for tomorrow ({day:%d %B %Y}) — Oman.</b></p>']
    count = 0
    for candidate in candidates:
        if candidate['reason'] or not candidate['rows']:
            continue
        parts.append('<h3>' + escape(candidate['employee_name']) + '</h3><ul>')
        seen = set()
        for row in candidate['rows']:
            if row['task'] in seen:
                continue
            seen.add(row['task'])
            count += 1
            parts.append('<li><b>' + escape(row['project_title']) + '</b>: '
                + escape(row['task_title']) + ' (' + escape(row['task']) + ')'
                + (' — due ' + escape(row['due_date']) if row['due_date'] else '')
                + (' — <b>Overdue</b>' if row['status'] == 'Overdue' else '') + '</li>')
        parts.append('</ul>')
    parts.append('<p>Please update your daily work and task status in the project’s Project Plan.</p>')
    return ''.join(parts), count


def dispatch(settings, day, candidates):
    from bsgroup.hr_email import is_oman
    from bsgroup.project_schedule import DELIVERY, identity, validate_endpoint
    if not is_oman() or not settings.get('oman_group_enabled') or not settings.get('oman_group_verified'):
        return 'Group delivery disabled'
    key = identity('GROUP:' + frappe.local.site, TARGET, day)
    if frappe.db.exists(DELIVERY, key):
        return 'Already reserved'
    body, count = compose(day, candidates)
    if not count:
        return 'No eligible tasks'
    if len(body.encode('utf-8')) > 24000:
        frappe.throw('Oman group summary exceeds 24 KB. Review before sending.')
    url = settings.get_password('oman_group_webhook')
    validate_endpoint(url)
    log = frappe.get_doc(dict(doctype=DELIVERY, delivery_target=TARGET, schedule_date=day,
        task_count=count, status='Reserved', detail='Group summary reserved before HTTP; no automatic resend.'))
    try:
        log.insert(ignore_permissions=True, set_name=key)
        frappe.db.commit()
    except frappe.DuplicateEntryError:
        frappe.db.rollback()
        return 'Already reserved'
    import requests
    try:
        response = requests.post(url, json={'allocated_to': TARGET, 'message': body,
            'idempotency_key': key, 'schedule_date': str(day)}, timeout=(10, 30), allow_redirects=False)
        status = 'Accepted' if 200 <= response.status_code < 300 else 'Failed'
        detail = f'HTTP {response.status_code}. Verify Projects Team Oman delivery in Power Automate.'
    except requests.RequestException:
        status, detail = 'Uncertain', 'Check Power Automate history before any manual resend.'
    frappe.db.set_value(DELIVERY, key, dict(status=status, detail=detail))
    frappe.db.commit()
    return status


@frappe.whitelist(methods=['POST'])
def send_now():
    frappe.only_for('System Manager')
    from bsgroup.project_schedule import profile, SETTINGS, candidates
    from bsgroup.hr_email import is_oman
    if not is_oman():
        frappe.throw('This group delivery is available only for Oman.')
    now = datetime.now(profile().TZ)
    day = now.date() + timedelta(days=1)
    settings = frappe.get_single(SETTINGS)
    return dict(result=dispatch(settings, day, candidates(day, settings, sent_day=now.date())),
        destination=TARGET, schedule_date=str(day))
