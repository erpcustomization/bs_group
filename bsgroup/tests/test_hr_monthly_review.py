import importlib.util
import sys
import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo


class MonthlyHRReviewTests(unittest.TestCase):
    def setUp(self):
        self.f=types.ModuleType('frappe');self.f.whitelist=lambda **kw:lambda fn:fn
        self.f.PermissionError=PermissionError
        self.f.throw=lambda message,*args:(_ for _ in ()).throw(PermissionError(message))
        self.f.has_permission=Mock(return_value=True);self.f.get_list=Mock(return_value=[])
        u=types.ModuleType('frappe.utils');u.getdate=lambda x:date.fromisoformat(str(x)[:10]);u.get_datetime=datetime.fromisoformat;u.flt=lambda x:float(x or 0)
        h=types.ModuleType('bsgroup.hr_management');self.guard=h._guard=Mock()
        c=types.ModuleType('bsgroup.hr_attendance');c.month_bounds=lambda m:(date.fromisoformat(m+'-01'),date(2026,12,1));c._rows=Mock(return_value=[])
        self.patch=patch.dict(sys.modules,{'frappe':self.f,'frappe.utils':u,'bsgroup.hr_management':h,'bsgroup.hr_attendance':c});self.patch.start()
        spec=importlib.util.spec_from_file_location('monthly_review_test',Path(__file__).resolve().parents[1]/'hr_monthly_review.py');self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.day=date(2026,11,6);self.now=self.stamp('2026-11-08 12:00:00');self.start=self.stamp('2026-11-06 09:00:00');self.end=self.stamp('2026-11-06 18:00:00')

    def tearDown(self):self.patch.stop()

    def stamp(self,s):return datetime.fromisoformat(s).replace(tzinfo=ZoneInfo('Asia/Dubai'))

    def logs(self,*items):return [dict(stamp=self.stamp(t),time=t,log_type=k,name=str(i)) for i,(t,k) in enumerate(items)]

    def metrics(self,logs,**kw):
        pairs,issues=self.m.paired_intervals(logs,self.now)
        return self.m.day_metrics(self.day,self.now,pairs,logs,issues,(self.start,self.end),**kw)

    def test_full_nine_hour_window_and_after_hours_are_separate(self):
        d=self.metrics(self.logs(('2026-11-06 09:15:00','IN'),('2026-11-06 20:00:00','OUT')))
        self.assertEqual((d['scheduled_minutes'],d['office_minutes'],d['late_minutes'],d['after_minutes']),(540,525,15,120))
        self.assertEqual((d['late_day'],d['after_day']),(1,1))

    def test_lunch_is_not_automatically_deducted_but_actual_out_gap_is(self):
        d=self.metrics(self.logs(('2026-11-06 09:00:00','IN'),('2026-11-06 12:00:00','OUT'),('2026-11-06 13:00:00','IN'),('2026-11-06 18:00:00','OUT')))
        self.assertEqual(d['office_minutes'],480);self.assertEqual(d['scheduled_minutes'],540)

    def test_missing_checkout_never_invents_hours_or_late_days(self):
        d=self.metrics(self.logs(('2026-11-06 09:20:00','IN')))
        self.assertEqual((d['office_minutes'],d['late_day'],d['after_minutes']),(0,0,0))
        self.assertIn('Incomplete or ambiguous punches',d['flags'])

    def test_duplicate_in_is_flagged_and_not_counted(self):
        d=self.metrics(self.logs(('2026-11-06 09:00:00','IN'),('2026-11-06 10:00:00','IN'),('2026-11-06 19:00:00','OUT')))
        self.assertEqual((d['office_minutes'],d['after_minutes']),(0,0));self.assertTrue(d['flags'])

    def test_holiday_leave_and_on_duty_do_not_count_as_late_or_missing(self):
        logs=self.logs(('2026-11-06 10:00:00','IN'),('2026-11-06 19:00:00','OUT'))
        for kw in ({'holiday':True},{'leave':1},{'leave':.5},{'duty':1}):
            d=self.metrics(logs,**kw);self.assertEqual(d['late_day'],0);self.assertEqual(d['missing_checkin'],0)
        self.assertEqual(self.metrics([],leave=.5)['expected_due_minutes'],270)

    def test_missing_punch_is_not_an_hr_absence(self):
        d=self.metrics([]);self.assertEqual(d['missing_checkin'],1);self.assertEqual(d['hr_absent'],0)

    def test_draft_absence_does_not_count_and_conflicting_submitted_absence_is_flagged(self):
        d=self.metrics([],attendance=[dict(status='Absent',docstatus=0)])
        self.assertEqual(d['hr_absent'],0)
        d=self.metrics(self.logs(('2026-11-06 09:00:00','IN'),('2026-11-06 18:00:00','OUT')),attendance=[dict(status='Absent',docstatus=1)])
        self.assertEqual(d['hr_absent'],1);self.assertIn('HR absence conflicts with other records',d['flags'])

    def test_day_not_finished_does_not_count_missing_checkin(self):
        d=self.m.day_metrics(self.day,self.start+timedelta(minutes=10),[],[],set(),(self.start,self.end))
        self.assertEqual(d['missing_checkin'],0);self.assertEqual(d['expected_due_minutes'],10)

    def test_overnight_pair_after_six_is_clipped_at_midnight(self):
        d=self.metrics(self.logs(('2026-11-06 17:00:00','IN'),('2026-11-07 01:00:00','OUT')))
        self.assertEqual(d['after_minutes'],360)

    def test_missing_schedule_is_unknown_not_zero_expected(self):
        d=self.m.day_metrics(self.day,self.now,[],[],set())
        self.assertIsNone(d['scheduled_minutes']);self.assertIsNone(d['late_day']);self.assertIsNone(d['missing_checkin'])

    def test_access_guard_before_queries(self):
        self.guard.side_effect=PermissionError()
        with self.assertRaises(PermissionError):self.m.report('2026-11')
        self.f.get_list.assert_not_called()

    def test_empty_scope_keeps_automatic_sending_disabled(self):
        r=self.m.report('2026-11');self.assertEqual(r['employees'],[]);self.assertFalse(r['automation_enabled'])

    def test_holiday_assignment_changes_are_date_effective(self):
        rows=[dict(assigned_to='UAE',from_date='2026-01-01',holiday_list='company'),
              dict(assigned_to='staff',from_date='2026-11-01',holiday_list='old'),
              dict(assigned_to='staff',from_date='2026-11-15',holiday_list='new')]
        self.assertEqual(self.m.effective_holiday(rows,'staff','UAE',date(2026,11,6)),'old')
        self.assertEqual(self.m.effective_holiday(rows,'staff','UAE',date(2026,11,16)),'new')
        self.assertEqual(self.m.effective_holiday(rows,'staff','UAE',date(2026,10,1)),'company')


if __name__=='__main__':unittest.main()
