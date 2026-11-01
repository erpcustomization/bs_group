import ast
from pathlib import Path
from types import SimpleNamespace as Row
source = Path(__file__).parents[1] / 'bsgroup/work_dashboard.py'
fn = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'presales_summary')
def rows(dt, **kwargs):
    if dt == 'Presales Request':
        return [Row(name='p1', status='Open', docstatus=1),Row(name='p2', status='Submitted to Sales', docstatus=1),Row(name='p3',status='Open',docstatus=2)]
    return [Row(name='d1',docstatus=0,custom_deal_status='Costing in Progress'),Row(name='d2',docstatus=1,custom_deal_status='Quoted')]
def events(dt, **kwargs):
    assert ['reference_name','in',['d1','d2']] in kwargs['filters']
    assert ['creation','>=','2026-10-01'] in kwargs['filters']
    return [Row(reference_name='d2'),Row(reference_name='d2')]
fake = Row(has_permission=lambda *a:True,get_list=rows,get_all=events)
ns = {'frappe':fake}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(source),'exec'),ns)
assert ns['presales_summary']('2026-10-01','2026-11-01') == {'open_requests':1,'pending_dcs':1,'submitted':1}
fake.has_permission = lambda *a:False
assert ns['presales_summary']('2026-10-01','2026-11-01') == {'open_requests':0,'pending_dcs':0,'submitted':0}
print('PASS: backlog, closed/cancelled exclusions, submission event dates, deduplication, permission gates')
