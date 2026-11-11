"""Early checkout boundaries plus permission/company/shift selection contracts."""
import importlib.util
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

class Row(dict):
    __getattr__ = dict.get

tz=ZoneInfo('Asia/Dubai')
day=date(2026,11,11)
def stamp(hour, minute=0, delta=0):
    return datetime(2026,11,11,hour,minute,tzinfo=tz)+timedelta(days=delta)
def duration(value):
    if isinstance(value,timedelta): return value
    hours,minutes,seconds=map(int,value.split(':'))
    return timedelta(hours=hours,minutes=minutes,seconds=seconds)
def throw(message,exc=ValueError): raise exc(message)
fake=NS(session=NS(user='mohan@bitssecureit.com'),PermissionError=PermissionError,
    whitelist=lambda:lambda f:f,throw=throw,
    utils=NS(get_system_timezone=lambda:'Asia/Dubai',getdate=lambda v:date.fromisoformat(str(v)),
             get_datetime=lambda v:datetime.fromisoformat(str(v)),to_timedelta=duration))
sys.modules['frappe']=fake
path=Path(__file__).parents[1]/'bsgroup/dashboard_early_checkout.py'
spec=importlib.util.spec_from_file_location('early_checkout',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
start,end=stamp(9),stamp(18)
def early(logs,now=stamp(20),s=start,e=end): return m.early_departure(logs,s,e,now)
assert early([(start,'IN'),(stamp(17),'OUT')])['minutes_early']==60
assert early([(stamp(10),'IN'),(stamp(17),'OUT')])['minutes_early']==60 # late IN still early OUT
assert early([(start,'IN'),(end,'OUT')]) is None
assert early([(start,'IN'),(stamp(19),'OUT')]) is None
assert early([(start,'IN')]) is None
assert early([(stamp(17),'OUT')]) is None
assert early([(stamp(8),'OUT'),(start,'IN')]) is None
assert early([(start,'IN'),(start,'OUT')]) is None
assert early([(start,'IN'),(stamp(12),'OUT'),(stamp(13),'IN')]) is None
assert early([(start,'IN'),(stamp(12),'OUT'),(stamp(13),'IN'),(end,'OUT')]) is None
assert early([(start,'IN'),(stamp(12),'OUT'),(stamp(13),'IN'),(stamp(17),'OUT')])['minutes_early']==60
assert early([(start,'IN'),(stamp(17),'OUT')],now=stamp(16)) is None
assert early([(start,'IN'),(end-timedelta(seconds=1),'OUT')])['minutes_early']==1
night_start,night_end=stamp(22),stamp(6,delta=1)
assert early([(night_start,'IN'),(stamp(5,delta=1),'OUT')],stamp(8,delta=1),night_start,night_end)['minutes_early']==60
assert early([(night_start,'IN'),(night_end,'OUT')],stamp(8,delta=1),night_start,night_end) is None
shift=Row(name='General - UAE',start_time='08:00:00',end_time='17:00:00',holiday_list=None)
assert m.scheduled_bounds(day,shift,tz)==(stamp(8),stamp(17)) # no hardcoded 9–6 override
night=Row(name='Night',start_time='22:00:00',end_time='06:00:00')
assert m.scheduled_bounds(day,night,tz)==(night_start,night_end)

class Clock(datetime):
    @classmethod
    def now(cls,tz): return stamp(20)
m.datetime=Clock
employee=lambda name,**kw:Row(name=name,employee_name=name,status='Active',date_of_joining=None,
    relieving_date=None,default_shift='General - UAE',holiday_list=None,**kw)
employees=[employee(name) for name in ['EARLY','EXPIRED','ONLEAVE','ONDUTY','OFF','MISSING','OPEN']]
employees[5].default_shift=None
employees[4].holiday_list='Holiday'
employees[6].default_shift='General - UAE'
queries=[]
records={
    'Employee':employees,
    'Shift Assignment':[Row(employee='EARLY',shift_type='Assigned',end_date=None),
                        Row(employee='EXPIRED',shift_type='Assigned',end_date='2026-11-10')],
    'Holiday':['Holiday'], 'Leave Application':['ONLEAVE'], 'Attendance Request':['ONDUTY'],
    'Employee Checkin':[Row(employee=name,time='2026-11-11 09:00:00',log_type='IN') for name in ['EARLY','EXPIRED','OPEN']]
       +[Row(employee=name,time='2026-11-11 17:30:00',log_type='OUT') for name in ['EARLY','EXPIRED']]
}
def get_all(dt,**kwargs):
    queries.append((dt,kwargs));return records[dt]
fake.get_all=get_all
fake.get_list=lambda dt,**kw:['Permitted Company']
fake.get_doc=lambda dt,name:shift if name=='General - UAE' else Row(name='Assigned',start_time='09:00:00',end_time='18:00:00',holiday_list=None)
result=m.summary('2026-11-11')
assert result['count']==1 and result['details'][0]['employee']=='EARLY'
assert result['details'][0]['minutes_early']==30
assert queries[0][1]['filters']=={'company':['in',['Permitted Company']]}
assert next(q for dt,q in queries if dt=='Employee Checkin')['filters'][0][2]==['EARLY','EXPIRED','OPEN']
fake.get_list=lambda *a,**kw:[]
queries.clear();assert m.summary('2026-11-11')['count']==0 and not queries
fake.session.user='sales@example.com'
try: m.summary('2026-11-11');raise AssertionError('Unauthorized user accepted')
except PermissionError: pass
fake.session.user='Administrator'
for invalid in ['bad','2026-11-12']:
    try: m.summary(invalid);raise AssertionError('Invalid date accepted')
    except ValueError: pass
print('PASS: early/equal/late checkout, re-entry, missing punches, future punches, overnight shifts, actual assigned end, assignment expiry, exclusions, company scope and access')
