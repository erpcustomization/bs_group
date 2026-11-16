import ast
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

path=Path(__file__).parents[1]/'bsgroup/management_attendance.py'
functions=[node for node in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(node,ast.FunctionDef) and node.name in ('classify', 'punch_summary', 'punch_details')]
ns={}
exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),str(path),'exec'),ns)
classify=ns['classify']
start=datetime(2026,11,3,9)
before=start-timedelta(minutes=1)
after=start+timedelta(hours=9)
assert classify(start,before,None,None)=='not_started'
assert classify(start,start,None,None)=='no_checkin'
assert classify(start,after,start,None)=='on_time'
assert classify(start,after,start+timedelta(minutes=1),None)=='pending_checkout'
assert classify(start,after,start+timedelta(minutes=1),after)=='late'
assert classify(start,after,start+timedelta(minutes=1),before)=='pending_checkout'
assert classify(start,after,None,None,holiday=True)=='off'
assert classify(start,after,None,None,leave=1)=='leave'
assert classify(start,after,None,None,duty=1)=='on_duty'
assert classify(start,after,None,None,leave=.5)=='partial_day'
assert classify(None,after,None,None)=='unconfigured'
print('PASS: pre-shift exclusion, zero grace, completed late pairs, leave, duty, holidays and missing shift')

def stamp(t): return datetime.fromisoformat('2026-11-16T'+t)
start=stamp('09:00:00')
for name,out,inside in [('Mohan','09:10:51','09:10:53'),('Paul','09:08:43','09:08:45'),('Sanisha','09:00:05','09:00:11')]:
    logs=[(stamp(out),'OUT'),(stamp(inside),'IN')]
    before=list(logs)
    first,checkout,_=ns['punch_summary'](logs)
    assert checkout is None
    assert classify(start,stamp('13:00:00'),first,checkout)=='pending_checkout'
    text=ns['punch_details'](SimpleNamespace(employee_name=name,name=name),logs,start)
    assert f'Check-in: {inside} AM' in text and 'Check-out: Pending' in text
    assert f'OUT {out} AM → IN {inside} AM' in text
    if name=='Sanisha': assert 'Late by 0m 11s' in text
    assert logs==before
    logs.append((stamp('18:00:00'),'OUT'))
    first,checkout,_=ns['punch_summary'](logs)
    assert classify(start,stamp('19:00:00'),first,checkout)=='late'
    logs.append((stamp('18:05:00'),'IN'))
    assert ns['punch_summary'](logs)[1] is None
assert ns['punch_summary']([(start,'OUT'),(start,'IN')])[1] is None
assert ns['punch_summary']([(start,'OUT')])[:2]==(None,None)
assert ns['punch_summary']([])[:2]==(None,None)
print('PASS: exact reported punches, seconds, no mutation, equal-time OUT, valid checkout and reopened session')
