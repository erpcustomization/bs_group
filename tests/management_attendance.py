import ast
from datetime import datetime, timedelta
from pathlib import Path

path=Path(__file__).parents[1]/'bsgroup/management_attendance.py'
functions=[node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name=='classify']
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
