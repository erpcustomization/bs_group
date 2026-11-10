"""Place labels use stored names only and never perform external lookups."""
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch
ROOT=Path(__file__).resolve().parents[1]
pkg=types.ModuleType('bsgroup');pkg.__path__=[str(ROOT/'bsgroup')]
f=types.ModuleType('frappe');f.cache=types.SimpleNamespace(get_value=Mock(return_value=None))
report=types.ModuleType('report');report.get_head_offices=Mock(return_value=['OFFICE']);report.get_place=Mock(return_value='Muscat Office')
with patch.dict(sys.modules,{'bsgroup':pkg,'frappe':f,'bsgroup.bs_group.report.employee_checkin_report.employee_checkin_report':report}):
    spec=importlib.util.spec_from_file_location('places',ROOT/'bsgroup/attendance_place.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.describe_location(23.5,58.5)=='Muscat Office · GPS 23.50000, 58.50000'
    report.get_place.assert_called_with(23.5,58.5,['OFFICE'],allow_external=False)
    f.cache.get_value.return_value='Recorded building, Street, Muscat, Oman'
    report.get_place.reset_mock()
    assert m.describe_location(23.5,58.5)=='Recorded building, Street, Muscat, Oman · GPS 23.50000, 58.50000 · © OpenStreetMap contributors'
    report.get_place.assert_not_called()
    f.cache.get_value.return_value='';report.get_place.return_value=None
    assert m.describe_location(25.1,55.3)=='Place name unavailable · GPS 25.10000, 55.30000'
    f.cache.get_value.reset_mock()
    assert m.describe_location(None,55)=='Location not recorded'
    assert m.describe_location(0,0)=='Location not recorded'
    f.cache.get_value.assert_not_called()
    f.cache.get_value.side_effect=RuntimeError('cache unavailable')
    assert m.describe_location(25.1,55.3).endswith('GPS 25.10000, 55.30000')
print('PASS: stored mapped address precedence, configured site label, no external lookup, missing names/GPS, outage fallback')
