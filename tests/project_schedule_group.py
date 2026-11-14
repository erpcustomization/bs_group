import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.f=types.ModuleType('frappe')
        self.f.whitelist=lambda **kw:lambda fn:fn
        self.f.local=types.SimpleNamespace(site='oman')
        self.f.db=types.SimpleNamespace(exists=Mock(return_value=False),commit=Mock(),rollback=Mock(),set_value=Mock())
        self.f.DuplicateEntryError=type('DuplicateEntryError',(Exception,),{})
        self.log=Mock(); self.f.get_doc=Mock(return_value=self.log)
        self.hr=types.ModuleType('bsgroup.hr_email');self.hr.site_profile=Mock(return_value={'region':'Oman'})
        self.scheduler=types.ModuleType('bsgroup.project_schedule')
        self.scheduler.DELIVERY='Delivery';self.scheduler.identity=lambda site,user,day:f'{site}:{user}:{day}'
        self.scheduler.validate_endpoint=Mock()
        self.requests=types.ModuleType('requests');self.requests.post=Mock(return_value=types.SimpleNamespace(status_code=202))
        self.requests.RequestException=type('RequestException',(Exception,),{})
        self.p=patch.dict(sys.modules,{'frappe':self.f,'bsgroup.hr_email':self.hr,'bsgroup.project_schedule':self.scheduler,'requests':self.requests});self.p.start()
        spec=importlib.util.spec_from_file_location('group',Path(__file__).resolve().parents[1]/'bsgroup/project_schedule_group.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.settings=Mock();self.settings.get.return_value=1;self.settings.get_password.return_value='test-endpoint'
        self.day=date(2026,11,15)
        self.row=dict(task='T1',task_title='<Activity>',project_title='Dema',due_date='2026-11-14',status='Overdue')
        self.people=[dict(employee_name='Amar',reason='',rows=[self.row]),dict(employee_name='Nowfal',reason='',rows=[self.row])]

    def tearDown(self):self.p.stop()

    def test_combines_people_and_keeps_shared_task_under_each_person(self):
        body,count=self.m.compose(self.day,self.people)
        self.assertEqual(count,2);self.assertIn('Amar',body);self.assertIn('Nowfal',body)
        self.assertIn('&lt;Activity&gt;',body);self.assertIn('15 November 2026',body)
        self.assertIn('Overdue',body)

    def test_holidays_exclusions_and_same_person_duplicates(self):
        self.people[0]['rows'].append(self.row)
        self.people[1]['reason']='Holiday'
        body,count=self.m.compose(self.day,self.people)
        self.assertEqual(count,1);self.assertNotIn('Nowfal',body)

    def test_repeated_and_concurrent_reservations_never_post(self):
        self.f.db.exists.return_value=True
        self.assertEqual(self.m.dispatch(self.settings,self.day,self.people),'Already reserved')
        self.f.db.exists.return_value=False;self.log.insert.side_effect=self.f.DuplicateEntryError
        self.assertEqual(self.m.dispatch(self.settings,self.day,self.people),'Already reserved')
        self.requests.post.assert_not_called()

    def test_commit_before_post_and_group_identity_separate(self):
        def post(*args,**kw):
            self.f.db.commit.assert_called_once()
            self.assertEqual(kw['json']['allocated_to'],'Projects Team Oman')
            self.assertTrue(kw['json']['idempotency_key'].startswith('GROUP:oman:'))
            self.assertFalse(kw['allow_redirects'])
            return types.SimpleNamespace(status_code=202)
        self.requests.post.side_effect=post
        self.assertEqual(self.m.dispatch(self.settings,self.day,self.people),'Accepted')
        self.assertEqual(self.f.get_doc.call_args.args[0]['task_count'],2)
        self.assertNotIn('recipient',self.f.get_doc.call_args.args[0])

    def test_unknown_site_disabled_and_empty_do_not_send(self):
        self.hr.site_profile.return_value=None
        self.m.dispatch(self.settings,self.day,self.people)
        self.hr.site_profile.return_value={'region':'Oman'};self.settings.get.return_value=0
        self.m.dispatch(self.settings,self.day,self.people)
        self.settings.get.return_value=1
        self.assertEqual(self.m.dispatch(self.settings,self.day,[]),'No eligible tasks')
        self.requests.post.assert_not_called()

    def test_uae_uses_only_uae_endpoint_and_identity(self):
        self.hr.site_profile.return_value={'region':'UAE'}
        self.f.local.site='uae'
        self.assertEqual(self.m.dispatch(self.settings,self.day,self.people),'Accepted')
        self.settings.get_password.assert_called_once_with('uae_group_webhook')
        payload=self.requests.post.call_args.kwargs['json']
        self.assertEqual(payload['allocated_to'],'Projects Team UAE')
        self.assertTrue(payload['idempotency_key'].startswith('GROUP:uae:'))
        self.assertIn('— UAE',payload['message'])

    def test_holiday_for_everyone_never_reserves_or_posts_on_either_site(self):
        for region in ('Oman','UAE'):
            self.hr.site_profile.return_value={'region':region}
            for person in self.people: person['reason']='Holiday / weekly day off'
            self.assertEqual(self.m.dispatch(self.settings,self.day,self.people),'No eligible tasks')
        self.requests.post.assert_not_called()
        self.log.insert.assert_not_called()

    def test_oman_switch_cannot_enable_uae_group(self):
        self.hr.site_profile.return_value={'region':'UAE'}
        self.settings.get.side_effect=lambda key: key.startswith('oman_')
        self.assertEqual(self.m.dispatch(self.settings,self.day,self.people),'Group delivery disabled')
        self.requests.post.assert_not_called()

    def test_uncertain_not_blindly_retried(self):
        self.requests.post.side_effect=self.requests.RequestException
        self.assertEqual(self.m.dispatch(self.settings,self.day,self.people),'Uncertain')
        self.f.db.exists.return_value=True
        self.assertEqual(self.m.dispatch(self.settings,self.day,self.people),'Already reserved')
        self.requests.post.assert_called_once()


if __name__=='__main__':unittest.main()
