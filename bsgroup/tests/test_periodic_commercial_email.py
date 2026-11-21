import ast
import calendar
import unittest
from datetime import datetime, date, time, timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock


class PeriodicTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((Path(__file__).parents[1] / 'periodic_commercial_email.py').read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('periods','key','send_reports')]
        self.ns = dict(calendar=calendar, datetime=datetime, date=date, time=time,
            timedelta=timedelta, sha256=sha256)
        exec(compile(ast.Module(body=nodes,type_ignores=[]), 'periodic', 'exec'), self.ns)
        self.anchor = date(2026,11,21)

    def test_first_run_and_fixed_fifteen_day_window(self):
        self.assertEqual(self.ns['periods'](datetime(2026,11,21,17,30),self.anchor),[])
        r=self.ns['periods'](datetime(2026,12,6,17,30),self.anchor)
        self.assertEqual(r,[('15-Day',datetime(2026,11,21,17,30),datetime(2026,12,6,17,30))])
        self.assertEqual(self.ns['periods'](datetime(2026,12,6,18,55),self.anchor),r)

    def test_month_end_and_leap_year(self):
        self.assertEqual(self.ns['periods'](datetime(2026,11,30,17,30),self.anchor)[0],
            ('Month-End',datetime(2026,11,1),datetime(2026,11,30,17,30)))
        self.assertFalse(self.ns['periods'](datetime(2028,2,28,17,30),date(2028,2,28)))
        self.assertEqual(self.ns['periods'](datetime(2028,2,29,17,30),date(2028,2,28))[0][0],'Month-End')

    def test_no_early_or_late_send(self):
        for hour,minute in [(17,29),(19,0),(23,0)]:
            self.assertEqual(self.ns['periods'](datetime(2026,12,6,hour,minute),self.anchor),[])

    def test_coincident_reports_are_separate(self):
        r=self.ns['periods'](datetime(2026,11,30,17,30),date(2026,11,15))
        self.assertEqual(len(r),2)
        self.assertNotEqual(self.ns['key']('u','Sales',r[0][0],r[0][2]),self.ns['key']('u','Sales',r[1][0],r[1][2]))

    def test_retry_does_not_queue_duplicate_and_uses_current_cc(self):
        f=Mock(); markers=set(); f.db.get_single_value.side_effect=lambda dt,field: 1 if field=='enabled' else self.anchor
        f.db.exists.side_effect=lambda dt,key:key in markers
        f.get_doc.side_effect=lambda doc:Mock(db_insert=lambda:markers.add(doc['name']))
        f.sendmail.return_value='QUEUE'
        f.DuplicateEntryError=type('DuplicateEntryError',(Exception,),{})
        now=Mock();now.now.return_value=datetime(2026,12,6,17,30)
        self.ns.update(frappe=f,datetime=now,TZ=None,FLAG='enabled',ANCHOR='anchor',
            site_profile=lambda:True,collect_range=lambda a,b:{},
            people=lambda:[dict(user='rahul@bitssecureit.com',kind='Sales',cc=['mohan@bitssecureit.com'])],
            compose=lambda *a:('Report','Body'))
        # periods uses datetime.combine; retain the real implementation there.
        now.combine.side_effect=datetime.combine
        self.assertEqual(self.ns['send_reports'](),1)
        self.assertEqual(self.ns['send_reports'](),0)
        self.assertEqual(f.sendmail.call_count,1)
        self.assertEqual(f.sendmail.call_args.kwargs['cc'],['mohan@bitssecureit.com'])


if __name__=='__main__':unittest.main()
