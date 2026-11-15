"""Checks for technical role lifecycle and new-viewer record boundaries."""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch

root = Path(__file__).resolve().parents[1]
f = types.ModuleType('frappe')
f.session = types.SimpleNamespace(user='tech@example.com')
f.db = types.SimpleNamespace(exists=lambda *a: True, escape=lambda s: "'" + s.replace("'", "''") + "'")
f.get_roles = Mock(return_value=['BS Project Support Viewer', 'Projects User'])
f.get_meta = Mock(return_value=types.SimpleNamespace(permissions=[]))

class User:
    def __init__(self, roles, enabled=1, user_type='System User'):
        self.roles = [types.SimpleNamespace(role=r) for r in roles]
        self.enabled, self.user_type = enabled, user_type
    def append(self, field, row):
        getattr(self, field).append(types.SimpleNamespace(**row))
    def set(self, field, value):
        setattr(self, field, value)

with patch.dict(sys.modules, {'frappe': f}):
    spec = importlib.util.spec_from_file_location('support', root/'bsgroup/project_support_access.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    for role in m.TECHNICAL_ROLES:
        user = User([role, 'Employee'])
        m.sync_user(user); m.sync_user(user)
        assert [r.role for r in user.roles] == [role, 'Employee', m.ROLE]
    for user in (User(['Sales User']), User(['Technician'], 0), User(['Technician'], user_type='Website User')):
        m.sync_user(user); assert m.ROLE not in [r.role for r in user.roles]
    user = User(['Employee', m.ROLE]); m.sync_user(user)
    assert [r.role for r in user.roles] == ['Employee']
    assert m.limited_scheduler()
    assert not m.limited_scheduler('Administrator')
    own = types.SimpleNamespace(resource='tech@example.com')
    other = types.SimpleNamespace(resource='other@example.com')
    assert m.scheduler_permission({'tech_task_scheduler_list': [own]}) is None
    assert m.scheduler_permission({'tech_task_scheduler_list': [own, other]}) is False
    assert m.scheduler_permission({'tech_task_scheduler_list': []}) is False
    query = m.scheduler_query()
    assert 'NOT EXISTS' in query and "COALESCE(s.resource,'')!='tech@example.com'" in query
    f.get_meta.return_value.permissions = [types.SimpleNamespace(role='Projects User', read=1, if_owner=0)]
    assert not m.limited_scheduler()
    assert m.scheduler_query() == ''
    assert m.scheduler_permission({'tech_task_scheduler_list': [other]}) is None
    f.get_meta.return_value.permissions[0].if_owner = 1
    assert m.limited_scheduler()  # owner-only permission is not unrestricted access
    f.get_roles.return_value = ['Sales User']
    assert not m.limited_scheduler()

# Ensure both task reports use the permission-aware API and request all accessible rows.
for report in ('task_summary_report', 'task_scheduler_report'):
    src = (root/f'bsgroup/bs_group/report/{report}/{report}.py').read_text(encoding='utf-8')
    assert 'tasks = frappe.get_list(' in src and 'limit_page_length=0' in src
    assert 'tasks = frappe.get_all(' not in src
src = (root/'bsgroup/bs_group/report/tech_task_scheduler_report/tech_task_scheduler_report.py').read_text(encoding='utf-8')
assert 'ttsl.resource = %(support_viewer)s' in src
assert 'values["support_viewer"] = frappe.session.user' in src
print('PASS technical role eligibility, idempotence, removal, existing-reader preservation, own/mixed/empty scheduler boundaries and report filtering')
