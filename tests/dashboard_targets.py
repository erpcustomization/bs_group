import ast
from pathlib import Path
from types import SimpleNamespace as NS
from datetime import date
import sys
p=Path(__file__).parents[1]/'bsgroup/dashboard_targets.py'
module=ast.parse(p.read_text(encoding='utf-8-sig'))
ns={'frappe':None,'flt':lambda x:float(x or 0),'getdate':lambda x:date.fromisoformat(x)}
for f in module.body:
    if isinstance(f,ast.FunctionDef):
        f.decorator_list=[]
        exec(compile(ast.Module(body=[f],type_ignores=[]),str(p),'exec'),ns)
assert ns['progress'](100,125)==dict(target=100.0,achieved=125.0,remaining=0,percent=125.0)
assert ns['progress'](0,30)['percent'] is None
assert ns['progress'](100,-10)['remaining']==110
class D(dict):
    __getattr__=dict.get
calls=[]
def get_all(dt,filters=None,**kw):
    calls.append((dt,filters))
    if dt=='Employee':
        rows=[D(name='e1',employee_name='Sales One',user_id='one@test',company='AE'),D(name='e2',employee_name='Sales Two',user_id='two@test',company='AE')]
        return [e for e in rows if not filters.get('user_id') or e.user_id==filters['user_id']]
    if dt=='Has Role':return ['one@test','two@test']
    if dt=='Sales Person':return [D(name=filters['employee'])]
    if dt=='Target Detail':return [D(target_amount=100,custom_gp_target=20,custom_invoiced_gp_target=0)]
    if dt=='Sales Target GP Entry':return [D(name='actual')]
def get_doc(*args):return D(monthly_data=[D(invoiced_sales_revenue=40,invoiced_sales_gp=8)])
f=NS(session=NS(user='one@test'),get_list=lambda *a,**k:['AE'],get_all=get_all,get_doc=get_doc,db=NS(get_value=lambda dt,*a:1 if dt=='User' else 'AED'))
ns['frappe']=f
sys.modules['erpnext.accounts.utils']=NS(get_fiscal_year=lambda *a,**k:('2026',))
r=ns['overview']('2026-11-03')
assert len(r['cards'])==1 and r['cards'][0]['user']=='one@test'
assert r['cards'][0]['sales']['percent']==40 and r['cards'][0]['gp']['percent']==40
f.session.user='mohan@bitssecureit.com'
assert len(ns['overview']('2026-11-03')['cards'])==2
print('PASS: own-user isolation, chairman scope, annual actuals, legacy GP fallback, missing target and overachievement')
