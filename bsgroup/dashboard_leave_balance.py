"""Read-only own-user balance, with an explicitly labelled private import reference.

The reference never grants leave or changes the native HRMS approval calculation.
Employee balances and user identities are not shipped with application assets.
"""
import json
from decimal import Decimal, InvalidOperation

import frappe
from frappe.utils import flt
from bsgroup.dashboard_leave import dubai_today

SOURCE_FILE = 'annual-leave-dashboard-2026.json'
# Pin the reviewed private upload; another user's similarly named upload is not a source.
SOURCE_FILE_ID = 'ae27d69db2'
ANNUAL = 'Annual Vacation'


def reference_row(payload, user, today):
    if not payload.get('valid_from', '') <= today <= payload.get('valid_to', ''):
        return None
    rows = [r for r in payload.get('rows', []) if r.get('user') == user]
    if len(rows) != 1:
        return None
    value = str(rows[0].get('current', '')).strip()
    if value not in ('-', '–'):
        try:
            if not Decimal(value).is_finite():
                return None
        except InvalidOperation:
            return None
    return value


def imported_reference(user, today):
    files = frappe.get_all('File', filters={'name': SOURCE_FILE_ID, 'file_name': SOURCE_FILE, 'is_private': 1},
                          fields=['name'], order_by='creation desc', limit_page_length=1)
    if not files:
        return None
    content = frappe.get_doc('File', files[0].name).get_content()
    if isinstance(content, bytes):
        content = content.decode('utf-8-sig')
    return reference_row(json.loads(content.lstrip('\ufeff')), user, today)


@frappe.whitelist()
def context():
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw('Please sign in.', frappe.PermissionError)
    today = str(dubai_today())
    employees = frappe.get_all('Employee', filters={'user_id': user, 'status': 'Active'},
                               fields=['name'], limit_page_length=2)
    if len(employees) == 1:
        from hrms.hr.doctype.leave_application.leave_application import get_leave_details
        details = get_leave_details(employees[0].name, today)
        allocation = details.get('leave_allocation', {}).get(ANNUAL)
        if allocation is not None:
            balance = flt(allocation.get('remaining_leaves'))
            pending = flt(allocation.get('leaves_pending_approval'))
            return dict(balance=balance, pending=pending, available=max(0, balance-pending), source='hrms')
    reference = imported_reference(user, today)
    return dict(balance=reference, source='reference' if reference is not None else 'unavailable',
                employee_linked=len(employees) == 1)
