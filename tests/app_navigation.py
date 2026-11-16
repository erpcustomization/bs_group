import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

root=Path(__file__).resolve().parents[1]
f=types.ModuleType('frappe')
f.local=types.SimpleNamespace(flags=types.SimpleNamespace())
f.db=types.SimpleNamespace(get_value=Mock(return_value='System User'),exists=lambda *a:True)
f.scrub=lambda s:s.lower().replace(' ','_')
f.has_permission=lambda dt,p:dt in {'Lead','Project','HD Ticket','Employee Advance','Presales Request'}
f.get_roles=Mock(return_value=['Projects User'])
s=types.ModuleType('bsgroup.scoped_sales_access');s.scope=Mock(return_value=None);s.SCREENS={'sales':('Lead',),'presales':('Presales Request',)}
h=types.ModuleType('bsgroup.hr_management');h.can_manage=Mock(return_value=False)
with patch.dict(sys.modules,{'frappe':f,'bsgroup.scoped_sales_access':s,'bsgroup.hr_management':h}):
    spec=importlib.util.spec_from_file_location('navigation',root/'bsgroup/app_navigation.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.on_session_creation(types.SimpleNamespace(user='employee@example.com'))
    assert f.local.flags.home_page=='/desk/my-work-dashboard'
    f.local.flags=types.SimpleNamespace();f.db.get_value.return_value='Website User'
    m.on_session_creation(types.SimpleNamespace(user='portal@example.com'))
    assert not hasattr(f.local.flags,'home_page')
    routes=m.destinations();assert routes['BS Project'].endswith('/project')
    assert routes['BS User Management'] is None
    assert routes['BS HR'] is None and routes['BS AMC'] is None
    assert routes['BS Approvals'].endswith('/employee-advance')
    s.scope.return_value='sales';routes=m.destinations()
    assert routes['BS Sales'].endswith('/lead') and routes['BS Project'] is None
    s.scope.return_value='presales';assert m.destinations()['BS Sales'].endswith('/presales-request')
    s.scope.return_value=None;h.can_manage.return_value=True
    assert m.destinations()['BS HR'].endswith('/hr-dashboard')
    f.get_roles.return_value=['System Manager']
    assert m.destinations()['BS User Management'].endswith('/bs-user-management')
    with patch.object(f, 'has_permission', lambda dt,p: dt == 'Material Request'):
        assert m.destinations()['BS Procurement'] == '/desk/bs-group/bs-procurement'
    with patch.object(f, 'has_permission', lambda dt,p: False):
        assert m.destinations()['BS Procurement'] is None
    f.session=types.SimpleNamespace(user='mithun@example.com')
    f.get_roles.return_value=['Projects User']
    f.has_permission=lambda dt,p: dt in {'Project','Task','Site Survey Request','Tech Task Scheduler'}
    f.get_doc=lambda dt,name:types.SimpleNamespace(disabled=0,
        ref_doctype='Tech Task Scheduler' if name=='Tech Task Scheduler Report' else 'Task',
        roles=[types.SimpleNamespace(role='Sales Manager' if name=='Tech Task Scheduler Report' else 'Projects User')])
    links=m.project_support_links()
    assert [x['label'] for x in links]==['Project','Site Survey Request','Task','Tech Task Scheduler','Task Summary Report','Task Scheduler Report']
    assert all('bs_app=BS%20Project' in x['href'] for x in links)
    assert not any(x['label']=='Delivery Request' for x in links)
    s.scope.return_value='sales'
    assert m.project_support_links()==[]
    s.scope.return_value=None
    f.has_permission=lambda dt,p:False
    assert m.project_support_links()==[]
print('PASS system login, portal preservation, role scope, read permissions and HR guard')
print('PASS Project Support submenu: DocType access, report roles, scoped users and denied links')
