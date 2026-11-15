"""Daily labour usage and project expenses; never an employee reimbursement/payment."""
from hashlib import sha256
from decimal import Decimal, InvalidOperation

import frappe
from frappe import _
from frappe.utils import getdate, flt

DT = 'Project Labour Expense'


def enabled():
    from bsgroup.project_daily_work import timesheets_enabled
    return timesheets_enabled() and frappe.db.exists('DocType', DT)


def expense_key(approval, line, day):
    # One project-wide expense for a labour line/day, irrespective of retries or author.
    return 'PLE-' + sha256(f'{approval}|{line}|{day}'.encode()).hexdigest()[:32]


def quantity(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        number = Decimal(-1)
    if not number.is_finite() or number <= 0 or number != number.to_integral_value():
        frappe.throw(_('Enter a positive whole number of labourers.'))
    return int(number)


def usage(approval, exclude=None):
    if not enabled():
        return []
    filters = {'labor_preapproval': approval}
    if exclude:
        filters['name'] = ['!=', exclude]
    return frappe.get_all(DT, filters=filters,
        fields=['name', 'labor_line', 'persons', 'amount', 'work_date', 'recorded_by', 'modified'])


def totals(approval):
    rows = usage(approval)
    return sum(flt(r.persons) for r in rows), sum(flt(r.amount) for r in rows)


def has_preapproval(project):
    return bool(frappe.db.exists('Labor Preapproval', {'source':'Project', 'reference':project, 'docstatus':['!=',2]}))


@frappe.whitelist()
def context(project, task):
    from bsgroup.project_plan import _read_task, _is_assigned, _status_actor
    doc, item = _read_task(project, task)
    if not (_is_assigned(item, closed=True) or _status_actor(doc, item)):
        frappe.throw(_('Only the assigned user or project status manager can record this work.'), frappe.PermissionError)
    result = {'required':bool(enabled() and has_preapproval(project)), 'lines':[]}
    if not result['required']:
        return result
    for name in frappe.get_all('Labor Preapproval', filters={'source':'Project', 'reference':project,
            'task':task, 'company':doc.company, 'docstatus':1, 'workflow_state':'Approved'}, pluck='name'):
        approval = frappe.get_doc('Labor Preapproval', name)
        used = usage(name)
        for line in approval.labor_line_items:
            current = next((r for r in used if r.labor_line == line.name and getdate(r.work_date) == getdate()), None)
            result['lines'].append(dict(value=line.name, approval=name, skill=line.role__skill,
                rate=line.rate, daily_limit=line.no_of_persons, approved_days=line.days,
                current_persons=current.persons if current else 0,
                expected_modified=str(current.modified) if current else '',
                recorded_by=current.recorded_by if current else '',
                remaining_person_days=max(0, line.no_of_persons * line.days - sum(r.persons for r in used if r.labor_line == line.name))))
    return result


def validate_limits(line, persons, other_line_days, total_other_days, legacy_days,
                    total_other_cost, legacy_cost, approved_days, approved_cost):
    if persons > line.no_of_persons:
        frappe.throw(_('Labour count exceeds the approved daily headcount. Additional approval is required.'))
    if persons + other_line_days > line.no_of_persons * line.days:
        frappe.throw(_('The approved allowance for this labour type is exhausted. Additional approval is required.'))
    if persons + total_other_days + legacy_days > approved_days:
        frappe.throw(_('Total labour usage exceeds the approved person-day allowance.'))
    amount = Decimal(str(line.rate)) * persons
    if amount + Decimal(str(total_other_cost)) + Decimal(str(legacy_cost)) > Decimal(str(approved_cost)):
        frappe.throw(_('Labour expense exceeds the approved cost limit.'))
    return float(amount)


def record(project, task, payload, work_entry, work, day):
    """Caller has checked Task actor/access. All writes share the daily-work transaction."""
    if not enabled():
        return None
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    if not isinstance(data, dict):
        frappe.throw(_('Choose whether labour was used today.'))
    if not has_preapproval(project.name) and not data:
        return None
    if data.get('used') not in ('Yes', 'No'):
        frappe.throw(_('Choose Yes or No for labour used today.'))
    if data['used'] == 'No':
        return None
    if not data.get('approval') or not data.get('line'):
        frappe.throw(_('Select an approved labour line for this task.'))
    approval = frappe.get_doc('Labor Preapproval', data['approval'], for_update=True)
    if (approval.docstatus != 1 or approval.workflow_state != 'Approved' or approval.source != 'Project'
            or approval.reference != project.name or approval.task != task.name or approval.company != project.company):
        frappe.throw(_('Use an approved labour preapproval for this project and task.'))
    line = next((r for r in approval.labor_line_items if r.name == data['line']), None)
    if not line:
        frappe.throw(_('The labour line does not belong to this approval.'))
    persons = quantity(data.get('persons'))
    name = expense_key(approval.name, line.name, day)
    current = frappe.get_doc(DT, name) if frappe.db.exists(DT, name) else None
    if current:
        if current.work_entry == work_entry:
            return current.name
        if current.recorded_by != frappe.session.user:
            frappe.throw(_('Labour for this approval line and date has already been recorded by {0}. Do not record the same labour again.').format(current.recorded_by))
        if str(current.modified) != str(data.get('expected_modified') or ''):
            frappe.throw(_('Today\'s labour expense changed. Reopen the work dialog before updating the daily total.'))
    elif data.get('expected_modified'):
        frappe.throw(_('The labour expense changed. Reopen the work dialog.'))
    # Existing named-worker attendance must not be recorded again through daily work.
    if frappe.db.exists('Labor Attendance', {'labor_preapproval':approval.name, 'docstatus':['!=',2],
            'check_in_time':['between',[str(day)+' 00:00:00',str(day)+' 23:59:59']]}):
        frappe.throw(_('Labour attendance already exists for this approval today. Reconcile it before recording daily labour expenses.'))
    from bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval import get_consumed_person_days, get_consumed_cost
    other = usage(approval.name, name)
    all_days, all_cost = totals(approval.name)
    amount = validate_limits(line, persons, sum(r.persons for r in other if r.labor_line == line.name),
        sum(r.persons for r in other), get_consumed_person_days(approval.name) - all_days,
        sum(r.amount for r in other), get_consumed_cost(approval.name) - all_cost,
        approval.approved_person_days, approval.total_labor_cost)
    expense = current or frappe.new_doc(DT)
    expense.update(dict(project=project.name, task=task.name, company=project.company,
        labor_preapproval=approval.name, labor_line=line.name, skill=line.role__skill,
        work_date=day, persons=persons, rate=line.rate, amount=amount,
        currency=frappe.get_cached_value('Company',project.company,'default_currency'),
        recorded_by=frappe.session.user, work_entry=work_entry, work_done=work))
    expense.flags.bs_daily_labor = True
    if current:
        expense.save(ignore_permissions=True)
    else:
        expense.insert(ignore_permissions=True, set_name=name)
    return expense.name


def expense_rows(project):
    if not enabled():
        return []
    # Project panel has already enforced project access; match its claim visibility.
    from bsgroup.project_expenses import manager_for
    manager, _problem = manager_for(project)
    filters = {'project':project.name}
    if manager != frappe.session.user and not set(frappe.get_roles()) & {'System Manager','Accounts Manager','Accounts User','HR Manager'}:
        filters['recorded_by'] = frappe.session.user
    return frappe.get_all(DT, filters=filters, fields=['name','task','work_date','persons','skill',
        'rate','amount','currency','recorded_by','work_done','labor_preapproval'], order_by='work_date desc', limit_page_length=100)


def guard_attendance(doc, method=None):
    if not enabled() or not doc.labor_preapproval or doc.docstatus == 2:
        return
    frappe.get_doc('Labor Preapproval', doc.labor_preapproval, for_update=True)
    if doc.check_in_time and frappe.db.exists(DT, {'labor_preapproval':doc.labor_preapproval,
            'work_date':getdate(doc.check_in_time)}):
        frappe.throw(_('This day\'s labour is already recorded through Project Plan. Do not create duplicate attendance or expense.'))


def lock_voucher(doc, method=None):
    if enabled():
        names = {frappe.db.get_value('Labor Attendance', r.labor_attendance, 'labor_preapproval') for r in doc.items if r.labor_attendance}
        for name in sorted(n for n in names if n):
            frappe.get_doc('Labor Preapproval', name, for_update=True)


def guard_preapproval_cancel(doc, method=None):
    if enabled():
        frappe.get_doc('Labor Preapproval', doc.name, for_update=True)
        if frappe.db.exists(DT, {'labor_preapproval':doc.name}):
            frappe.throw(_('This approval has recorded daily labour expenses. Reconcile these before cancelling it.'))
