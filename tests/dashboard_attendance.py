import ast
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
path=Path(__file__).parents[1]/'bsgroup/dashboard_attendance.py'
tree=ast.parse(path.read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='summarize')
ns={'datetime':datetime,'time':time}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(path),'exec'),ns)
def stamp(t): return datetime.fromisoformat('2026-11-01T'+t).replace(tzinfo=ZoneInfo('Asia/Dubai'))
def calc(logs,now):return ns['summarize']([dict(time=stamp(t),log_type=k) for t,k in logs],stamp(now))
r=calc([('09:15','IN')],'10:00')
assert (r['late_minutes'],r['worked_minutes'],r['available_minutes'],r['projected_minutes'])==(15,45,525,525)
assert calc([('08:30','IN')],'19:00')['worked_minutes']==540
r=calc([('09:15','IN'),('12:00','OUT'),('13:00','IN')],'18:30')
assert r['worked_minutes']==465 and r['remaining_minutes']==0
assert calc([('09:15','IN'),('10:00','IN'),('17:00','OUT')],'18:00')['worked_minutes']==465
assert calc([('09:15','IN'),('12:00','OUT')],'15:00')['worked_minutes']==165
assert calc([],'10:00')['state']=='no_checkin'
assert calc([('11:00','IN')],'10:00')['check_in'] is None
assert calc([('09:15','')],'10:00')['unknown_logs']
print('PASS: 9:15 example, early arrival, 6 PM cap, breaks, duplicate punches, checkout, empty/future/untyped logs')
