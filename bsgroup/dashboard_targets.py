"""Read-only annual target cards, scoped to self or the chairman's companies."""
import frappe
from frappe.utils import getdate, flt


def progress(target, actual):
    target, actual = flt(target), flt(actual)
    return dict(target=target, achieved=actual, remaining=max(0, target-actual),
        percent=round(actual/target*100, 1) if target > 0 else None)


@frappe.whitelist()
def overview(day):
    user = frappe.session.user
    if user == 'Guest':
        frappe.throw('Please sign in.', frappe.PermissionError)
    selected = getdate(day)
    team = user in ('Administrator', 'mohan@bitssecureit.com')
    companies = frappe.get_list('Company', pluck='name', limit_page_length=0)
    if not companies:
        return dict(visible=False)
    filters = {'status':'Active', 'company':['in', companies]}
    if not team:
        filters['user_id'] = user
    employees = frappe.get_all('Employee', filters=filters,
        fields=['name','employee_name','user_id','company'], limit_page_length=0)
    # Only linked sales users; never guess from similar names or accept a user parameter.
    sales_users = set(frappe.get_all('Has Role', filters={'parenttype':'User',
        'role':['in',['BS Scoped Sales','Sales User','Sales Manager']]}, pluck='parent', limit_page_length=0))
    employees = [e for e in employees if e.user_id in sales_users and
        frappe.db.get_value('User', e.user_id, 'enabled')]
    cards = []
    for employee in employees:
        persons = frappe.get_all('Sales Person', filters={'employee':employee.name,'enabled':1},
            fields=['name'], limit_page_length=0)
        if not persons:
            continue
        # Fiscal-year resolution follows the company's configured financial year.
        from erpnext.accounts.utils import get_fiscal_year
        fy = get_fiscal_year(selected, company=employee.company)[0]
        card = dict(name=employee.employee_name, user=employee.user_id, company=employee.company,
            currency=frappe.db.get_value('Company',employee.company,'default_currency'),
            fiscal_year=fy, warning=None, actual_available=False)
        if len(persons) != 1:
            card.update(warning='Multiple Sales Person links; HR mapping needs review.', sales=progress(0,0), gp=progress(0,0))
            cards.append(card)
            continue
        salesperson = persons[0].name
        card['salesperson'] = salesperson
        rows = frappe.get_all('Target Detail', filters={'parenttype':'Sales Person',
            'parent':salesperson,'fiscal_year':fy}, fields=['target_amount','custom_invoiced_gp_target','custom_gp_target'],limit_page_length=0)
        # Do not add potentially overlapping item-group targets together.
        if len(rows) > 1:
            card['warning'] = 'Multiple target rows; target breakdown needs review.'
        target = rows[0] if len(rows)==1 else {}
        revenue = flt(target.get('target_amount'))
        gp = flt(target.get('custom_invoiced_gp_target')) or flt(target.get('custom_gp_target'))
        entries = frappe.get_all('Sales Target GP Entry', filters={'salesperson':salesperson,
            'fiscal_year':fy,'docstatus':['!=',2]}, fields=['name'],limit_page_length=0)
        actual_revenue = actual_gp = 0
        if len(entries)==1:
            doc = frappe.get_doc('Sales Target GP Entry',entries[0].name)
            actual_revenue = sum(flt(r.invoiced_sales_revenue) for r in doc.monthly_data)
            actual_gp = sum(flt(r.invoiced_sales_gp) for r in doc.monthly_data)
            card['actual_available'] = True
        elif len(entries)>1:
            card['warning'] = 'Multiple performance entries; results need review.'
        card.update(sales=progress(revenue,actual_revenue),gp=progress(gp,actual_gp))
        cards.append(card)
    return dict(visible=bool(cards),team=team,cards=sorted(cards,key=lambda x:({'mohan@bitssecureit.com':0,'gopinath@bitssecureit.com':1}.get(x['user'],2),x['name'].casefold())),
        basis='Recorded invoiced sales and gross profit from Monthly Sales Performance Entry; full fiscal year. Not quotations or open pipeline.')
