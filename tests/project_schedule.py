import importlib.util
import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch


class R(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.throw = lambda msg: (_ for _ in ()).throw(ValueError(msg))
        self.f.local = R(site='uae-test')
        self.f.session = R(user='employee@example.com')
        self.f.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})
        self.f.db = R(exists=Mock(return_value=False), get_value=Mock(return_value=None),
            commit=Mock(), rollback=Mock(), set_value=Mock())
        self.log = R(insert=Mock())
        self.f.get_doc = Mock(return_value=self.log)
        self.f.has_permission = Mock(return_value=True)
        self.f.get_all = Mock(return_value=[])
        self.utils = types.ModuleType('frappe.utils')
        self.utils.getdate = lambda v: v if isinstance(v, date) else date.fromisoformat(v)
        self.utils.strip_html = lambda s:s
        self.requests = types.ModuleType('requests')
        self.requests.RequestException = type('RequestException', (Exception,), {})
        self.requests.post = Mock(return_value=R(status_code=202))
        self.modules = patch.dict(sys.modules, {'frappe': self.f, 'frappe.utils': self.utils, 'requests': self.requests})
        self.modules.start()
        spec = importlib.util.spec_from_file_location('schedule_under_test', Path(__file__).resolve().parents[1]/'bsgroup/project_schedule.py')
        self.m = importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.day = date(2026, 11, 16)
        self.row = dict(project='P1',project_title='Project & One',task='T1',task_title='<Task>',due_date='2026-11-15',status='Overdue')
        self.candidate = dict(user='employee@example.com',employee_name='Employee')
        self.settings = R(get_password=lambda key:'https://test.environment.api.powerplatform.com/workflows/private/triggers/manual/paths/invoke?sig=placeholder')
        self.p = R(COMPANY='Company - AE',plan=Mock(return_value={'reason':'','shift':'General'}),employees=Mock(return_value=[]))
        self.m.profile = Mock(return_value=self.p)

    def tearDown(self):
        self.modules.stop()

    def test_overdue_and_no_end_date_included(self):
        for end in ('2026-01-01',None):
            self.assertTrue(self.m.eligible_task(R(status='Open',exp_start_date='2026-11-01',exp_end_date=end),self.day))

    def test_completed_closed_cancelled_template_and_future_excluded(self):
        for status in self.m.TERMINAL:
            self.assertFalse(self.m.eligible_task(R(status=status,exp_start_date='2026-01-01'),self.day))
        for start in (None,'2026-11-17'):
            self.assertFalse(self.m.eligible_task(R(status='Open',exp_start_date=start),self.day))

    def test_duplicate_todos_yield_one_row(self):
        self.f.get_all.return_value=[R(reference_name='T1'),R(reference_name='T1')]
        task=R(name='T1',project='P1',status='Open',exp_start_date='2026-11-01',exp_end_date='2026-11-14',subject='Task')
        project=R(name='P1',project_name='Project',company='AE',status='Open')
        self.f.get_doc.side_effect=lambda dt,name: task if dt=='Task' else project
        rows=self.m.task_rows('employee@example.com',self.day,'AE')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['status'],'Overdue')
        self.assertEqual(self.f.get_all.call_args.kwargs['filters']['allocated_to'],'employee@example.com')
        self.f.has_permission.return_value=False
        self.assertEqual(self.m.task_rows('employee@example.com',self.day,'AE'),[])

    def test_calendar_holiday_retained_wfh_is_working(self):
        self.p.plan.return_value={'reason':'Holiday / weekly day off'}
        self.assertTrue(self.m.calendar_plan(R(),self.day)['reason'])
        self.p.plan.return_value={'reason':'Approved on-duty / work-from-home arrangement'}
        self.assertEqual(self.m.calendar_plan(R(),self.day)['reason'],'')

    def test_holiday_tomorrow_no_tasks_or_send(self):
        self.p.employees.return_value=[R(name='E1',employee_name='One',user_id='one@example.com')]
        self.p.plan.return_value={'reason':'Holiday / weekly day off','shift':'General'}
        self.m.task_rows=Mock()
        result=self.m.candidates(self.day,R(send_on_holiday_eve=1),self.day)
        self.assertEqual(result[0]['rows'],[]);self.m.task_rows.assert_not_called()

    def test_message_tomorrow_and_escaped(self):
        body=self.m.message('Employee',self.day,[self.row],'UAE')
        self.assertIn('scheduled for tomorrow (16 November 2026)',body)
        self.assertIn('&lt;Task&gt;',body);self.assertIn('Overdue',body)

    def test_repeat_attempt_never_posts(self):
        self.f.db.exists.return_value=True
        self.assertEqual(self.m.dispatch(self.settings,self.candidate,self.day,[self.row]),'Already reserved')
        self.requests.post.assert_not_called()

    def test_delivery_test_does_not_consume_real_day_reservation(self):
        self.m.dispatch(self.settings,self.candidate,self.day,[self.row],test=True)
        test_key=self.log.insert.call_args.kwargs['set_name']
        self.assertNotEqual(test_key,self.m.identity(self.f.local.site,self.candidate['user'],self.day))
        self.assertIn('TEST ONLY',self.requests.post.call_args.kwargs['json']['message'])

    def test_concurrent_reservation_never_posts(self):
        self.log.insert.side_effect=self.f.DuplicateEntryError
        self.assertEqual(self.m.dispatch(self.settings,self.candidate,self.day,[self.row]),'Already reserved')
        self.requests.post.assert_not_called()

    def test_reservation_commits_before_private_send(self):
        def send(*args,**kw):
            self.f.db.commit.assert_called_once()
            self.assertEqual(kw['json']['allocated_to'],'employee@example.com')
            self.assertFalse(kw['allow_redirects'])
            self.assertIn('idempotency_key',kw['json'])
            return R(status_code=202)
        self.requests.post.side_effect=send
        self.assertEqual(self.m.dispatch(self.settings,self.candidate,self.day,[self.row]),'Accepted')

    def test_timeout_uncertain_and_no_retry(self):
        self.requests.post.side_effect=self.requests.RequestException
        self.assertEqual(self.m.dispatch(self.settings,self.candidate,self.day,[self.row]),'Uncertain')
        self.requests.post.assert_called_once()
        self.f.db.exists.return_value=True
        self.m.dispatch(self.settings,self.candidate,self.day,[self.row])
        self.requests.post.assert_called_once()

    def test_redirect_not_accepted(self):
        self.requests.post.return_value=R(status_code=302)
        self.assertEqual(self.m.dispatch(self.settings,self.candidate,self.day,[self.row]),'Failed')

    def test_ids_separate_sites_users_and_dates(self):
        self.assertEqual(len({self.m.identity(s,u,d) for s in ('OM','AE') for u in ('one','two') for d in ('15','16')}),8)

    def test_invalid_endpoint_rejected(self):
        for url in ('http://test.logic.azure.com/workflows/a','https://evil.example/workflows/a','https://logic.azure.com.evil.example/workflows/a'):
            with self.assertRaises(ValueError):self.m.validate_endpoint(url)

    def test_sync_reuses_document_and_task_rows(self):
        row=R(name='ROW1',task='T1')
        doc=R(name='TTS1',tech_task_scheduler_list=[row],flags=R())
        doc.set=lambda name,value:doc.update({name:value})
        doc.save=Mock();doc.append=Mock()
        self.f.db.get_value.return_value='TTS1';self.f.get_doc.return_value=doc
        data={k:'' for k in ('date','category','category_doctype','category_name','project','task','resource','status','activity_details')}
        data.update(task='T1',project='P1')
        for _ in range(2):self.assertEqual(self.m.sync_schedule('P1','one',self.day,[data]),'TTS1')
        self.assertEqual(len(doc.tech_task_scheduler_list),1);self.assertEqual(doc.tech_task_scheduler_list[0].name,'ROW1')
        doc.append.assert_not_called()

    def test_evening_only_enabled_and_start_date(self):
        settings=R(enabled=1,private_delivery_verified=1,start_date='2026-11-16')
        for stamp,expected in [('2026-11-15T18:00:00',False),('2026-11-16T17:59:59',False),
                ('2026-11-16T18:00:00',True),('2026-11-16T19:00:00',False)]:
            self.assertEqual(self.m.evening_due(datetime.fromisoformat(stamp),settings),expected)
        settings.private_delivery_verified=0
        self.assertFalse(self.m.evening_due(datetime(2026,11,16,18),settings))

    def test_existing_manual_schedule_not_duplicated(self):
        self.f.get_all.return_value=[R(task='T1',parent='MANUAL1')]
        self.f.db.get_value.side_effect=[None,R(docstatus=1,custom_bs_auto_key=None)]
        self.assertIsNone(self.m.sync_schedule('P1','one',self.day,[dict(task='T1')]))
        self.f.get_doc.assert_not_called()

if __name__=='__main__':unittest.main()
