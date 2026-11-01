"""Dashboard discovery follows roles, without granting document access."""
import ast
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).parents[1] / 'bsgroup/work_dashboard.py'
fn = next(n for n in ast.parse(source.read_text()).body
          if isinstance(n, ast.FunctionDef) and n.name == 'screens')
roles = []
ns = {'frappe': SimpleNamespace(get_roles=lambda: roles,
      session=SimpleNamespace(user='oman.sales@example.com')),
      'scope': lambda: None}
exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), 'exec'), ns)
assert ns['screens']() == []
roles[:] = ['Sales User']
assert ns['screens']() == ['Lead', 'Opportunity', 'Deal Cost Sheet', 'Quotation']
roles[:] = ['Projects User', 'Purchase User']
assert 'Project' in ns['screens']() and 'Purchase Order' in ns['screens']()
assert 'Quotation' not in ns['screens']()
roles[:] = ['Sales User', 'Presales']
assert ns['screens']().count('Deal Cost Sheet') == 1
assert 'Presales Request' in ns['screens']()
print('PASS: role-based dashboard discovery, multi-role deduplication, no-role isolation')
