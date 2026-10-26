"""Read-only local integration: derived labels, counts and pagination agree."""
from pathlib import Path
import frappe
import bsgroup

bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
frappe.init(site='rel1-test.local', sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
from bsgroup.opportunity_progress import resolve_many
from bsgroup.opportunity_progress_filter import get, get_count, matches, split_filters

try:
    assert matches('Delayed by Presales', '=', 'Delayed by Presales')
    assert not matches('Delayed by Presales', '=', 'Open')
    assert matches('Delayed by Presales', 'like', '%Presales')
    assert matches('Open', 'not in', ['Closed', 'Lost'])
    assert matches('Open', 'in', 'Open,Closed')
    assert matches('Open', 'is', 'set')
    assert not matches('Open', 'is', 'not set')
    ordinary, derived = split_filters([['status', '=', 'Open'], ['Opportunity','company','=','Example']])
    assert len(ordinary) == len(derived) == 1
    rows = frappe.get_list('Opportunity', fields=['name','status'], order_by='name asc', limit_page_length=0)
    expected = {}
    for start in range(0,len(rows),500):
        expected.update(resolve_many(rows[start:start+500]))
    labels = sorted(set(item['label'] for item in expected.values()))
    checks = 0
    for label in labels:
        filters = [['Opportunity','status','=',label]]
        frappe.local.form_dict = frappe._dict(doctype='Opportunity', filters=filters)
        count = get_count()
        names = [name for name,result in expected.items() if result['label'] == label]
        assert count == len(names), (label,count,len(names))
        for start in (0,2):
            frappe.local.form_dict = frappe._dict(doctype='Opportunity', filters=filters,
                fields=['name','status'], order_by='name asc', start=start, page_length=2)
            result = get()
            actual = [dict(zip(result['keys'], row))['name'] for row in result['values']] if result else []
            assert actual == names[start:start+2], (label,actual,names[start:start+2])
            assert frappe.local.form_dict.filters == filters
            checks += 1
    # Unknown labels must return zero, never fall back to all records.
    frappe.local.form_dict = frappe._dict(doctype='Opportunity',filters=[['Opportunity','status','=','NOT A STATUS']])
    assert get_count() == 0
    frappe.set_user('Guest')
    frappe.local.form_dict = frappe._dict(doctype='Opportunity',filters=[['Opportunity','status','=','Open']])
    try:
        get_count()
        raise AssertionError('Guest must not read Opportunities through derived filters')
    except frappe.PermissionError:
        pass
    print(f'PASS operators, {len(labels)} derived statuses, {checks} pagination checks, counts and zero-match behavior')
finally:
    frappe.db.rollback()
    frappe.destroy()
