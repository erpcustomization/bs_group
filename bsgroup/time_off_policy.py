"""Calendar-day company entitlements for dashboard Time Off requests."""
from datetime import date, timedelta
import frappe
from frappe.utils import getdate, flt

HAJJ = 'Hajj Leave - Half Pay'
STUDY = 'Study Leave - Unpaid'
MATERNITY_FULL = 'Maternity Leave - Full Pay'
MATERNITY_HALF = 'Maternity Leave - Half Pay'
SPECIAL_TYPES = (HAJJ, STUDY, MATERNITY_FULL, MATERNITY_HALF)
SPECIAL_CATEGORIES = ('Hajj Leave', 'Study Leave', 'Maternity Leave')


def study_eligible(joining, as_of):
    if not joining:
        return False
    joining, as_of = getdate(joining), getdate(as_of)
    try:
        anniversary = joining.replace(year=joining.year + 4)
    except ValueError:
        anniversary = joining.replace(year=joining.year + 4, day=28)
    return as_of > anniversary


def calendar_parts(category, start, end, period_start=None):
    start, end = getdate(start), getdate(end)
    if end < start:
        raise ValueError('End date must be on or after the start date.')
    parts = []
    if category == 'Maternity Leave':
        if not period_start:
            raise ValueError('Enter the first day of this maternity period, including for continuation requests.')
        origin = getdate(period_start)
        if start < origin or end > origin + timedelta(days=59):
            raise ValueError('Maternity leave must fall within days 1 to 60 of the same maternity period.')
        for leave_type, lower, upper in ((MATERNITY_FULL,origin,origin+timedelta(days=44)),(MATERNITY_HALF,origin+timedelta(days=45),origin+timedelta(days=59))):
            a,b=max(start,lower),min(end,upper)
            if a<=b:
                parts.append(dict(leave_type=leave_type,from_date=str(a),to_date=str(b),days=(b-a).days+1,half_day=0,
                                  allocation_from=str(lower),allocation_to=str(upper),entitlement=(upper-lower).days+1))
    else:
        if category not in ('Hajj Leave','Study Leave'):
            raise ValueError('Unknown leave category.')
        limit=15 if category=='Hajj Leave' else 10
        leave_type=HAJJ if category=='Hajj Leave' else STUDY
        a=start
        while a<=end:
            b=min(end,date(a.year,12,31));days=(b-a).days+1
            if days>limit:
                raise ValueError(f'{category} is limited to {limit} calendar days per calendar year.')
            parts.append(dict(leave_type=leave_type,from_date=str(a),to_date=str(b),days=days,half_day=0,
                              allocation_from=str(date(a.year,1,1)),allocation_to=str(date(a.year,12,31)),entitlement=limit))
            a=b+timedelta(days=1)
    return parts


def used_days(employee, leave_type, start, end, exclude=None):
    filters={'employee':employee,'leave_type':leave_type,'docstatus':['<',2],
             'status':['in',['Open','Approved']],'from_date':['<=',str(end)],'to_date':['>=',str(start)]}
    if exclude:
        filters['name']=['!=',exclude]
    rows=frappe.get_all('Leave Application',filters=filters,fields=['from_date','to_date','half_day','half_day_date'])
    total=0
    for row in rows:
        a,b=max(getdate(row.from_date),getdate(start)),min(getdate(row.to_date),getdate(end))
        total+=(b-a).days+1
        if row.half_day and row.half_day_date and a<=getdate(row.half_day_date)<=b:
            total-=.5
    return total


def check_type(leave_type):
    row=frappe.db.get_value('Leave Type',leave_type,['is_lwp','is_ppl','fraction_of_daily_salary_per_leave','include_holiday'],as_dict=True)
    half=leave_type in (HAJJ,MATERNITY_HALF)
    if not row or not row.include_holiday or bool(row.is_lwp)!=(leave_type==STUDY) or bool(row.is_ppl)!=half or (half and flt(row.fraction_of_daily_salary_per_leave)!=.5):
        frappe.throw('HR must complete the calendar-day/pay configuration for '+leave_type+'.')


def plan(employee,category,start,end,period_start=None):
    from bsgroup.dashboard_leave import dubai_today
    joining=frappe.db.get_value('Employee',employee,'date_of_joining')
    if category=='Study Leave' and not study_eligible(joining,dubai_today()):
        frappe.throw('Study leave is available only after more than four years of service. Please ask HR to check your joining date if needed.')
    try:
        parts=calendar_parts(category,start,end,period_start)
    except ValueError as exc:
        frappe.throw(str(exc))
    for part in parts:
        check_type(part['leave_type'])
        already=used_days(employee,part['leave_type'],part['allocation_from'],part['allocation_to'])
        if already+part['days']>part['entitlement']:
            frappe.throw(f"{category}: pending and approved requests already use {already:g} days of the {part['entitlement']}-day allowance.")
    if category=='Maternity Leave':
        # Earlier requests without this period marker need an HR reconciliation.
        legacy=frappe.db.exists('Leave Application',{'employee':employee,'leave_type':'Maternity Leave','docstatus':['<',2],
            'status':['in',['Open','Approved']],'from_date':['<=',str(getdate(period_start)+timedelta(days=59))],'to_date':['>=',str(period_start)]})
        if legacy:
            frappe.throw('An existing maternity request overlaps this period. Please ask HR to reconcile it before applying again.')
        other=frappe.get_all('Leave Application',filters={'employee':employee,'leave_type':['in',[MATERNITY_FULL,MATERNITY_HALF]],
            'docstatus':['<',2],'status':['in',['Open','Approved']]},fields=['custom_maternity_period_start'])
        origin=getdate(period_start)
        for row in other:
            if row.custom_maternity_period_start:
                old=getdate(row.custom_maternity_period_start)
                if old!=origin and abs((old-origin).days)<60:
                    frappe.throw('Use the original maternity period start date for continuation requests; overlapping periods are not allowed.')
    return parts


