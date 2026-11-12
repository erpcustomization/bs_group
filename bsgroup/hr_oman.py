"""Oman BS HR rollout: existing HR workflows, local policies and native access."""
from pathlib import Path
from urllib.parse import urlparse

import frappe

OMAN_HOSTS = {'erp-om.bitssecureit.com', 'erp-om.k.frappe.cloud'}


def is_oman():
    host = urlparse((getattr(frappe, 'conf', None) or {}).get('host_name') or '').hostname
    return host in OMAN_HOSTS or getattr(getattr(frappe, 'local', None), 'site', None) in OMAN_HOSTS


@frappe.whitelist()
def navigation_script():
    from bsgroup.hr_management import can_manage
    content = ''
    if is_oman() and can_manage():
        for name in ('hr_management', 'hr_organization', 'hr_monthly_review', 'hr_attendance', 'hr_sidebar'):
            content += '\n' + Path(frappe.get_app_path('bsgroup', 'public', 'js', name + '.js')).read_text()
    frappe.local.response.update(type='download', filename='oman_hr.js', filecontent=content,
        content_type='application/javascript', display_content_as='inline')


def boot_session(bootinfo):
    if not is_oman():
        return
    from bsgroup.hr_management import can_manage
    bootinfo.bs_hr_management = can_manage()


def configure_hooks(hooks):
    def append(mapping, key, value):
        prior = mapping.get(key, [])
        prior = [prior] if isinstance(prior, str) else list(prior)
        if value not in prior:
            prior.append(value)
        mapping[key] = prior
    append(hooks, 'app_include_js', '/api/method/bsgroup.hr_oman.navigation_script?v=20261111-hr-parity')
    append(hooks, 'boot_session', 'bsgroup.hr_oman.boot_session')
    events = hooks.setdefault('doc_events', {}).setdefault('Leave Allocation', {})
    for event in ('validate', 'before_update_after_submit'):
        append(events, event, 'bsgroup.hr_annual_allocation.validate_allocation')
    cron = hooks.setdefault('scheduler_events', {}).setdefault('cron', {})
    append(cron, '* * * * *', 'bsgroup.oman_attendance_email.send_reminders')
    append(cron, '2 9 * * 5', 'bsgroup.weekly_attendance_email.send_summaries')
