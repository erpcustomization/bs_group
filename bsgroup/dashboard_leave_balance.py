"""Read-only own-user balance, with an explicitly labelled private import reference.

The reference never grants leave or changes the native HRMS approval calculation.
Employee balances and user identities are not shipped with application assets.
"""
import json
from decimal import Decimal, InvalidOperation

import frappe
from frappe.utils import flt, getdate
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


def request_status(source, balance, available=0):
    if source == 'hrms':
        return 'available' if available > 0 else 'empty'
    if source == 'reference':
        if str(balance) in ('-', '–'):
            return 'unknown'
        return 'empty' if Decimal(str(balance)) <= 0 else 'pending'
    return 'unknown'


@frappe.whitelist()
def context(date=None):
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw('Please sign in.', frappe.PermissionError)
    today = str(getdate(date or dubai_today()))
    employees = frappe.get_all('Employee', filters={'user_id': user, 'status': 'Active'},
                               fields=['name'], limit_page_length=2)
    if len(employees) == 1:
        from hrms.hr.doctype.leave_application.leave_application import get_leave_details
        details = get_leave_details(employees[0].name, today)
        allocation = details.get('leave_allocation', {}).get(ANNUAL)
        if allocation is not None:
            balance = flt(allocation.get('remaining_leaves'))
            pending = flt(allocation.get('leaves_pending_approval'))
            available = max(0, balance-pending)
            return dict(balance=balance, pending=pending, available=available, source='hrms',
                        employee_linked=True, annual_status=request_status('hrms', balance, available))
    reference = imported_reference(user, today)
    source = 'reference' if reference is not None else 'unavailable'
    return dict(balance=reference, source=source, employee_linked=len(employees) == 1,
                annual_status=request_status(source, reference) if reference is not None else
                ('empty' if len(employees) == 1 else 'unknown'))
