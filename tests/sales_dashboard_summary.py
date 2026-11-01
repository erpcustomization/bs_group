import ast
from pathlib import Path
from types import SimpleNamespace as NS

class Row(dict):
    __getattr__ = dict.__getitem__

source = Path(__file__).parents[1] / 'bsgroup/work_dashboard.py'
functions = [n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name in ('aggregate_sales', 'sales_summary')]
def rows(dt, **kw):
    if dt == 'Opportunity':
        assert kw['filters']=={'opportunity_owner':'sales@example.com'}
        return ['own']
    assert kw['filters']==[['docstatus','=',1],['transaction_date','>=','2026-10-01'],['transaction_date','<','2026-11-01']]
    return [Row(company='AE',base_grand_total=100,status='Open',custom_pipeline_stage='Won',opportunity='own',owner='presales@example.com'),
            Row(company='AE',base_grand_total=50,status='Lost',custom_pipeline_stage='Lost',opportunity='own',owner='other'),
            Row(company='OM',base_grand_total=20,status='Open',custom_pipeline_stage='Open',opportunity=None,owner='sales@example.com'),
            Row(company='AE',base_grand_total=999,status='Open',custom_pipeline_stage='Won',opportunity='someone-else',owner='sales@example.com')]
fake=NS(session=NS(user='sales@example.com'),has_permission=lambda *a:True,get_list=rows,
    get_meta=lambda *a:NS(has_field=lambda f:True),get_cached_value=lambda dt,company,f:{'AE':'AED','OM':'OMR'}[company])
ns={'frappe':fake}
exec(compile(ast.fix_missing_locations(ast.Module(body=functions,type_ignores=[])),str(source),'exec'),ns)
result=ns['sales_summary']('2026-10-01','2026-11-01')
assert result['quoted']=={'count':3,'amounts':{'AED':150,'OMR':20}}
assert result['won']=={'count':1,'amounts':{'AED':100}}
assert result['lost']=={'count':1,'amounts':{'AED':50}}
fake.has_permission=lambda *a:False
assert ns['sales_summary']('2026-10-01','2026-11-01')['quoted']['count']==0
print('PASS: own salesperson, permission/date/submitted filters, won/lost classification, currency separation and empty access')
