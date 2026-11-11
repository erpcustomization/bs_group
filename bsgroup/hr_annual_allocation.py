"""Capped annual allocations using native HRMS saves, ledger and permissions."""
from decimal import Decimal, InvalidOperation
import frappe
from frappe.utils import flt, getdate
from bsgroup.dashboard_leave import dubai_today
from bsgroup.hr_management import _guard

ANNUAL = 'Annual Vacation'
LIMIT = 26


def allocation_limit():
    # The UAE-specific 26-day decision must not replace Oman's HR policy.
    from urllib.parse import urlparse
    host = urlparse((getattr(frappe, 'conf', None) or {}).get('host_name') or '').hostname
    site = getattr(getattr(frappe, 'local', None), 'site', None)
    if host in {'erp-om.bitssecureit.com', 'erp-om.k.frappe.cloud'} or site == 'erp-om.k.frappe.cloud':
        native = flt(frappe.get_cached_value('Leave Type', ANNUAL, 'max_leaves_allowed'))
        return native if native > 0 else None
    return LIMIT


def allocation_days(value):
    try:
        days = Decimal(str(value))
    except (InvalidOperation, ValueError):
        frappe.throw('Enter a valid number of annual-leave days.')
    limit = allocation_limit()
    if not days.is_finite() or days < 0 or (limit is not None and days > Decimal(str(limit))):
        message = f'between 0 and {limit:g} days' if limit is not None else 'a non-negative number of days'
        frappe.throw(f'Annual-leave allocation must be {message}, including carried-forward days.')
    return float(days)


def validate_allocation(doc, method=None):
    if doc.leave_type != ANNUAL or doc.docstatus == 2:
        return
    total = allocation_days(flt(doc.new_leaves_allocated) + flt(doc.unused_leaves))
    # Never permit direct edits of the derived total without corresponding ledger entries.
    doc.total_leaves_allocated = total
    previous = doc.get_doc_before_save()
    if previous and previous.docstatus == 1 and total < flt(previous.total_leaves_allocated):
        from hrms.hr.doctype.leave_application.leave_application import get_leave_details
        at = max(getdate(doc.from_date), min(getdate(dubai_today()), getdate(doc.to_date)))
        current = get_leave_details(doc.employee, str(at)).get('leave_allocation', {}).get(ANNUAL)
        if current is None:
            frappe.throw('The current HRMS balance could not be verified. Review the allocation in HRMS.')
        available_after = flt(current.get('remaining_leaves')) + total - flt(previous.total_leaves_allocated)
        if available_after < flt(current.get('leaves_pending_approval')) - 0.00001:
            frappe.throw('This allocation would be below leave already used, approved or reserved by pending requests. Review those requests first.')


@frappe.whitelist()
def context(employee, date=None):
    _guard()
    emp = frappe.get_doc('Employee', employee)
    emp.check_permission('read')
    at = str(getdate(date or dubai_today()))
    rows = frappe.get_list('Leave Allocation', filters={'employee': employee, 'leave_type': ANNUAL,
        'docstatus': ['<', 2], 'from_date': ['<=', at], 'to_date': ['>=', at]},
        fields=['name', 'modified', 'docstatus', 'from_date', 'to_date', 'new_leaves_allocated',
                'unused_leaves', 'total_leaves_allocated', 'expired'], limit_page_length=0)
    for row in rows:
        row['can_edit'] = not row.expired and frappe.has_permission('Leave Allocation', 'write', doc=row.name)
    draft = frappe.new_doc('Leave Allocation')
    draft.employee, draft.company, draft.leave_type = emp.name, emp.company, ANNUAL
    return dict(employee=emp.name, employee_name=emp.employee_name, company=emp.company,
                allocations=rows, limit=allocation_limit(), can_create=frappe.has_permission('Leave Allocation', 'create', doc=draft), date=at)


@frappe.whitelist(methods=['POST'])
def save(allocation, total_days, modified, reason):
    _guard()
    target = allocation_days(total_days)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        frappe.throw('Enter the reason for this annual-leave allocation change (up to 1,000 characters).')
    doc = frappe.get_doc('Leave Allocation', allocation, for_update=True)
    doc.check_permission('read')
    doc.check_permission('write')
    if doc.leave_type != ANNUAL or doc.docstatus != 1 or doc.expired:
        frappe.throw('Open the active submitted annual-leave allocation to edit it.')
    if str(doc.modified) != str(modified):
        frappe.throw('This allocation was updated by someone else. Reopen it before saving.')
    old = flt(doc.total_leaves_allocated)
    if target < flt(doc.unused_leaves):
        frappe.throw('The target is below carried-forward days. HR must review the previous allocation first.')
    doc.new_leaves_allocated = target - flt(doc.unused_leaves)
    doc.total_leaves_allocated = target
    # Native save creates a balancing Leave Ledger Entry and retains Version history.
    doc.save()
    from frappe.utils import escape_html
    doc.add_comment('Info', f'Annual allocation changed from {old:g} to {target:g} days through BS HR. Reason: {escape_html(reason.strip())}')
    return dict(name=doc.name, allocated=doc.total_leaves_allocated)
