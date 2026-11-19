"""Run without a live database; never sends mail."""
import ast
import calendar
from datetime import date, datetime, timedelta, time
from hashlib import sha256
from html import escape
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo
import sys

class D(dict):
    __getattr__ = dict.get

p = Path(__file__).parents[1] / 'bsgroup/monthly_sales_targets_email.py'
ns = dict(calendar=calendar, datetime=datetime, timedelta=timedelta, time=time,
    sha256=sha256, escape=escape, flt=lambda v:float(v or 0), getdate=lambda v:v,
    site_profile=lambda:dict(region='UAE'), MOHAN='mohan@bitssecureit.com', TZ=ZoneInfo('Asia/Dubai'),
    FLAG='monthly', table=lambda headers, rows:str((headers,rows)))
ns['progress'] = lambda t,a:dict(target=float(t or 0), achieved=a, remaining=max(0,float(t or 0)-a), percent=round(a/float(t)*100,1) if t else None)
for node in ast.parse(p.read_text()).body:
    if isinstance(node, ast.FunctionDef):
        node.decorator_list=[]
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),ns)
assert ns['cutoff'](date(2027,1,1)) == date(2026,12,31)
assert ns['cutoff'](date(2028,3,1)) == date(2028,2,29)
assert ns['due'](datetime(2026,12,1,10,30))
assert not ns['due'](datetime(2026,12,1,10,29))
assert not ns['due'](datetime(2026,12,2,10,30))
assert not ns['due'](datetime(2026,12,1,12,0))
assert list(ns['month_dates'](date(2026,4,1),date(2027,2,28))) == ['April','May','June','July','August','September','October','November','December','January','February']
ns['people'] = lambda:[dict(kind='Sales',user='sales@bitssecureit.com',name='Sales',cc=['manager@bitssecureit.com']),dict(kind='Sales',user=ns['MOHAN'],name='Mohan',cc=[ns['MOHAN']]),dict(kind='Presales',user='pre@bitssecureit.com',cc=[])]
recipients = list(ns['recipients']())
assert len(recipients)==2 and recipients[0]['cc']==['manager@bitssecureit.com',ns['MOHAN']] and recipients[1]['cc']==[]
rows=[D(month='January',invoiced_sales_revenue=100,invoiced_sales_gp=20,status='Saved'),D(month='February',invoiced_sales_revenue=200,invoiced_sales_gp=30,status='Draft'),D(month='March',invoiced_sales_revenue=900,invoiced_sales_gp=90,status='Saved')]
def get_all(dt, **kw):
    return {'Employee':['e1'], 'Sales Person':['s1'], 'Target Detail':[D(target_amount=1000,custom_invoiced_gp_target=0,custom_gp_target=100)], 'Sales Target GP Entry':['actual']}[dt]
ns['frappe'] = NS(get_all=get_all, get_doc=lambda *a:D(monthly_data=rows),db=NS(get_value=lambda *a:'AED'))
sys.modules['erpnext.accounts.utils']=NS(get_fiscal_year=lambda *a,**k:('2026',date(2026,1,1),date(2026,12,31)))
data=ns['collect'](recipients[0],date(2026,2,28))
assert data['sales']['achieved']==300 and data['sales']['percent']==30 and data['gp']['achieved']==50
assert len(data['monthly'])==2
rows.pop(1)
data=ns['collect'](recipients[0],date(2026,2,28))
assert data['sales']['achieved']==100 and data['monthly'][1][3]=='Not entered' and data['warnings']
subject,body=ns['report'](recipients[0],date(2026,2,28))
assert 'February 2026' in subject and 'BITS Secure IT' in body
rows.clear()
assert not ns['collect'](recipients[0],date(2026,2,28))['sales']['available']
# Successful retries must not enqueue another email. Marker and queue share transaction.
markers=set(); sent=[]
class Notice:
    def __init__(self,d):self.d=d
    def db_insert(self):markers.add(self.d['name'])
class FixedNow:
    @staticmethod
    def now(tz):return datetime(2026,12,1,10,30,tzinfo=tz)
ns['datetime']=FixedNow
ns['report']=lambda *a:('Subject','Body')
ns['recipients']=lambda:iter(recipients)
ns['frappe']=NS(db=NS(get_single_value=lambda *a:1,exists=lambda dt,key:key in markers,savepoint=lambda *a:None,commit=lambda:None),get_doc=lambda d:Notice(d),sendmail=lambda **k:sent.append(k) or 'queue')
assert ns['send_reports']()==2 and ns['send_reports']()==0 and len(sent)==2
assert sent[0]['cc']==['manager@bitssecureit.com','mohan@bitssecureit.com']
assert ns['key']('a',date(2026,11,30))!=ns['key']('a',date(2026,12,31))
print('PASS: monthly schedule, year rollover, fiscal month range, previous-month cutoff, recipient/CC isolation, missing data, GP fallback, duplicate prevention')
