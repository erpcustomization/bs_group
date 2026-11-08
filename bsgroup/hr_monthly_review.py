"""Read-only HR evidence for monthly attendance/leave review. Never issues warnings."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import frappe
from frappe.utils import getdate, get_datetime, flt
from bsgroup.hr_management import _guard
from bsgroup.hr_attendance import month_bounds, _rows

TZ = ZoneInfo('Asia/Dubai')
ANNUAL = 'Annual Vacation'
PROPOSED_RULES = [
    dict(key='late', title='Late-arrival warning', trigger='3 completed late-arrival days in a calendar month',
         delivery='Employee; once per month after the threshold is reached',
         safeguard='Exclude holidays, approved leave/on-duty dates and incomplete or conflicting punches.'),
    dict(key='absence', title='Absence review', trigger='1 submitted HR Absent day without approved leave or conflicting punches',
         delivery='HR review first; employee warning only after HR confirms the absence',
         safeguard='Missing check-in alone never triggers an absence warning.'),
    dict(key='annual', title='Annual-leave planning reminder', trigger='10 or more available annual-leave days',
         delivery='Employee; once per month',
         safeguard='Use current HRMS balance after pending requests. Unknown/import-reference balances require HR review.'),
    dict(key='after_hours', title='Manager after-hours review', trigger='30 or more recorded minutes after 6 PM on a day',
         delivery='Recorded reporting manager; one daily digest for the previous day',
         safeguard='Include the exact IN/OUT pairs. Request business reason/authorization; do not approve overtime or pay automatically.'),
]


def paired_intervals(logs, now):
    """Only unambiguous completed pairs contribute hours; keep every raw punch."""
    pairs, issues = [], set()
    active = None
    ambiguous = False
    for log in sorted(logs, key=lambda x: x['stamp']):
        stamp, kind = log['stamp'], log.get('log_type')
        if stamp > now:
            continue
        if kind == 'IN':
            if active is not None:
                issues.update((active.date(), stamp.date()))
                ambiguous = True
            else:
                active, ambiguous = stamp, False
        elif kind == 'OUT':
            if active is None:
                issues.add(stamp.date())
            elif not ambiguous and timedelta(0) < stamp-active <= timedelta(days=1):
                pairs.append((active, stamp))
            else:
                issues.update((active.date(), stamp.date()))
            active, ambiguous = None, False
        else:
            issues.add(stamp.date())
            if active:
                ambiguous = True
    if active:
        issues.add(active.date())
    return pairs, issues


def minutes_between(pairs, start, end):
    return round(sum(max(0, (min(b, end)-max(a, start)).total_seconds()) for a,b in pairs)/60, 2)


def effective_holiday(assignments, employee, company, day, fallback=None):
    groups=[[a for a in assignments if a['assigned_to']==who] for who in (employee,company)]
    for group in groups:
        current=[a for a in group if getdate(a['from_date'])<=day]
        if current:return max(current,key=lambda a:getdate(a['from_date']))['holiday_list']
    for group in groups:
        if group:return min(group,key=lambda a:getdate(a['from_date']))['holiday_list']
    return fallback


def day_metrics(day, now, pairs, punches, issues, schedule=None, holiday=False, leave=0, duty=0, attendance=None):
    attendance = attendance or []
    start, end = schedule if schedule else (None, None)
    lower = datetime.combine(day, time(), TZ)
    after_start = datetime.combine(day, time(18), TZ)
    after = minutes_between(pairs, after_start, min(lower+timedelta(days=1), now)) if day <= now.date() else 0
    raw = [r for r in punches if r['stamp'].date()==day and r['stamp']<=now]
    first = next((r['stamp'] for r in sorted(raw,key=lambda x:x['stamp']) if r.get('log_type')=='IN'),None)
    last = next((r['stamp'] for r in sorted(raw,key=lambda x:x['stamp'],reverse=True) if r.get('log_type')=='OUT'),None)
    scheduled = round((end-start).total_seconds()/60,2) if start and not holiday else 0 if holiday else None
    due = round(max(0,(min(now,end)-start).total_seconds())/60*(1-leave),2) if start and not holiday else 0 if holiday else None
    office = minutes_between(pairs,start,end) if start else None
    flags = []
    if not schedule: flags.append('Shift or holiday calendar unavailable')
    if day in issues: flags.append('Incomplete or ambiguous punches')
    hr_absent = any(r.get('status')=='Absent' and r.get('docstatus')==1 for r in attendance)
    if hr_absent and (raw or leave or duty or holiday): flags.append('HR absence conflicts with other records')
    if any(r.get('docstatus')==0 for r in attendance): flags.append('Draft HR attendance')
    eligible = bool(start and day<=now.date() and not holiday and not leave and not duty)
    # Overnight shifts need their own arrival window; don't label daytime punches late.
    if start and end.date()!=start.date():
        eligible=False
        flags.append('Overnight shift: review arrival separately')
    complete = bool(first and any(a==first for a,b in pairs) and day not in issues)
    late_minutes = round(max(0,(first-start).total_seconds())/60,2) if eligible and complete else 0
    missing = bool(eligible and now>=end and not first)
    return dict(date=str(day), first_in=first.strftime('%H:%M:%S') if first else None,
                last_out=last.strftime('%H:%M:%S') if last else None, scheduled_minutes=scheduled,
                expected_due_minutes=due, office_minutes=office, after_minutes=after,
                after_day=int(after>0), late_minutes=late_minutes if start else None, late_day=int(late_minutes>0) if start else None,
                leave_days=leave if day<=now.date() else 0, on_duty=duty, holiday=holiday,
                hr_absent=int(hr_absent and day<=now.date()), missing_checkin=int(missing) if start else None,
                flags=flags, punches=[{k:v for k,v in r.items() if k!='stamp'} for r in raw],
                attendance=attendance, future=day>now.date(),
                shift_start=start.strftime('%H:%M') if start else None,
                shift_end=end.strftime('%H:%M') if end else None)


def _annual(employee, at, restricted):
    needed=('Leave Allocation','Leave Application','Leave Ledger Entry')
    if any(not frappe.has_permission(dt,'read') for dt in needed):
        return dict(source='restricted',note='Annual-leave records are restricted by existing access.')
    from hrms.hr.doctype.leave_application.leave_application import get_leave_details
    try:
        details=get_leave_details(employee.name,str(at))
    except frappe.PermissionError:
        return dict(source='restricted',note='Annual-leave details are restricted by HRMS.')
    allocation=details.get('leave_allocation',{}).get(ANNUAL)
    if allocation is not None:
        balance=flt(allocation.get('remaining_leaves')); pending=flt(allocation.get('leaves_pending_approval'))
        return dict(source='hrms',allocated=flt(allocation.get('total_leaves')),balance=balance,
                    available=max(0,balance-pending),pending=pending,
                    used_in_allocation=flt(allocation.get('leaves_taken')),as_of=str(at))
    # Imported negative/unknown values remain visible only with access to the private source.
    from bsgroup.dashboard_leave_balance import SOURCE_FILE_ID, imported_reference
    if employee.user_id and frappe.has_permission('File','read',doc=SOURCE_FILE_ID):
        ref=imported_reference(employee.user_id,str(at))
        if ref is not None:
            return dict(source='reference',balance=ref,as_of=str(at),note='Excel reference; no live allocation. Not an available balance.')
    return dict(source='unavailable',note='No annual-leave allocation for this date.')


@frappe.whitelist()
def report(month, employee=None):
    _guard()
    start,end=month_bounds(month)
    now=datetime.now(TZ)
    if not frappe.has_permission('Employee','read'):
        frappe.throw('Employee records are restricted.',frappe.PermissionError)
    employees=frappe.get_list('Employee',fields=['name','employee_name','company','department','reports_to',
        'user_id','company_email','status','date_of_joining','relieving_date','default_shift','holiday_list'],
        order_by='employee_name asc',limit_page_length=0)
    employees=[e for e in employees if (not e.date_of_joining or getdate(e.date_of_joining)<end)
        and (not e.relieving_date or getdate(e.relieving_date)>=start)
        and (e.status=='Active' or e.relieving_date)]
    if employee:
        if employee not in {e.name for e in employees}:
            frappe.throw('Employee is outside your permitted HR view.',frappe.PermissionError)
        employees=[e for e in employees if e.name==employee]
    restricted=[]
    if not employees:return dict(month=month,employees=[],restricted=[],rules=PROPOSED_RULES,automation_enabled=False)
    names=[e.name for e in employees]
    site=ZoneInfo(frappe.utils.get_system_timezone())
    lower=datetime.combine(start-timedelta(days=1),time(),TZ).astimezone(site).replace(tzinfo=None)
    upper=datetime.combine(end+timedelta(days=1),time(),TZ).astimezone(site).replace(tzinfo=None)
    logs=_rows('Employee Checkin',['name','employee','time','log_type'],
        [['employee','in',names],['time','>=',lower],['time','<',upper]],restricted)
    overlap=[['employee','in',names],['docstatus','!=',2],['from_date','<',str(end)],['to_date','>=',str(start)]]
    leaves=_rows('Leave Application',['name','employee','from_date','to_date','leave_type','status','docstatus','half_day','half_day_date'],overlap,restricted)
    duty=_rows('Attendance Request',['name','employee','from_date','to_date','reason','docstatus','half_day','half_day_date'],
        overlap+[['reason','in',['On Duty','Work From Home']]],restricted)
    attendance=_rows('Attendance',['name','employee','attendance_date','status','docstatus'],
        [['employee','in',names],['attendance_date','>=',str(start)],['attendance_date','<',str(end)],['docstatus','!=',2]],restricted)
    assignments=_rows('Shift Assignment',['employee','shift_type','start_date','end_date'],
        [['employee','in',names],['docstatus','=',1],['status','=','Active'],['start_date','<',str(end)]],restricted)
    assignments.sort(key=lambda a:str(a.start_date),reverse=True)
    shift_names={e.default_shift for e in employees}|{a.shift_type for a in assignments}
    shifts={}
    for name in shift_names-{None,''}:
        if frappe.has_permission('Shift Type','read',doc=name):shifts[name]=frappe.get_doc('Shift Type',name)
        elif 'Shift Type' not in restricted:restricted.append('Shift Type')
    company_holidays={}
    for company in {e.company for e in employees}:
        if frappe.has_permission('Company','read',doc=company):
            company_holidays[company]=frappe.get_doc('Company',company).get('default_holiday_list')
    holiday_assignments=[]
    if frappe.db.exists('DocType','Holiday List Assignment'):
        holiday_assignments=_rows('Holiday List Assignment',['assigned_to','holiday_list','from_date'],
            [['assigned_to','in',names+list({e.company for e in employees})],['docstatus','=',1]],restricted)
    list_names={e.holiday_list for e in employees}|{s.holiday_list for s in shifts.values()}|set(company_holidays.values())
    list_names|={a.holiday_list for a in holiday_assignments}
    holidays={};holiday_coverage={}
    for name in list_names-{None,''}:
        if frappe.has_permission('Holiday List','read',doc=name):
            holiday_doc=frappe.get_doc('Holiday List',name)
            holidays[name]={getdate(h.holiday_date):h.description for h in holiday_doc.holidays}
            holiday_coverage[name]=(getdate(holiday_doc.from_date),getdate(holiday_doc.to_date))
        elif 'Holiday List' not in restricted:restricted.append('Holiday List')
    from bsgroup.attendance_widget import shift_bounds
    from hrms.hr.doctype.leave_application.leave_application import get_number_of_leave_days
    results=[]
    for emp in employees:
        elog=[dict(r, time=str(r.time),stamp=get_datetime(r.time).replace(tzinfo=site).astimezone(TZ)) for r in logs if r.employee==emp.name]
        pairs,issues=paired_intervals(elog,now)
        eleaves=[r for r in leaves if r.employee==emp.name]
        eduty=[r for r in duty if r.employee==emp.name and r.docstatus==1]
        eassign=[r for r in assignments if r.employee==emp.name]
        daily=[]; day=start; annual_taken=0; leave_total=0
        while day<end:
            if (emp.date_of_joining and day<getdate(emp.date_of_joining)) or (emp.relieving_date and day>getdate(emp.relieving_date)):
                day+=timedelta(days=1);continue
            assigned=next((a.shift_type for a in eassign if getdate(a.start_date)<=day and (not a.end_date or getdate(a.end_date)>=day)),emp.default_shift)
            shift=shifts.get(assigned)
            fallback=emp.holiday_list or company_holidays.get(emp.company)
            holiday_name=(shift.holiday_list if shift else None) or effective_holiday(holiday_assignments,emp.name,emp.company,day,fallback)
            covered=holiday_name in holiday_coverage and holiday_coverage[holiday_name][0]<=day<=holiday_coverage[holiday_name][1]
            schedule=shift_bounds(day,shift) if shift and covered and not {'Shift Assignment','Holiday List Assignment'}&set(restricted) else None
            off=day in holidays.get(holiday_name,{})
            approved=[r for r in eleaves if r.docstatus==1 and r.status=='Approved' and getdate(r.from_date)<=day<=getdate(r.to_date)]
            portion=0; annual_portion=0
            for leave in approved:
                half=bool(leave.half_day and (not leave.half_day_date or getdate(leave.half_day_date)==day))
                amount=max(0,flt(get_number_of_leave_days(emp.name,leave.leave_type,day,day,
                    half_day=int(half),half_day_date=day if half else None,leave_application=leave.name)))
                portion=max(portion,min(1,amount))
                if leave.leave_type==ANNUAL:annual_portion=max(annual_portion,min(1,amount))
            duty_portion=max([.5 if r.half_day and (not r.half_day_date or getdate(r.half_day_date)==day) else 1
                for r in eduty if getdate(r.from_date)<=day<=getdate(r.to_date)]+[0])
            d=day_metrics(day,now,pairs,elog,issues,schedule,off,portion,duty_portion,
                [dict(r) for r in attendance if r.employee==emp.name and getdate(r.attendance_date)==day])
            d['shift']=assigned;d['leave_records']=[dict(r) for r in eleaves if getdate(r.from_date)<=day<=getdate(r.to_date)]
            if 'Employee Checkin' in restricted:
                for k in ('office_minutes','after_minutes','after_day','late_minutes','late_day','missing_checkin'):d[k]=None
            if 'Attendance' in restricted:d['hr_absent']=None
            if 'Leave Application' in restricted:
                d['leave_days']=None;d['expected_due_minutes']=None;d['late_day']=None;d['late_minutes']=None;d['missing_checkin']=None
            if 'Attendance Request' in restricted:
                d['late_day']=None;d['late_minutes']=None;d['missing_checkin']=None
            daily.append(d)
            if day<=now.date():annual_taken+=annual_portion;leave_total+=portion
            day+=timedelta(days=1)
        def total(key):
            values=[d[key] for d in daily]
            return None if any(v is None for v in values) else round(sum(values),2)
        balance_at=min(end-timedelta(days=1),now.date())
        annual=_annual(emp,balance_at,restricted)
        manager=None
        if emp.reports_to and frappe.has_permission('Employee','read',doc=emp.reports_to):
            m=frappe.get_doc('Employee',emp.reports_to)
            manager=dict(name=m.name,employee_name=m.employee_name,email=m.company_email or m.user_id)
        results.append(dict(employee=emp.name,employee_name=emp.employee_name,company=emp.company,department=emp.department,
            email=emp.company_email or emp.user_id,manager=manager,annual=annual,
            annual_taken=round(annual_taken,2) if 'Leave Application' not in restricted else None,
            leave_taken=round(leave_total,2) if 'Leave Application' not in restricted else None,
            totals={k:total(k) for k in ('scheduled_minutes','expected_due_minutes','office_minutes','after_minutes','after_day','late_minutes','late_day','hr_absent','missing_checkin')},
            review_days=sum(bool(d['flags']) for d in daily if not d['future']),days=daily))
    return dict(month=month,as_of=now.isoformat(),employees=results,restricted=sorted(set(restricted)),
                rules=PROPOSED_RULES,automation_enabled=False,
                can_warning=frappe.has_permission('HR Warning','create'),
                can_request=frappe.has_permission('HR Service Request','create'),
                can_email=frappe.has_permission('Communication','create'))
