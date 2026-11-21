import ast
import unittest
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo


class DailyProjectEmailTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).parents[1] / 'project_daily_emails.py').read_text(encoding='utf-8'))
        names = {'due', 'key', 'recipients', 'entry_status', 'queue_one', 'run', 'schedule_rows', 'work_rows'}
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        self.ns = dict(datetime=datetime, date=date, time=time, timedelta=timedelta, sha256=sha256,
            TZ=ZoneInfo('Asia/Dubai'), MANI='manikandan@bitssecureit.com',
            SLOTS={'tasks':time(9),'projects':time(10),'reminder':time(17,30),'status':time(18,10),'timesheets':time(19)},
            getdate=lambda value: value if type(value) is date else date.fromisoformat(str(value)[:10]))
        exec(compile(ast.Module(body=nodes,type_ignores=[]), 'project_daily', 'exec'), self.ns)
        self.day=date(2026,11,23)
        self.person=dict(user='worker@example.com', employee=SimpleNamespace(name='EMP-1'))

    def test_exact_slots_and_recovery_windows(self):
        for kind, at in self.ns['SLOTS'].items():
            now=datetime.combine(self.day, at, self.ns['TZ'])
            self.assertEqual(self.ns['due'](now,self.day),[kind])
            self.assertEqual(self.ns['due'](now+timedelta(minutes=25),self.day),[kind])
            self.assertEqual(self.ns['due'](now-timedelta(seconds=1),self.day),[])
            self.assertEqual(self.ns['due'](now+timedelta(minutes=30),self.day),[])
            self.assertEqual(self.ns['due'](now,self.day+timedelta(days=1)),[])

    def test_separate_recipients(self):
        for kind in ('tasks','projects','reminder','status'):
            self.assertEqual(self.ns['recipients']('employee',kind),(['employee'],[]))
        self.assertEqual(self.ns['recipients']('employee','timesheets'),(['manikandan@bitssecureit.com'],['employee']))
        self.assertEqual(self.ns['recipients']('manikandan@bitssecureit.com','timesheets'),(['manikandan@bitssecureit.com'],[]))

    def test_markers_are_per_user_day_and_type(self):
        keys={self.ns['key'](u,k,d) for u in ('a','b') for k in self.ns['SLOTS'] for d in (self.day,self.day+timedelta(days=1))}
        self.assertEqual(len(keys),20)

    def test_blank_work_and_wrong_project_do_not_count(self):
        tasks=[dict(project='P1',task='T1'),dict(project='P2',task='T2'),dict(project='P3',task='T3')]
        work=[dict(project='P1',task='T1',work='Installed'),dict(project='P2',task='T2',work=''),dict(project='P9',task='T3',work='Other')]
        self.assertEqual([r['entry_status'] for r in self.ns['entry_status'](tasks,work)],['Recorded','Not recorded','Not recorded'])

    def fake_queue(self):
        f=Mock(); markers=set()
        f.DuplicateEntryError=type('DuplicateEntryError',(Exception,),{})
        f.db.exists.side_effect=lambda dt,key:key in markers
        def insert(doc):
            def save():
                if doc['name'] in markers: raise f.DuplicateEntryError()
                markers.add(doc['name'])
            return Mock(db_insert=save)
        f.get_doc.side_effect=insert
        f.db.rollback.side_effect=lambda **kw:markers.clear()
        f.sendmail.return_value='QUEUE'
        f.throw.side_effect=RuntimeError
        self.ns.update(frappe=f, calendar_plan=lambda *a:{'reason':''},
            compose=lambda *a:dict(to=['worker@example.com'],cc=[],subject='Status',body='Content'))
        return f,markers

    def test_repeated_run_only_queues_once(self):
        f,markers=self.fake_queue()
        self.assertTrue(self.ns['queue_one'](self.person,self.day,'status'))
        self.assertFalse(self.ns['queue_one'](self.person,self.day,'status'))
        self.assertEqual(f.sendmail.call_count,1)
        f.db.commit.assert_called_once()

    def test_holiday_skips_without_queue_or_marker(self):
        f,markers=self.fake_queue()
        self.ns['calendar_plan']=lambda *a:{'reason':'Holiday / weekly day off'}
        self.assertFalse(self.ns['queue_one'](self.person,self.day,'status'))
        self.assertFalse(markers)
        f.sendmail.assert_not_called()

    def test_failed_send_rolls_back_and_can_retry(self):
        f,markers=self.fake_queue()
        f.sendmail.return_value=None
        with self.assertRaises(RuntimeError):self.ns['queue_one'](self.person,self.day,'status')
        self.assertFalse(markers)
        f.sendmail.return_value='QUEUE'
        self.assertTrue(self.ns['queue_one'](self.person,self.day,'status'))
        self.assertFalse(self.ns['queue_one'](self.person,self.day,'status'))
        self.assertEqual(f.sendmail.call_count,2)

    def test_concurrent_reservation_prevents_second_queue(self):
        f,_=self.fake_queue()
        f.get_doc.return_value=None
        f.get_doc.side_effect=lambda doc:Mock(db_insert=Mock(side_effect=f.DuplicateEntryError()))
        self.assertFalse(self.ns['queue_one'](self.person,self.day,'status'))
        f.sendmail.assert_not_called()

    def test_manager_account_must_be_enabled(self):
        f,_=self.fake_queue()
        f.db.get_value.return_value=False
        with self.assertRaises(RuntimeError):self.ns['queue_one'](self.person,self.day,'timesheets')
        f.sendmail.assert_not_called()


if __name__ == '__main__':unittest.main()
