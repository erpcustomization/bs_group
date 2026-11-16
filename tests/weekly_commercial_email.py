import importlib.util
import sys
import types
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch

class Row(dict):
    __getattr__ = dict.get

root=Path(__file__).resolve().parents[1]
f=types.ModuleType('frappe'); f.whitelist=lambda **kw:lambda fn:fn
hr=types.ModuleType('bsgroup.hr_email');hr.site_profile=lambda:dict(region='UAE')
with patch.dict(sys.modules,{'frappe':f,'bsgroup.hr_email':hr}):
    spec=importlib.util.spec_from_file_location('weekly',root/'bsgroup/weekly_commercial_email.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.period(date(2026,11,16))==(date(2026,11,9),date(2026,11,16))
    assert m.period(date(2027,1,4))==(date(2026,12,28),date(2027,1,4))
    for hour,minute,result in [(10,29,False),(10,30,True),(11,55,True),(12,0,False)]:
        assert m.due(datetime(2026,11,16,hour,minute,tzinfo=m.TZ))==result
    assert not m.due(datetime(2026,11,17,10,30,tzinfo=m.TZ))
    assert m.key('a','Sales',date(2026,11,16))==m.key('a','Sales',date(2026,11,16))
    assert len({m.key(u,k,d) for u in ['a','b'] for k in ['Sales','Presales'] for d in [date(2026,11,16),date(2026,11,23)]})==8
    def row(name,**kw):
        return Row(name=name,owner='sales@example.com',modified_by='presales@example.com',creation='2026-11-10 09:00:00',modified='2026-11-12 10:00:00',docstatus=0,**kw)
    source={dt:[] for dt in m.TYPES}
    source['Lead']=[row('L-TEST',lead_name='TEST ONLY Customer'),row('L-REAL',lead_name='Real Customer')]
    source['Opportunity']=[row('O-1',opportunity_from='Lead',party_name='L-TEST')]
    source['Presales Request']=[row('P-1',opportunity='O-1'),row('P-REAL',customer='Real Customer',status='In Progress')]
    source['Deal Cost Sheet']=[row('D-1',presales_request='P-1'),row('D-REAL',presales_request='P-REAL',deal_owner='sales@example.com',customer='Real Customer')]
    source['Quotation']=[row('Q-1',custom_deal_cost_sheet='D-1')]
    f.get_all=lambda dt,**kw:source.get(dt,[])
    data=m.collect(date(2026,11,16))
    assert data['excluded']=={('Lead','L-TEST'),('Opportunity','O-1'),('Presales Request','P-1'),('Deal Cost Sheet','D-1'),('Quotation','Q-1')}
    assert ('Deal Cost Sheet','D-REAL') in data['events']
    f.get_doc=lambda dt,n:next(r for r in source[dt] if r.name==n)
    f.has_permission=lambda *a,**kw:True
    subject,body=m.report(dict(user='presales@example.com',kind='Presales',name='<Person>'),data)
    assert 'P-REAL' in body and 'D-REAL' in body and 'Q-1' not in body
    assert '&lt;Person&gt;' in body and 'Presales Operations' not in body
    subject,body=m.report(dict(user='other@example.com',kind='Presales',name='Other'),data)
    assert 'P-REAL' not in body and 'No activity recorded' in body
    f.has_permission=lambda *a,**kw:False
    subject,body=m.report(dict(user='presales@example.com',kind='Presales',name='Person'),data)
    assert 'P-REAL' not in body
    source['Employee']=[Row(name='EMP1',employee_name='Sales',user_id='sales@example.com',reports_to=None)]
    f.get_roles=lambda user:['Sales User']
    f.utils=Row(validate_email_address=lambda v:bool(v and '@' in v))
    f.db=Row(get_value=lambda dt,n,field,**kw: 'Sales' if field=='first_name' else 1)
    people=m.people(); assert people[0]['cc']==[m.MOHAN] and people[0]['kind']=='Sales'
print('PASS previous week/year boundary, exact send-time gate, recipient/week/type dedup keys, linked test exclusions, activity attribution, escaping, record access and Mohan fallback')
