import importlib.util, sys, types, unittest
from pathlib import Path
from unittest.mock import Mock, patch

class R(dict):
    __getattr__=dict.get
    __setattr__=dict.__setitem__

class InlineTimesheetTests(unittest.TestCase):
    def setUp(self):
        self.f=types.ModuleType('frappe');self.f._=lambda s:s
        self.f.whitelist=lambda **kw:lambda fn:fn
        self.f.throw=lambda s:(_ for _ in ()).throw(ValueError(s))
        self.enabled=Mock(return_value=True)
        daily=types.ModuleType('bsgroup.project_daily_work');daily.enabled=self.enabled
        self.modules=patch.dict(sys.modules,{'frappe':self.f,'bsgroup.project_daily_work':daily});self.modules.start()
        spec=importlib.util.spec_from_file_location('inline',Path(__file__).resolve().parents[1]/'bsgroup/project_timesheets.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.row=R(name='ROW-1',project='P-1',task='T-1',description='Original',custom_bs_work_date='2026-11-14',hours=0,custom_bs_work_entry='COMMENT-1')
        self.sheet=R(name='TS-1',employee_name='Employee',user='employee@example.com',docstatus=0,status='Draft',time_logs=[self.row],check_permission=Mock(),save=Mock())
        self.project=R(check_permission=Mock())
        self.f.get_doc=Mock(side_effect=lambda dt,*a,**kw:self.project if dt=='Project' else self.sheet)
        self.f.get_list=Mock(return_value=[R(name='TS-1')]);self.f.has_permission=Mock(return_value=True)
        self.f.db=R(get_value=Mock(return_value='Task title'))
    def tearDown(self):self.modules.stop()
    def test_list_contains_only_project_rows(self):
        self.sheet.time_logs.append(R(name='OTHER',project='P-2',description='Private'))
        rows=self.m.lines('P-1')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['work'],'Original')
        self.assertEqual(rows[0]['date'],'2026-11-14');self.assertTrue(rows[0]['editable'])
        self.sheet.check_permission.assert_called_with('read')
        self.assertIn(['Timesheet Detail','project','=','P-1'],self.f.get_list.call_args.kwargs['filters'])
    def test_save_preserves_all_other_fields(self):
        before=dict(self.row);self.m.save_work('P-1','TS-1','ROW-1','Corrected','Original')
        self.assertEqual(self.row,dict(before,description='Corrected'))
        self.sheet.save.assert_called_once_with()
        self.sheet.check_permission.assert_any_call('write')
        self.assertTrue(self.f.get_doc.call_args.kwargs['for_update'])
    def test_stale_update_cannot_overwrite(self):
        with self.assertRaises(ValueError):self.m.save_work('P-1','TS-1','ROW-1','New','Stale')
        self.sheet.save.assert_not_called()
    def test_replayed_success_is_noop(self):
        self.m.save_work('P-1','TS-1','ROW-1','Original','Old')
        self.sheet.save.assert_not_called()
    def test_cross_project_rejected(self):
        with self.assertRaises(ValueError):self.m.save_work('P-2','TS-1','ROW-1','New','Original')
        self.sheet.save.assert_not_called()
    def test_submitted_and_cancelled_are_read_only(self):
        for state in (1,2):
            self.sheet.docstatus=state
            self.assertFalse(self.m.lines('P-1')[0]['editable'])
            with self.assertRaises(ValueError):self.m.save_work('P-1','TS-1','ROW-1','New','Original')
        self.sheet.save.assert_not_called()
    def test_native_permission_denial_stops_write(self):
        self.sheet.check_permission.side_effect=PermissionError('Denied')
        with self.assertRaises(PermissionError):self.m.save_work('P-1','TS-1','ROW-1','New','Original')
        self.sheet.save.assert_not_called()
    def test_oman_not_enabled_and_blank_rejected(self):
        self.enabled.return_value=False
        with self.assertRaises(ValueError):self.m.lines('P-1')
        self.enabled.return_value=True
        with self.assertRaises(ValueError):self.m.save_work('P-1','TS-1','ROW-1',' ','Original')
        self.sheet.save.assert_not_called()

if __name__=='__main__':unittest.main()
