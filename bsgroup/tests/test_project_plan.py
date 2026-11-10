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
        self.project = Record(name='P-A',project_name='Project A',company='A',status='Open',check_permission=Mock())
        self.task = Record(name='TASK-A',project='P-A',subject='Activity',description='Scope',status='Open',modified='2026-11-10 12:00:00',
                           exp_start_date=None,exp_end_date=None,priority='Medium',check_permission=Mock(),save=Mock())
        self.f.get_doc = Mock(side_effect=lambda dt,name,**kw: self.project if dt=='Project' else self.task)
        self.f.has_permission = Mock(return_value=True)
        self.f.get_list = Mock(return_value=[])
        self.f.get_all = Mock(return_value=[])
        self.f.db = Record(savepoint=Mock(),rollback=Mock(),get_value=Mock(return_value=Record(enabled=1,user_type='System User')))
        utils=types.ModuleType('frappe.utils')
        utils.getdate=lambda value: datetime.fromisoformat(str(value)).date()
        utils.get_datetime=lambda value: datetime.fromisoformat(str(value))
        utils.strip_html=lambda value:value
        self.assign=Record(add=Mock(),remove=Mock())
        form=types.ModuleType('frappe.desk.form');form.assign_to=self.assign
        self.patch=patch.dict(sys.modules,{'frappe':self.f,'frappe.utils':utils,'frappe.desk.form':form})
        self.patch.start()
        spec=importlib.util.spec_from_file_location('plan_test',Path(__file__).resolve().parents[1]/'project_plan.py')
        self.plan=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.plan)

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


if __name__=='__main__':unittest.main()
