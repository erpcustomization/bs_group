"""Exercise actual endpoint logic against an isolated attendance store."""
import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

records = {'Employee': [NS(name='OWN', default_shift='General - UAE', holiday_list='H')],
           'Shift Assignment': [], 'Employee Checkin': [], 'Attendance Request': []}
calls = []
cache = {}
def get_all(doctype, **kwargs):
    calls.append((doctype, kwargs))
    return records[doctype]
frappe = NS(session=NS(user='alice@example.com'),
    whitelist=lambda: lambda f:f, get_all=get_all,
    utils=NS(to_timedelta=lambda s:timedelta(hours=int(str(s).split(':')[0])),
             get_system_timezone=lambda:'Asia/Dubai', get_datetime=datetime.fromisoformat),
    get_doc=lambda *args:NS(name='General - UAE',start_time='09:00:00',end_time='06:00:00',holiday_list='H'),
    db=NS(get_value=lambda *args:None,exists=lambda *args:False),
    cache=NS(get_value=lambda key:cache.get(key),set_value=lambda key,value,**kw:cache.update({key:value})))
sys.modules['frappe']=frappe
spec=importlib.util.spec_from_file_location('widget',Path(__file__).parents[1]/'bsgroup/attendance_widget.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
now=datetime.fromisoformat('2026-11-02T18:10:00+04:00')
records['Employee Checkin']=[NS(time='2026-11-02 09:01:00',log_type='IN'),NS(time='2026-11-02 18:02:00',log_type='OUT')]
r=m._status(now)
assert r['shift_end'].endswith('18:00:00+04:00') and r['late_minutes']==1 and r['grace_min']==0
assert r['worked_minutes']==541 and not r['checked_in'] and not r['early_exit_minutes']
assert calls[0][1]['filters']['user_id']=='alice@example.com'
for dt,kw in calls:
    if dt in ['Employee Checkin','Shift Assignment','Attendance Request']:
        filters=kw['filters']
        assert filters.get('employee')=='OWN' if isinstance(filters,dict) else ['employee','=','OWN'] in filters
records['Employee Checkin']=[NS(time='2026-11-02 09:00:00',log_type='IN'),NS(time='2026-11-02 12:30:00',log_type='OUT'),NS(time='2026-11-02 13:00:00',log_type='IN'),NS(time='2026-11-02 17:45:00',log_type='OUT')]
r=m._status(now)
assert r['worked_minutes']==495 and r['early_exit_minutes']==15
records['Attendance Request']=[NS(reason='Work From Home')]
assert m._status(now)['on_duty']
records['Employee']=[]
assert m._status(now)=={'visible':False}
m.get_today_status();count=len(calls);m.get_today_status();assert len(calls)==count
frappe.session.user='bob@example.com';m.get_today_status();assert len(calls)>count
assert len(cache)==2
print('PASS: own-user filters, per-user cache, dashboard-only shift override, 9:01 late, break accounting, checkout, duty and missing employee')
