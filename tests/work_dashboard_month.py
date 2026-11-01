import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).parents[1] / 'bsgroup/work_dashboard.py'
fn = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'data')
fn.decorator_list = []
class Row(dict):
    __getattr__ = dict.__getitem__
row = Row(name='allowed', status='Open', creation='2024-02-29', modified='2024-02-29')
calls = []
def get_list(dt, **kwargs):
    assert dt == 'Lead', 'Unreadable document type must not be queried'
    calls.append(kwargs)
    return [row]
def fail(message):
    raise ValueError(message)
fake = SimpleNamespace(has_permission=lambda dt, p: dt == 'Lead', get_meta=lambda dt: SimpleNamespace(has_field=lambda f: True),
    get_list=get_list, throw=fail, session=SimpleNamespace(user='sales@example.com'),
    utils=SimpleNamespace(today=lambda:'2024-02-29', getdate=date.fromisoformat))
ns = {'frappe':fake,'screens':lambda:['Lead','Quotation']}
exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(source), 'exec'), ns)
r = ns['data']('2024-02')
assert r['end'] == '2024-03-01' and len(r['daily']) == 29
assert r['totals'] == {'created':1,'updated':1,'active':1}, 'Overlap must not double count active records'
assert r['daily'][-1] == 1 and len(r['cards']) == 1
assert all(c['filters'][1][1:] == ['<','2024-03-01'] for c in calls)
assert ns['data']('2024-12')['end'] == '2025-01-01'
try:
    ns['data']('not-a-month')
    raise AssertionError('Invalid month accepted')
except ValueError:
    pass
fake.get_list = lambda *a, **k: []
assert ns['data']('2024-02')['totals']['active'] == 0
print('PASS: leap month, year boundary, deduplication, permission gate, empty month, invalid input')
