"""Daily reporting contract: permission boundary, dates and sales attribution."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS


class Row(dict):
    __getattr__ = dict.__getitem__


queries = []

def get_list(dt, fields, filters, limit_page_length):
    queries.append((dt, filters))
    if dt == 'Lead':
        return [Row(name='L1', owner='admin', lead_owner='sales-a')]
    if dt == 'Opportunity':
        return [Row(name='O1', owner='admin', opportunity_owner='sales-a')]
    if dt == 'Presales Request':
        return [Row(name='P1')]
    if dt == 'Deal Cost Sheet':
        return [Row(name='D1', custom_deal_status='Draft', custom_record_authority=None),
                Row(name='D2', custom_deal_status='Lost', custom_record_authority=None),
                Row(name='D3', custom_deal_status='Draft', custom_record_authority='Superseded')]
    assert dt == 'Quotation'
    assert ['docstatus', '=', 1] in filters
    if ['transaction_date', '=', '2026-11-03'] in filters:
        return [Row(name='Q1', currency='AED', grand_total=105, owner='presales', opportunity='O1'),
                Row(name='Q2', currency='OMR', grand_total=20, owner='sales-b', opportunity=None)]
    assert ['custom_won_date', '=', '2026-11-03'] in filters
    assert ['custom_pipeline_stage', '=', 'Won'] in filters
    assert not any(f[0] == 'transaction_date' for f in filters)
    return [Row(name='Q-old', currency='AED', grand_total=300, owner='presales', opportunity='O1')]


def throw(message, exc=ValueError):
    raise exc(message)


fake = NS(session=NS(user='mohan@bitssecureit.com'), whitelist=lambda:lambda f:f,
          utils=NS(today=lambda:'2026-11-03'), has_permission=lambda *a:True,
          get_list=get_list, get_cached_value=lambda dt,user,field:user,
          throw=throw, PermissionError=PermissionError)
sys.modules['frappe'] = fake
sys.modules['bsgroup.management_attendance'] = NS(overview=lambda day:dict(day=str(day),total=0,totals={}))
path = Path(__file__).parents[1] / 'bsgroup/management_dashboard.py'
spec = importlib.util.spec_from_file_location('management_dashboard', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
data = module.daily()
assert (data['leads'],data['opportunities'],data['presales'],data['dcs']) == (1,1,1,1)
assert data['quoted'] == {'count':2,'amounts':{'AED':105,'OMR':20}}
assert data['won'] == {'count':1,'amounts':{'AED':300}}
assert [p['user'] for p in data['people']] == ['sales-a','sales-b']
assert data['people'][0]['won']['amounts']['AED'] == 300
for dt, filters in queries:
    if dt in ('Lead','Presales Request'):
        assert ['creation','>=','2026-11-03'] in filters
        assert ['creation','<','2026-11-04'] in filters
fake.has_permission = lambda *a:False
assert module.daily()['quoted'] is None
assert module.daily()['people'] == []
for day in ('bad','2026-11-04'):
    try:
        module.daily(day)
        raise AssertionError('invalid/future date accepted')
    except ValueError:
        pass
fake.session.user = 'sales-a'
try:
    module.daily()
    raise AssertionError('other user accepted')
except PermissionError:
    pass
print('PASS: daily cohorts, older quotes won today, currency separation, attribution, workload exclusions, permissions and date validation')
