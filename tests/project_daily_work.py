import importlib.util, sys, types, unittest
from pathlib import Path
from unittest.mock import Mock, patch

class R(dict):
    __getattr__=dict.get
    __setattr__=dict.__setitem__

class DailyWorkTests(unittest.TestCase):
    def setUp(self):
        self.f=types.ModuleType('frappe');self.f._=lambda s:s
        self.f.conf={};self.f.local=R(site='erp-bitssecureit.u.frappe.cloud');self.f.session=R(user='assigned@example.com')
        self.f.throw=lambda s:(_ for _ in ()).throw(ValueError(s))
        self.f.db=R(get_value=Mock(return_value=None));self.f.get_all=Mock(return_value=[])
        self.sheet=R(name='TS-1',check_permission=Mock(),save=Mock(),append=Mock())
        self.entry=R(insert=Mock())
        def insert(**kw): self.entry.name=kw['set_name'];return self.entry
        self.entry.insert.side_effect=insert
        def get_doc(dt,*args,**kw):
            if isinstance(dt,dict):self.entry.update(dt);return self.entry
            return self.sheet
        self.f.get_doc=Mock(side_effect=get_doc);self.f.new_doc=Mock(return_value=self.sheet)
        self.f.enqueue=Mock()
        self.project=R(name='P-1',company='AE',status='Open',is_new=lambda:False)
        self.task=R(name='T-1',project='P-1',status='In Progress')
        utils=types.ModuleType('frappe.utils');utils.getdate=lambda:'2026-11-14'
        plan=types.ModuleType('bsgroup.project_plan');plan.WORK_SUBJECT='Project Plan daily work'
        workspace=types.ModuleType('bsgroup.project_workspace');workspace.own_employee=lambda company:'EMP-1'
        self.patch=patch.dict(sys.modules,{'frappe':self.f,'frappe.utils':utils,'bsgroup.project_plan':plan,'bsgroup.project_workspace':workspace});self.patch.start()
        spec=importlib.util.spec_from_file_location('daily',Path(__file__).resolve().parents[1]/'bsgroup/project_daily_work.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
    def tearDown(self):self.patch.stop()
    def test_uae_only(self):
        self.assertTrue(self.m.enabled());self.f.local.site='erp-om.k.frappe.cloud';self.assertFalse(self.m.enabled())
    def test_dated_own_draft_and_no_invented_hours(self):
        result=self.m.capture(self.project,self.task,'Installed <camera>','request-1')
        self.assertEqual(result['timesheet'],'TS-1');self.assertEqual(self.sheet.user,'assigned@example.com')
        row=self.sheet.append.call_args.args[1]
        self.assertEqual((row['project'],row['task'],row['custom_bs_work_date'],row['hours']),('P-1','T-1','2026-11-14',0))
        self.assertNotIn('from_time',row);self.assertIn('&lt;camera&gt;',self.entry.content)
        self.sheet.check_permission.assert_called_once_with('create');self.sheet.save.assert_called_once()
    def test_retry_does_not_duplicate(self):
        self.f.db.get_value.return_value='TS-OLD'
        self.assertEqual(self.m.capture(self.project,self.task,'Work','same')['timesheet'],'TS-OLD')
        self.f.new_doc.assert_not_called();self.entry.insert.assert_not_called()
    def test_reuses_only_own_daily_draft(self):
        self.f.get_all.return_value=['TS-1'];self.m.capture(self.project,self.task,'Work','one')
        filters=self.f.get_all.call_args.kwargs['filters']
        self.assertEqual(filters['user'],'assigned@example.com');self.assertEqual(filters['docstatus'],0)
        self.assertEqual(filters['custom_date'],'2026-11-14');self.sheet.check_permission.assert_called_once_with('write')
    def test_terminal_and_missing_request_rejected(self):
        for status in self.m.TERMINAL:
            self.task.status=status
            with self.assertRaises(ValueError):self.m.capture(self.project,self.task,'Work','r')
        self.task.status='Open'
        with self.assertRaises(ValueError):self.m.capture(self.project,self.task,'Work',None)
    def test_all_tasks_required_empty_cancelled_or_pending_do_not_complete(self):
        for statuses in ([],['Completed','Open'],['Completed','Cancelled']):
            self.f.get_all.return_value=statuses;self.m.complete_project(self.project)
            self.assertEqual(self.project.status,'Open')
        self.f.get_all.return_value=['Completed','Completed'];self.m.complete_project(self.project)
        self.assertEqual((self.project.status,self.project.percent_complete),('Completed',100))
        self.project.status='Cancelled';self.m.complete_project(self.project);self.assertEqual(self.project.status,'Cancelled')
    def test_closed_uses_native_completed_and_reconcile_after_commit(self):
        self.task.status='Closed';self.m.normalize_closed(self.task);self.assertEqual(self.task.status,'Completed')
        self.task.is_new=lambda:False;self.task.has_value_changed=lambda f:True
        self.m.task_updated(self.task);self.assertTrue(self.f.enqueue.call_args.kwargs['enqueue_after_commit'])

if __name__=='__main__':unittest.main()