def automatic_entitlements_enabled():
    value = frappe.conf.get('bs_auto_special_leave_allocations')
    return value is True or (type(value) is int and value == 1)


def ensure_entitlements(employee,parts):
    """Provision only the fixed new policy allowances; never modify existing allocations.

    The caller holds the employee row lock and has checked own-employee access,
    leave eligibility, quotas, and the previewed plan. Application approvals stay Open.
    """
    for part in parts:
        leave_type=part['leave_type']
        if leave_type==STUDY:
            continue
        if leave_type not in (HAJJ,MATERNITY_FULL,MATERNITY_HALF):
            frappe.throw('Unexpected entitlement type.')
        filters={'employee':employee,'leave_type':leave_type,'docstatus':['<',2],
                 'from_date':['<=',part['to_date']],'to_date':['>=',part['from_date']]}
        existing=frappe.get_all('Leave Allocation',filters=filters,fields=['name','from_date','to_date','docstatus'])
        if existing:
            if len(existing)!=1 or existing[0].docstatus!=1 or getdate(existing[0].from_date)>getdate(part['from_date']) or getdate(existing[0].to_date)<getdate(part['to_date']):
                frappe.throw('An existing or draft leave allocation needs HR review; no allowance was changed.')
            continue
        if not automatic_entitlements_enabled():
            frappe.throw('HR must allocate this paid leave allowance before you apply. Automatic policy allocations are not enabled.')
        allocation=frappe.new_doc('Leave Allocation')
        allocation.update(dict(employee=employee,leave_type=leave_type,from_date=part['allocation_from'],to_date=part['allocation_to'],
                               new_leaves_allocated=part['entitlement'],carry_forward=0))
        allocation.flags.ignore_permissions=True
        allocation.insert(ignore_permissions=True)
        allocation.submit()
        allocation.add_comment('Info','Company Time Off policy allowance: '+leave_type+'. Created for the employee request; leave approval is still required.')


def validate(doc):
    if doc.leave_type not in SPECIAL_TYPES:
        return
    check_type(doc.leave_type)
    previous=doc.get_doc_before_save()
    if previous and previous.get('custom_maternity_period_start') and getdate(previous.custom_maternity_period_start)!=getdate(doc.get('custom_maternity_period_start')):
        frappe.throw('The maternity period start cannot be changed. Ask HR to cancel and replace an incorrect request.')
    if doc.is_new() and not doc.flags.get('time_off_request'):
        frappe.throw('Please use Time Off on the dashboard for this leave type so eligibility, annual limits and pay portions are checked.')
    if doc.status in ('Rejected','Cancelled') or doc.docstatus==2:
        return
    category = 'Hajj Leave' if doc.leave_type==HAJJ else 'Study Leave' if doc.leave_type==STUDY else 'Maternity Leave'
    from bsgroup.dashboard_leave import dubai_today
    if category=='Study Leave' and not study_eligible(frappe.db.get_value('Employee',doc.employee,'date_of_joining'),dubai_today()):
        frappe.throw('Study leave requires more than four years of service.')
    try:
        parts=calendar_parts(category,doc.from_date,doc.to_date,doc.get('custom_maternity_period_start'))
    except ValueError as exc:
        frappe.throw(str(exc))
    if len(parts)!=1 or parts[0]['leave_type']!=doc.leave_type or doc.half_day:
        frappe.throw('This request must use the calendar-day/pay split calculated by Time Off.')
    part=parts[0]
    if used_days(doc.employee,doc.leave_type,part['allocation_from'],part['allocation_to'],doc.name)+flt(doc.total_leave_days)>part['entitlement']:
        frappe.throw('Pending and approved requests would exceed this leave allowance.')


def entitlements_ready(employee,parts):
    if automatic_entitlements_enabled():
        return True
    for part in parts:
        if part['leave_type']==STUDY:
            continue
        if not frappe.db.exists('Leave Allocation',{'employee':employee,'leave_type':part['leave_type'],'docstatus':1,
                'from_date':['<=',part['from_date']],'to_date':['>=',part['to_date']]}):
            return False
    return True
