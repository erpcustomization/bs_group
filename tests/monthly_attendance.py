import ast
from datetime import datetime, date, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

source=Path(__file__).parents[1]/'bsgroup/monthly_attendance.py'
fn=next(n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='office_minutes')
tz=ZoneInfo('Asia/Dubai')
ns=dict(datetime=datetime,time=time,TZ=tz)
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
day=date(2026,10,1)
at=lambda h,m=0:datetime.combine(day,time(h,m),tz)
calc=ns['office_minutes']
later=datetime(2026,11,1,tzinfo=tz)
assert calc(day,[(at(8),'IN'),(at(20),'OUT')],later)[0]==540
assert calc(day,[(at(9,15),'IN'),(at(18,30),'OUT')],later)[0]==525
assert calc(day,[(at(9),'IN'),(at(12,30),'OUT'),(at(13),'IN'),(at(18),'OUT')],later)[0]==510
assert calc(day,[(at(19),'IN'),(at(20),'OUT')],later)[0]==0
assert calc(day,[(at(9),'IN')],later)==(0,at(9),True)
assert calc(day,[(at(9),'IN')],at(10))[0]==60
assert calc(day,[(at(9),'IN'),(at(9,30),'IN'),(at(18),'OUT')],later)[0]==540
assert calc(day,[(at(8),'OUT')],later)==(0,None,False)
print('PASS: 9–6 cap, late arrival, multiple sessions, overtime exclusion, missing checkout, current day, duplicate IN')
