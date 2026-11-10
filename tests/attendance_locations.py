"""Recorded-location pairing, no-GPS handling, and existing attendance regressions."""
import importlib.util
import runpy
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
pkg = types.ModuleType('bsgroup'); pkg.__path__ = [str(ROOT/'bsgroup')]
sys.modules['bsgroup'] = pkg
from bsgroup.attendance_location import format_location
for pair in [(None,55), (25,None), ('',55), (0,0), ('nan',55), (91,55), (25,181), ('bad',55)]:
    assert format_location(*pair) == 'Location not recorded', pair
assert format_location(0,55) == 'GPS 0.00000, 55.00000'
assert format_location(-25,-55) == 'GPS -25.00000, -55.00000'

s = runpy.run_path(str(ROOT/'tests/attendance_widget.py'))
NS = types.SimpleNamespace
s['records']['Employee'] = [NS(name='OWN', default_shift='General - UAE', holiday_list='H')]
s['records']['Employee Checkin'] = [
    NS(time='2026-11-02 09:00:00',log_type='IN',latitude=25,longitude=55),
    NS(time='2026-11-02 12:00:00',log_type='OUT',latitude=26,longitude=56),
    NS(time='2026-11-02 13:00:00',log_type='IN',latitude=27,longitude=57),
    NS(time='2026-11-02 17:00:00',log_type='OUT',latitude=28,longitude=58),
    NS(time='2026-11-02 20:00:00',log_type='OUT',latitude=29,longitude=59)]
r = s['m']._status(s['now'])
assert r['first_in_location'].endswith('GPS 25.00000, 55.00000')
assert r['last_out_location'].endswith('GPS 28.00000, 58.00000')
assert r['worked_minutes'] == 420
s['records']['Employee Checkin'][0].latitude = None
assert s['m']._status(s['now'])['first_in_location'] == 'Location not recorded'

class Row(dict):
    __getattr__ = dict.get
class Clock(datetime):
    @classmethod
    def now(cls, tz): return datetime(2026,11,2,18,10,tzinfo=tz)
f = s['frappe']
f.session.user='alice@example.com'
f.cache=NS(get_value=lambda key:None,set_value=lambda *a,**kw:None)
f.utils.getdate=lambda value: datetime.fromisoformat(str(value)).date()
records = {'Employee':[Row(name='OWN',default_shift=None,holiday_list=None,date_of_joining=None,relieving_date=None)],
    'Employee Checkin':s['records']['Employee Checkin'], 'Leave Application':[], 'Attendance Request':[], 'Shift Assignment':[]}
f.get_all=Mock(side_effect=lambda dt,**kw:records[dt])
spec=importlib.util.spec_from_file_location('month_test',ROOT/'bsgroup/monthly_attendance.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.datetime=Clock
r=m.get_month('2026-11')['days'][1]
assert r['check_in']=='09:00 AM' and r['check_out']=='05:00 PM'
assert r['check_in_location']=='Location not recorded'
assert r['check_out_location'].endswith('GPS 28.00000, 58.00000')
assert r['working_minutes']==420
for c in f.get_all.call_args_list:
    if c.args[0]=='Employee': assert c.kwargs['filters']['user_id']=='alice@example.com'
    if c.args[0]=='Employee Checkin': assert ['employee','=','OWN'] in c.kwargs['filters']
print('PASS: precise first IN / last OUT pairing, missing first GPS, different locations, future punches, own-user scope, valid zero axis, invalid GPS')
runpy.run_path(str(ROOT/'tests/monthly_attendance.py'))
import unittest
suite=unittest.defaultTestLoader.discover(str(ROOT/'bsgroup/tests'),pattern='test_hr_attendance.py')
suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'bsgroup/tests'),pattern='test_dashboard_punch.py'))
result=unittest.TextTestRunner(verbosity=1).run(suite)
assert result.wasSuccessful()
