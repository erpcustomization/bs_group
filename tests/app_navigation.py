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
    assert routes['BS HR'] is None and routes['BS AMC'] is None
    assert routes['BS Approvals'].endswith('/employee-advance')
    s.scope.return_value='sales';routes=m.destinations()
    assert routes['BS Sales'].endswith('/lead') and routes['BS Project'] is None
    s.scope.return_value='presales';assert m.destinations()['BS Sales'].endswith('/presales-request')
    s.scope.return_value=None;h.can_manage.return_value=True
    assert m.destinations()['BS HR'].endswith('/hr-dashboard')
print('PASS system login, portal preservation, role scope, read permissions and HR guard')
