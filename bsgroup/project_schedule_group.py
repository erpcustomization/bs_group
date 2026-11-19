"""One regional group summary per task date, independent of private sends."""
from datetime import datetime, timedelta
from html import escape

import frappe

TARGET = 'Projects Team Oman'


def configuration():
    from bsgroup.hr_email import site_profile
    region = (site_profile() or {}).get('region')
    if region not in ('Oman', 'UAE'):
        return None
    return region, region.lower() + '_group', 'Projects Team ' + region


def compose(day, candidates, region='Oman'):
    from bsgroup.project_schedule_message import employee_section, introduction, footer, unique_rows
    parts = [introduction(day, region)]
    count = 0
    for candidate in candidates:
        if candidate['reason'] or not candidate['rows']:
            continue
        rows = unique_rows(candidate['rows'])
        if count:
            parts.append('<br/><hr/><br/>')
        parts.append(employee_section(candidate['employee_name'], rows))
        count += len(rows)
    parts.append(footer())
    return ''.join(parts), count


def dispatch(settings, day, candidates):
    from bsgroup.project_schedule import DELIVERY, identity, validate_endpoint
    config = configuration()
    if not config:
        return 'Group delivery disabled'
    region, prefix, target = config
    if not settings.get(prefix + '_enabled') or not settings.get(prefix + '_verified'):
        return 'Group delivery disabled'
    key = identity('GROUP:' + frappe.local.site, target, day)
    if frappe.db.exists(DELIVERY, key):
        return 'Already reserved'
    body, count = compose(day, candidates, region)
    if not count:
        return 'No eligible tasks'
    if len(body.encode('utf-8')) > 24000:
        frappe.throw('Group summary exceeds 24 KB. Review before sending.')
    url = settings.get_password(prefix + '_webhook')
    validate_endpoint(url)
    log = frappe.get_doc(dict(doctype=DELIVERY, delivery_target=target, schedule_date=day,
        task_count=count, status='Reserved', detail='Group summary reserved before HTTP; no automatic resend.'))
    try:
        log.insert(ignore_permissions=True, set_name=key)
        frappe.db.commit()
    except frappe.DuplicateEntryError:
        frappe.db.rollback()
        return 'Already reserved'
    import requests
    try:
        response = requests.post(url, json={'allocated_to': target, 'message': body,
            'idempotency_key': key, 'schedule_date': str(day)}, timeout=(10, 30), allow_redirects=False)
        status = 'Accepted' if 200 <= response.status_code < 300 else 'Failed'
        detail = f'HTTP {response.status_code}. Verify {target} delivery in Power Automate.'
    except requests.RequestException:
        status, detail = 'Uncertain', 'Check Power Automate history before any manual resend.'
    frappe.db.set_value(DELIVERY, key, dict(status=status, detail=detail))
    frappe.db.commit()
    return status


@frappe.whitelist(methods=['POST'])
def send_now():
    frappe.only_for('System Manager')
    from bsgroup.project_schedule import profile, SETTINGS, candidates
    config = configuration()
    if not config:
        frappe.throw('Group delivery is available only for Oman and UAE.')
    now = datetime.now(profile().TZ)
    day = now.date() + timedelta(days=1)
    settings = frappe.get_single(SETTINGS)
    return dict(result=dispatch(settings, day, candidates(day, settings, sent_day=now.date())),
        destination=config[2], schedule_date=str(day))
