import importlib.util
import sys
import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch


class Doc(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.db = Mock()
        self.f.db.exists.return_value = False
        self.f.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})
        self.f.throw = lambda text: (_ for _ in ()).throw(ValueError(text))
        self.f.log_error = Mock()
        self.f.conf = Doc(host_name='https://erp.bitssecureit.com')
        self.f.local = Doc(site='local-test')
        self.u = types.ModuleType('frappe.utils')
        self.u.getdate = lambda v: v if isinstance(v, date) else date.fromisoformat(v)
        self.u.get_datetime = lambda v: v if isinstance(v, datetime) else datetime.fromisoformat(v)
        self.u.get_system_timezone = lambda: 'Asia/Dubai'
        self.u.validate_email_address = lambda v: v if '@' in v else None
        self.f.utils = self.u
        self.mail = types.ModuleType('bsgroup.hr_email')
        self.profile = dict(region='UAE', email='hr-notifications-ae@bitssecureit.com', sender_name='HR UAE')
        self.mail.site_profile = Mock(return_value=self.profile)
        self.account = Doc(name='HR Notifications', email_id=self.profile['email'])
        self.mail.configured_account = Mock(return_value=self.account)
        self.modules = patch.dict(sys.modules, {'frappe': self.f, 'frappe.utils': self.u,
                                                'bsgroup.hr_email': self.mail})
        self.modules.start()
        spec = importlib.util.spec_from_file_location('weekly_test_module',
            Path(__file__).resolve().parents[1] / 'weekly_attendance_email.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.now = datetime(2026, 11, 13, 9, 5, tzinfo=self.m.TZ)
        self.start = self.now.replace(day=12, hour=9, minute=0)
        self.end = self.start + timedelta(hours=9)
        self.employee = Doc(name='EMP-TEST', employee_name='Test & Employee', user_id='person@example.test')
        self.module = Mock()
        self.module.plan.return_value = dict(start=self.start, end=self.end, reason='')
        self.f.get_all = Mock(return_value=[])

    def tearDown(self):
        self.modules.stop()

    def classify(self, punches, **kw):
        return self.m.day_result(self.start, self.end, punches, **kw)

    def test_boundary_and_deduplication_of_two_issues(self):
        row = self.classify([(self.start, 'IN'), (self.end, 'OUT')])
        self.assertFalse(row['affected'])
        row = self.classify([(self.start + timedelta(seconds=1), 'IN')])
        self.assertTrue(row['late'])
        self.assertTrue(row['missing'])
        self.assertEqual(int(row['affected']), 1)

    def test_regional_identity_without_newer_hr_helper(self):
        self.assertEqual(self.m.site_profile()['region'], 'UAE')
        self.f.conf.host_name = 'https://erp-om.bitssecureit.com'
        self.assertEqual(self.m.site_profile()['region'], 'Oman')
        self.f.conf.host_name = 'https://unrelated.example.test'
        self.assertIsNone(self.m.site_profile())

    def test_midday_out_then_in_requires_final_checkout(self):
        row = self.classify([(self.start, 'IN'), (self.start+timedelta(hours=3), 'OUT'),
                             (self.start+timedelta(hours=4), 'IN')])
        self.assertTrue(row['missing'])
        self.assertFalse(row['late'])

    def test_early_checkout_is_not_a_weekly_trigger(self):
        self.assertFalse(self.classify([(self.start, 'IN'), (self.end-timedelta(hours=1), 'OUT')])['affected'])

    def test_missing_all_activity_or_out_only_is_not_called_late(self):
        for punches in ([], [(self.end, 'OUT')], [(self.start, '')]):
            self.assertFalse(self.classify(punches)['affected'])

    def test_approved_correction_supersedes_late_missing_punch(self):
        row = self.classify([(self.start+timedelta(hours=1), 'IN')],
                            corrected_in=self.start, corrected_out=self.end)
        self.assertFalse(row['affected'])

    def test_overnight_shift(self):
        start = self.start.replace(hour=22)
        end = start + timedelta(hours=8)
        row = self.m.day_result(start, end, [(start, 'IN'), (end, 'OUT')])
        self.assertFalse(row['affected'])
        self.assertEqual(row['out'].date(), date(2026, 11, 13))

    def test_friday_period_and_exact_scheduled_time(self):
        self.assertEqual(self.m.reporting_period(self.now.date()), (date(2026,11,6), date(2026,11,12)))
        self.assertTrue(self.m.is_due(self.now))
        for now in (self.now-timedelta(minutes=1), self.now.replace(minute=2),
                    self.now-timedelta(days=1), self.now.replace(hour=12)):
            self.assertFalse(self.m.is_due(now))
        self.assertEqual(self.m.next_run(self.now.replace(minute=2)), self.now.date())
        self.assertEqual(self.m.next_run(self.now-timedelta(minutes=1)), self.now.date())
        self.assertEqual(self.m.next_run(self.now), date(2026,11,20))

    def test_threshold_three_and_distinct_days(self):
        self.m.region_module = Mock(return_value=self.module)
        self.m.recipients = Mock(return_value=(['manager@example.test', self.m.HR_CC], ''))
        for affected in (2,3,4):
            rows = [dict(affected=i<affected, late=i<affected, missing=i<affected) for i in range(7)]
            self.m.read_day = Mock(side_effect=rows)
            summary = self.m.report(self.employee, self.now.date(), self.now)
            self.assertEqual(summary['affected'], affected)
            self.assertEqual(summary['eligible'], affected>=3)

    def test_holiday_or_approved_leave_skips_evidence(self):
        for reason in ('Holiday / weekly day off', 'Approved leave', 'No assigned or default shift'):
            self.module.plan.return_value['reason'] = reason
            row = self.m.read_day(self.employee, self.start.date(), self.now, self.module)
            self.assertTrue(row['excluded'])
        self.f.get_all.assert_not_called()

    def test_incomplete_overnight_shift_is_excluded(self):
        self.module.plan.return_value['end'] = self.now+timedelta(hours=1)
        self.assertTrue(self.m.read_day(self.employee, self.start.date(), self.now, self.module)['excluded'])

    def test_approved_correction_without_times_is_not_flagged(self):
        self.f.get_all.side_effect = [[], [Doc(attendance_request='CORRECTED', status='Present')]]
        row = self.m.read_day(self.employee, self.start.date(), self.now, self.module)
        self.assertTrue(row['excluded'])
        self.assertFalse(row['affected'])

    def test_manager_and_hr_cc_exactly(self):
        def lookup(dt, name, fields, **kw):
            if dt == 'User': return 1
            if fields == 'reports_to': return 'EMP-MANAGER'
            return Doc(user_id='manager@example.test', status='Active')
        self.f.db.get_value.side_effect = lookup
        cc, hold = self.m.recipients(self.employee)
        self.assertEqual(cc, ['manager@example.test', self.m.HR_CC])
        self.assertFalse(hold)
        self.f.db.get_value.side_effect = lambda dt, *a, **k: 1 if dt=='User' else None
        self.assertIn('not assigned', self.m.recipients(self.employee)[1])

    def test_mithun_weekly_cc_uses_manikandan_and_muskan_without_changing_manager(self):
        self.employee.user_id = 'mithun@bitssecureit.com'
        self.f.db.get_value.return_value = 1
        self.f.db.exists.return_value = True
        cc, hold = self.m.recipients(self.employee)
        self.assertEqual(cc, ['manikandan@bitssecureit.com', self.m.HR_CC])
        self.assertFalse(hold)
        self.f.db.exists.assert_called_once_with('Employee',
            {'user_id': 'manikandan@bitssecureit.com', 'status': 'Active'})
        self.f.db.set_value.assert_not_called()
        self.assertTrue(all(call.args[0] == 'User' for call in self.f.db.get_value.call_args_list))

    def test_mithun_override_is_uae_only(self):
        self.employee.user_id = 'mithun@bitssecureit.com'
        self.f.conf.host_name = 'https://erp-om.bitssecureit.com'
        def lookup(dt, name, fields, **kw):
            if dt == 'User': return 1
            if fields == 'reports_to': return 'EMP-RECORDED-MANAGER'
            return Doc(user_id='recorded@example.test', status='Active')
        self.f.db.get_value.side_effect = lookup
        self.assertEqual(self.m.recipients(self.employee),
            ([self.m.HR_CC, 'recorded@example.test'], ''))

    def test_unavailable_override_holds_email_without_falling_back_to_other_manager(self):
        self.employee.user_id = 'mithun@bitssecureit.com'
        for enabled, active in ((False, True), (True, False)):
            with self.subTest(enabled=enabled, active=active):
                self.f.db.get_value.side_effect = lambda dt, name, *a, **k: (
                    enabled if name == 'manikandan@bitssecureit.com' else 1)
                self.f.db.exists.return_value = active
                cc, hold = self.m.recipients(self.employee)
                self.assertEqual(cc, [])
                self.assertIn('Designated weekly CC recipient', hold)

    def sample(self):
        row = self.classify([(self.start+timedelta(minutes=15), 'IN')])
        row.update(day=self.start.date(), excluded=False)
        return dict(employee=self.employee.name, name=self.employee.employee_name,
            to=self.employee.user_id, cc=['manager@example.test', self.m.HR_CC], hold='',
            qualifies=True, eligible=True, start=date(2026,11,6), end=date(2026,11,12),
            rows=[row], affected=3, late=3, missing=3)

    def setup_queue(self):
        self.m.report = Mock(return_value=self.sample())
        self.marker = Mock()
        self.f.get_doc = Mock(return_value=self.marker)
        self.f.sendmail = Mock(return_value=Doc(email_account=self.account.name, sender=self.account.email_id))

    def test_individual_email_dedicated_sender_and_cc(self):
        self.setup_queue()
        self.assertTrue(self.m.queue_one(self.employee, self.now.date(), self.now, self.account))
        kwargs = self.f.sendmail.call_args.kwargs
        self.assertEqual(kwargs['recipients'], [self.employee.user_id])
        self.assertEqual(kwargs['cc'], ['manager@example.test', self.m.HR_CC])
        self.assertEqual(kwargs['expose_recipients'], 'header')
        self.assertFalse(kwargs['now'])
        self.assertIn(self.account.email_id, kwargs['sender'])

    def test_mohan_and_raj_are_excluded_before_any_email_is_built(self):
        for user in ('mohan@bitssecureit.com', 'raj@bitssecureit.com'):
            with self.subTest(user=user):
                self.setup_queue()
                self.employee.user_id = user
                self.assertFalse(self.m.queue_one(self.employee, self.now.date(), self.now, self.account))
                self.m.report.assert_not_called()
                self.f.sendmail.assert_not_called()

    def test_raj_preview_is_excluded_without_attendance_or_recipient_lookup(self):
        self.employee.user_id = 'raj@bitssecureit.com'
        self.m.region_module = Mock(return_value=self.module)
        self.m.read_day = Mock()
        self.m.recipients = Mock()
        result = self.m.report(self.employee, self.now.date(), self.now)
        self.assertTrue(result['excluded'])
        self.assertFalse(result['eligible'])
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['cc'], [])
        self.m.read_day.assert_not_called()
        self.m.recipients.assert_not_called()

    def test_weekly_duplicate_concurrency_and_failure_rollback(self):
        self.setup_queue()
        self.f.db.exists.return_value = True
        self.assertFalse(self.m.queue_one(self.employee, self.now.date(), self.now, self.account))
        self.f.sendmail.assert_not_called()
        self.f.db.exists.return_value = False
        self.marker.db_insert.side_effect = self.f.DuplicateEntryError()
        self.assertFalse(self.m.queue_one(self.employee, self.now.date(), self.now, self.account))
        self.f.sendmail.assert_not_called()
        self.marker.db_insert.side_effect = None
        self.f.sendmail.side_effect = RuntimeError('queue failed')
        with self.assertRaises(RuntimeError):
            self.m.queue_one(self.employee, self.now.date(), self.now, self.account)
        self.assertEqual(self.f.db.rollback.call_count, 2)

    def test_missing_manager_or_wrong_sender_cannot_send(self):
        self.setup_queue()
        self.m.report.return_value['hold'] = 'Reporting manager is not assigned'
        self.assertFalse(self.m.queue_one(self.employee, self.now.date(), self.now, self.account))
        self.f.sendmail.assert_not_called()
        self.m.report.return_value['hold'] = ''
        self.f.sendmail.return_value = Doc(email_account='Help Desk', sender='helpdesk@bitssecureit.com')
        with self.assertRaises(ValueError):
            self.m.queue_one(self.employee, self.now.date(), self.now, self.account)

    def test_strong_message_escaped_name_and_assigned_shift(self):
        body = self.m.email_body(self.sample(), self.profile)
        self.assertIn('Test &amp; Employee', body)
        self.assertIn('requires immediate improvement', body)
        self.assertIn('9:00 AM', body)
        self.assertIn('6:00 PM', body)
        self.assertIn('Staying beyond your assigned working hours to compensate for late arrival is not an acceptable practice.', body)
        self.assertIn('<li>Report to work on time as per your assigned shift.</li>', body)
        self.assertIn('<li>Maintain productivity throughout your working hours.</li>', body)
        self.assertIn('<li>Record both check-in and check-out accurately.</li>', body)
        self.assertIn('<li>Follow your assigned start and end time.</li>', body)
        self.assertIn('<b>Daily Attendance Details:</b>', body)
        self.assertIn('<b>Weekly Summary:</b>', body)
        self.assertIn('<li>Late check-ins: 3 days</li>', body)
        self.assertIn('<li>Missing check-outs: 3 days</li>', body)
        self.assertIn('<li>Total affected days: 3</li>', body)
        self.assertIn('Immediate and consistent improvement is expected. Any repeated violations will be addressed accordingly.', body)
        self.assertIn('<b>Human Resources – UAE</b><br><b>BITS Secure IT</b>', body)
        self.assertNotIn('salary', body)
        self.assertNotIn('disciplinary', body)

    def test_hook_idempotency_and_other_mail_unchanged(self):
        hooks = dict(scheduler_events={'cron': {'* * * * *': ['existing.daily']}})
        self.m.configure_hooks(hooks)
        self.m.configure_hooks(hooks)
        self.assertEqual(hooks['scheduler_events']['cron'][self.m.CRON], [self.m.METHOD])
        self.assertEqual(hooks['scheduler_events']['cron']['* * * * *'], ['existing.daily'])


if __name__ == '__main__':
    unittest.main()
