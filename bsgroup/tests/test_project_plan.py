import importlib.util
import json
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch


class Record(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class ProjectPlanTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f._ = lambda text: text
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.PermissionError = PermissionError
        def throw(text, exc=ValueError): raise exc(text)
        self.f.throw = throw
        self.f.parse_json = json.loads
        self.f.generate_hash = lambda **kw: 'testhash'
        self.f.session = Record(user='assigned@example.com')
        self.f.get_meta = Mock(return_value=Record(has_field=lambda name:True))
        self.project = Record(name='P-A',project_name='Project A',company='A',status='Open',check_permission=Mock())
        self.task = Record(name='TASK-A',project='P-A',subject='Activity',description='Scope',status='Open',modified='2026-11-10 12:00:00',
                           exp_start_date=None,exp_end_date=None,priority='Medium',check_permission=Mock(),save=Mock())
        self.f.get_doc = Mock(side_effect=lambda dt,name,**kw: self.project if dt=='Project' else self.task)
        self.f.has_permission = Mock(return_value=True)
        self.f.get_list = Mock(return_value=[])
        self.f.get_all = Mock(return_value=[])
        self.f.db = Record(savepoint=Mock(),rollback=Mock(),exists=Mock(return_value=False),get_value=Mock(return_value=Record(enabled=1,user_type='System User')))
        utils=types.ModuleType('frappe.utils')
        utils.getdate=lambda value=None: datetime.fromisoformat(str(value or '2026-11-11')).date()
        utils.get_datetime=lambda value: datetime.fromisoformat(str(value))
        utils.strip_html=lambda value:value
        self.assign=Record(add=Mock(),remove=Mock())
        form=types.ModuleType('frappe.desk.form');form.assign_to=self.assign
        self.patch=patch.dict(sys.modules,{'frappe':self.f,'frappe.utils':utils,'frappe.desk.form':form})
        self.patch.start()
        spec=importlib.util.spec_from_file_location('plan_test',Path(__file__).resolve().parents[1]/'project_plan.py')
        self.plan=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.plan)
        self.task.meta=Record(has_field=lambda name:True)

    def tearDown(self):self.patch.stop()

    def save(self,**kw):
        args=dict(project='P-A',task='TASK-A',subject='Updated',description='Revised',start_date='2026-11-11',end_date='2026-11-12',
                  assigned_to=[],expected_modified=self.task.modified,expected_assignees=[])
        args.update(kw)
        return self.plan.save_task(**args)

    def test_read_denial_precedes_task_query(self):
        self.project.check_permission.side_effect=PermissionError()
        with self.assertRaises(PermissionError):self.plan.get_plan('P-A')
        self.f.get_list.assert_not_called()

    def test_autosave_status_only_keeps_assigned_user_endpoint(self):
        with patch.object(self.plan, 'save_task') as save, patch.object(self.plan, 'set_task_status') as status, patch.object(self.plan, 'get_plan', return_value={'rows':[self.task], 'user_names':{}}):
            result=self.plan.autosave_task('P-A','TASK-A',{'status':'Delayed'},self.task.modified,[])
            save.assert_not_called()
            status.assert_called_once_with('P-A','TASK-A','Delayed',self.task.modified)
            self.assertEqual(result['row'],self.task)

    def test_autosave_combined_update_uses_new_version_and_rolls_back(self):
        self.f.db.get_value.return_value='2026-11-11 13:00:00'
        with patch.object(self.plan, 'save_task') as save, patch.object(self.plan, 'set_task_status',side_effect=ValueError('dependency')) as status:
            with self.assertRaises(ValueError):
                self.plan.autosave_task('P-A','TASK-A',{'subject':'Changed','status':'Completed'},self.task.modified,[])
            self.assertEqual(save.call_args.kwargs['description'],'Scope')
            status.assert_called_once_with('P-A','TASK-A','Completed','2026-11-11 13:00:00')
            self.f.db.rollback.assert_called_with(save_point='plan_autosave_testhash')

    def test_autosave_rejects_stale_or_unknown_fields(self):
        with patch.object(self.plan,'save_task') as save, patch.object(self.plan,'set_task_status') as status:
            for changes,version in [({'status':'Open'},'2000-01-01'),({'project':'P-B'},self.task.modified),({},self.task.modified)]:
                with self.assertRaises(ValueError):self.plan.autosave_task('P-A','TASK-A',changes,version,[])
            save.assert_not_called();status.assert_not_called()

    def test_plan_query_is_project_scoped_and_permission_filtered(self):
        self.plan.get_plan('P-A')
        args=self.f.get_list.call_args.kwargs
        self.assertEqual(args['filters'],{'project':'P-A','is_template':0})
        self.assertNotIn('ignore_permissions',args)

    def test_no_task_permission_does_not_query_tasks(self):
        self.f.has_permission.return_value=False
        result=self.plan.get_plan('P-A')
        self.f.get_list.assert_not_called();self.assertFalse(result['can_read_tasks'])

    def test_save_updates_same_task_and_native_assignment(self):
        result=self.save(assigned_to=['user@example.com'])
        self.assertEqual(result['name'],'TASK-A');self.task.save.assert_called_once()
        self.assertEqual(self.assign.add.call_args.args[0]['name'],'TASK-A')
        self.assertEqual(self.assign.add.call_args.args[0]['assign_to'],['user@example.com'])

    def test_cross_project_and_stale_writes_refused_before_save(self):
        for kw in ({'project':'P-B'}, {'expected_modified':'2000-01-01'},{'expected_assignees':['another']}, {'start_date':'2026-11-13'}):
            if 'project' in kw:self.project.name='P-B'
            with self.subTest(kw=kw),self.assertRaises((ValueError,PermissionError)):self.save(**kw)
            self.project.name='P-A'
        self.task.save.assert_not_called();self.assertEqual(self.f.db.rollback.call_count,4)

    def test_write_permission_and_terminal_guard(self):
        self.task.check_permission.side_effect=PermissionError()
        with self.assertRaises(PermissionError):self.save()
        self.task.check_permission.side_effect=None
        self.task.status='Completed'
        with self.assertRaises(ValueError):self.save()
        self.task.save.assert_not_called()

    def test_ineligible_user_does_not_gain_sharing(self):
        self.f.has_permission.return_value=False
        with self.assertRaises(PermissionError):self.save(assigned_to=['other'])
        self.assign.add.assert_not_called();self.task.save.assert_not_called()

    def test_retained_assignment_not_duplicated_and_due_date_synced(self):
        self.f.get_all.return_value=[Record(name='TODO-A',allocated_to='user',date='2026-11-11',description='Old')]
        self.save(assigned_to=['user'],expected_assignees=['user'])
        self.assign.add.assert_not_called();self.assign.remove.assert_not_called()
        self.assertEqual(str(self.task.date),'2026-11-12')

    def test_post_save_assignment_failure_rolls_back(self):
        self.assign.add.side_effect=ValueError('assignment failed')
        with self.assertRaises(ValueError):self.save(assigned_to=['user'])
        self.f.db.rollback.assert_called_once_with(save_point='project_plan_testhash')

    def test_datetime_time_is_preserved(self):
        self.assertEqual(str(self.plan._dated_value('2026-11-11 09:30:00','2026-11-12')),'2026-11-12 09:30:00')

    def test_only_native_template_statuses_are_normalized(self):
        self.task.is_new=lambda: True
        self.task.meta=Record(get_field=lambda name:Record(options='Project Planning\nCompleted\nCancelled'))
        for template,source,status,expected in [(1,None,'Template','Project Planning'),(0,'SOURCE','Open','Project Planning'),(0,None,'Open','Open'),(0,'SOURCE','Completed','Completed')]:
            self.task.update(is_template=template,template_task=source,status=status)
            self.plan.validate_template_status(self.task)
            self.assertEqual(self.task.status,expected)

    def test_standard_template_statuses_are_preserved(self):
        self.task.is_new=lambda: True
        self.task.meta=Record(get_field=lambda name:Record(options='Open\nTemplate\nCompleted'))
        self.task.update(is_template=1,status='Template')
        self.plan.validate_template_status(self.task)
        self.assertEqual(self.task.status,'Template')

    def test_assigned_user_status_write_is_narrow_and_native(self):
        self.f.has_permission.return_value=False
        self.f.db.exists.return_value=True
        result=self.plan.set_task_status('P-A','TASK-A','In Progress',self.task.modified)
        self.assertEqual(result['status'],'In Progress')
        self.task.save.assert_called_once_with(ignore_permissions=True)
        self.assertEqual(self.task.subject,'Activity')
        self.assertEqual(self.task.custom_bs_plan_status_managed,1)

    def test_unassigned_status_write_and_forged_status_rejected(self):
        self.f.has_permission.return_value=False
        with self.assertRaises(PermissionError): self.plan.set_task_status('P-A','TASK-A','Completed',self.task.modified)
        self.f.has_permission.return_value=True
        with self.assertRaises(ValueError): self.plan.set_task_status('P-A','TASK-A','Administrator',self.task.modified)
        with self.assertRaises(ValueError): self.plan.set_task_status('P-A','TASK-A','Open','2000-01-01')
        self.task.save.assert_not_called()

    def test_status_cross_project_and_native_failure_roll_back(self):
        self.task.project='P-B'
        with self.assertRaises(PermissionError):self.plan.set_task_status('P-A','TASK-A','Open',self.task.modified)
        self.task.project='P-A';self.task.save.side_effect=ValueError('dependency still open')
        with self.assertRaises(ValueError):self.plan.set_task_status('P-A','TASK-A','Completed',self.task.modified)
        self.assertEqual(self.f.db.rollback.call_count,2)

    def test_completed_task_reopen_requires_native_write(self):
        self.task.status='Completed';self.f.has_permission.return_value=False;self.f.db.exists.return_value=True
        with self.assertRaises(PermissionError):self.plan.set_task_status('P-A','TASK-A','Open',self.task.modified)
        self.task.save.assert_not_called()

    def test_work_requires_assignment_and_readable_project(self):
        with self.assertRaises(PermissionError):self.plan.save_work('P-A','TASK-A','Work')
        self.f.db.exists.return_value=True
        with self.assertRaises(ValueError):self.plan.save_work('P-A','TASK-A','  ')
        self.task.project='P-B'
        with self.assertRaises(PermissionError):self.plan.save_work('P-A','TASK-A','Work')

    def test_work_author_and_reference_are_server_controlled_and_html_escaped(self):
        self.f.db.exists.return_value=True;self.f.db.get_value.return_value='Assigned User'
        entry=Record(name='COMMENT-A',insert=Mock())
        entry.insert.return_value=entry
        def get_doc(dt,name=None,**kw):
            if isinstance(dt,dict):entry.update(dt);return entry
            return self.project if dt=='Project' else self.task
        self.f.get_doc.side_effect=get_doc
        self.plan.save_work('P-A','TASK-A','<img src=x onerror=alert(1)>\nInstalled camera')
        self.assertEqual(entry.reference_name,'TASK-A')
        self.assertEqual(entry.comment_email,'assigned@example.com')
        self.assertIn('&lt;img',entry.content);self.assertNotIn('<img',entry.content)
        self.assertIn('2026-11-11',entry.content)

    def test_deadline_job_preserves_only_managed_execution_status(self):
        base=type('Base',(),{'update_status':lambda self:'native','get':lambda self,name:self.managed})
        mixed=type('Mixed',(self.plan.ProjectPlanTaskMixin,base),{})
        task=mixed();task.managed=True;task.status='In Progress'
        self.assertIsNone(task.update_status())
        task.managed=False;self.assertEqual(task.update_status(),'native')
        task.managed=True;task.status='Pending from Client';self.assertEqual(task.update_status(),'native')


if __name__=='__main__':unittest.main()
