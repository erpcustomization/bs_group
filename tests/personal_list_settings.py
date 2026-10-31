import ast
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

source = Path(__file__).resolve().parents[1] / 'bsgroup/personal_list_settings.py'
tree = ast.parse(source.read_text())
class StripImports(ast.NodeTransformer):
    def visit_ImportFrom(self, node): return None
    def visit_Import(self, node): return None
tree = StripImports().visit(tree)
for node in tree.body:
    if isinstance(node, ast.FunctionDef): node.decorator_list = []
saved = []
checks = []
meta = NS(fields=[NS(fieldname='customer')])
f = NS(session=NS(user='priya@example.test'), get_roles=lambda:[],
       has_permission=lambda *a, **kw: checks.append((a,kw)),
       parse_json=lambda v: json.loads(v) if isinstance(v,str) else v,
       get_meta=lambda dt:meta)
env = {'frappe':f, 'math':math, 'original':lambda *a:'admin-path',
       'get_user_settings':lambda dt:'{"bs_column_widths":{"customer":150}}',
       'update_user_settings':lambda dt,s: saved.append((dt,s))}
exec(compile(tree,str(source),'exec'),env)
env['save_listview_settings']('Opportunity', {'fields':json.dumps([
    {'fieldname':'name','width':280}, {'fieldname':'invalid','width':400},
    {'fieldname':'customer','width':'nan'}]),'allow_edit':1}, ['customer'])
assert saved == [('Opportunity',{'bs_column_widths':{'name':280.0,'customer':150}})]
assert checks[0][0] == ('Opportunity','read')
f.session.user='Administrator'
assert env['save_listview_settings']('Opportunity',{}) == 'admin-path'
assert len(saved)==1
print('PASS: older-client resize saves only personal widths, checks access, preserves admin behavior')
