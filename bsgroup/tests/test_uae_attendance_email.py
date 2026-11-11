import importlib.util
import sys
import types
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import Mock, patch


class Doc(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class UAEAttendanceEmailTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.db = Mock()
        self.f.db.exists.return_value = False
        self.f.db.count.return_value = 1
        self.f.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})
        self.f.throw = lambda text: (_ for _ in ()).throw(ValueError(text))
        self.f.publish_realtime = Mock()
        self.utils = types.ModuleType('frappe.utils')
        self.utils.getdate = lambda x: x if isinstance(x, date) else date.fromisoformat(x)
        self.utils.to_timedelta = lambda x: x if isinstance(x, timedelta) else timedelta(
            hours=int(str(x).split(':')[0]), minutes=int(str(x).split(':')[1]))
        self.utils.validate_email_address = lambda x: x if '@' in x else None
        self.utils.get_system_timezone = lambda: 'Asia/Dubai'
        self.f.utils = self.utils
        self.mail = types.ModuleType('bsgroup.hr_email')
        self.account = Doc(name='HR Notifications', email_id='hr-notifications-ae@bitssecureit.com')
        self.mail.configured_account = Mock(return_value=self.account)
        self.mail.UAE_EMAIL = self.account.email_id
        self.mail.site_profile = Mock(return_value={'region': 'UAE'})
        self.holidays = types.ModuleType('hrms.utils.holiday_list')
        self.holidays.get_holiday_list_for_employee = Mock(return_value='UAE calendar')
        self.patch = patch.dict(sys.modules, {'frappe': self.f, 'frappe.utils': self.utils,
            'bsgroup.hr_email': self.mail,
            'hrms.utils.holiday_list': self.holidays})
        self.patch.start()
        spec = importlib.util.spec_from_file_location('test_uae_reminders',
            Path(__file__).resolve().parents[1] / 'uae_attendance_email.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.day = date(2026, 11, 12)
        self.now = datetime(2026, 11, 12, 8, 0, tzinfo=self.m.TZ)
        self.employee = Doc(name='TEST-EMP', employee_name='Test & Employee', user_id='employee@example.test',
            company=self.m.COMPANY, default_shift='Muscat', holiday_list=None)
        self.shift = Doc(name='Muscat', start_time='08:00:00', end_time='17:00:00', holiday_list=None)
        self.f.get_cached_doc = Mock(return_value=self.shift)
        self.f.get_all = Mock(return_value=[])
        self.f.db.get_value.side_effect = lambda dt, *args, **kw: (
            Doc(from_date=date(2026, 1, 1), to_date=date(2026, 12, 31)) if dt == 'Holiday List' else 1)

    def tearDown(self):
        self.patch.stop()

    def test_exact_start_zero_grace_and_no_today_sends(self):
        start, end = self.m.shift_window(self.day, self.shift)
        self.assertFalse(self.m.reminder_due(start-timedelta(seconds=1), start, end))
        self.assertTrue(self.m.reminder_due(start, start, end))
        self.assertFalse(self.m.reminder_due(end, start, end))
        old_start, old_end = self.m.shift_window(date(2026, 11, 11), self.shift)
        self.assertFalse(self.m.reminder_due(old_start, old_start, old_end))

    def test_overnight_shift_and_date_key(self):
        shift = Doc(start_time='22:00:00', end_time='06:00:00')
        start, end = self.m.shift_window(self.day, shift)
        self.assertEqual(end.date(), self.day + timedelta(days=1))
        self.assertTrue(self.m.reminder_due(start+timedelta(hours=3), start, end))
        self.assertEqual(self.m.daily_key('A', self.day), self.m.daily_key('A', self.day))
        self.assertNotEqual(self.m.daily_key('A', self.day), self.m.daily_key('A', self.day+timedelta(days=1)))

    def test_uses_assigned_shift_instead_of_default(self):
        self.f.get_all.return_value = [Doc(shift_type='School')]
        self.shift.start_time = '07:00:00'
        p = self.m.plan(self.employee, self.day)
        self.assertEqual(p['shift'], 'School')
        self.assertEqual(p['start'].hour, 7)
        self.assertFalse(p['reason'])

    def test_skip_holiday_leave_and_duty(self):
        for dt, word in [('Holiday', 'Holiday'), ('Leave Application', 'Approved leave'),
                         ('Attendance Request', 'Approved on-duty')]:
            self.f.db.exists.side_effect = lambda doctype, *args, expected=dt, **kw: doctype == expected
            self.assertIn(word, self.m.plan(self.employee, self.day)['reason'])

    def test_missing_or_expired_calendar_holds_for_review(self):
        self.f.db.get_value.side_effect = lambda dt, *args, **kw: (
            Doc(from_date=date(2025, 1, 1), to_date=date(2025, 12, 31)) if dt == 'Holiday List' else 1)
        self.assertIn('does not cover', self.m.plan(self.employee, self.day)['reason'])
        self.holidays.get_holiday_list_for_employee.return_value = None
        self.f.get_cached_value = Mock(return_value=None)
        self.assertIn('unavailable', self.m.plan(self.employee, self.day)['reason'])

    def test_disabled_unlinked_ambiguous_and_conflicting_shift_are_excluded(self):
        self.f.db.get_value.side_effect = lambda *args, **kw: 0
        self.assertIn('No enabled', self.m.plan(self.employee, self.day)['reason'])
        self.f.db.get_value.side_effect = lambda *args, **kw: 1
        self.f.db.count.return_value = 2
        self.assertIn('multiple active', self.m.plan(self.employee, self.day)['reason'])
        self.f.db.count.return_value = 1
        self.f.get_all.return_value = [Doc(shift_type='one'), Doc(shift_type='two')]
        self.assertIn('Overlapping', self.m.plan(self.employee, self.day)['reason'])

    def test_employment_dates(self):
        self.employee.date_of_joining = date(2026, 11, 13)
        self.assertIn('employment', self.m.plan(self.employee, self.day)['reason'])
        self.employee.date_of_joining = None
        self.employee.relieving_date = date(2026, 11, 11)
        self.assertIn('employment', self.m.plan(self.employee, self.day)['reason'])

    def test_pending_leave_message_does_not_ask_for_duplicate_application(self):
        p = self.m.plan(self.employee, self.day)
        text = self.m.message(p, self.now, pending=True)
        self.assertIn('already pending', text)
        self.assertNotIn('please submit', text)
        self.assertIn('Test &amp; Employee', text)
        self.assertIn('08:00', text)

    def setup_queue(self):
        p = self.m.plan(self.employee, self.day)
        self.m.plan = Mock(return_value=p)
        self.m.has_attendance = Mock(return_value=False)
        self.m.pending_leave = Mock(return_value=False)
        self.marker = Mock()
        self.f.get_doc = Mock(return_value=self.marker)
        self.f.sendmail = Mock(return_value=Doc(email_account=self.account.name, sender=self.account.email_id))

    def test_exact_hr_sender_employee_only_delayed_queue(self):
        self.setup_queue()
        self.assertTrue(self.m.queue_one(self.employee, self.day, self.now, self.account))
        args = self.f.sendmail.call_args.kwargs
        self.assertEqual(args['recipients'], [self.employee.user_id])
        self.assertIn(self.account.email_id, args['sender'])
        self.assertTrue(args['delayed'])
        self.assertFalse(args['now'])
        self.assertEqual(args['reference_doctype'], 'Employee')
        self.assertNotIn('cc', args)
        self.assertEqual(self.m.has_attendance.call_count, 2)

    def test_dedup_and_concurrent_daily_reservation(self):
        self.setup_queue()
        self.f.db.exists.return_value = True
        self.assertFalse(self.m.queue_one(self.employee, self.day, self.now, self.account))
        self.f.db.exists.return_value = False
        self.marker.db_insert.side_effect = self.f.DuplicateEntryError()
        self.assertFalse(self.m.queue_one(self.employee, self.day, self.now, self.account))
        self.f.sendmail.assert_not_called()
        self.f.db.rollback.assert_called_once()

    def test_checkin_arriving_before_queue_cancels_reservation(self):
        self.setup_queue()
        self.m.has_attendance.side_effect = [False, True]
        self.assertFalse(self.m.queue_one(self.employee, self.day, self.now, self.account))
        self.f.sendmail.assert_not_called()
        self.f.db.rollback.assert_called_once()

    def test_wrong_sender_or_queue_failure_rolls_back_for_retry(self):
        self.setup_queue()
        self.f.sendmail.return_value = Doc(email_account='Erp Om', sender='erp.om@bitssecureit.com')
        with self.assertRaises(ValueError):
            self.m.queue_one(self.employee, self.day, self.now, self.account)
        self.f.db.rollback.assert_called_once()
        self.f.publish_realtime.assert_not_called()

    def test_non_uae_never_reads_settings_or_sends(self):
        self.mail.site_profile.return_value = {'region': 'Oman'}
        self.assertEqual(self.m.send_reminders(), 0)
        self.f.get_cached_doc.assert_not_called()
        self.mail.configured_account.assert_not_called()

    def test_recorded_activity_and_submitted_attendance_skip_email(self):
        p = self.m.plan(self.employee, self.day)
        for dt in ('Employee Checkin', 'Attendance'):
            self.f.db.exists.side_effect = lambda doctype, *args, expected=dt, **kw: doctype == expected
            self.assertTrue(self.m.has_attendance(self.employee.name, p, self.now))

    def test_uae_company_only_and_missing_shift_excluded(self):
        self.m.employees()
        self.assertEqual(self.f.get_all.call_args.kwargs['filters'],
            {'status': 'Active', 'company': 'Bits Secure IT Infrastructure LLC - AE'})
        self.employee.default_shift = None
        self.assertEqual(self.m.plan(self.employee, self.day)['reason'], 'No assigned or default shift')

    def test_remains_off_before_start_and_when_disabled(self):
        with patch.object(self.m, 'datetime') as clock:
            clock.now.return_value = self.now - timedelta(days=1)
            self.assertEqual(self.m.send_reminders(), 0)
            self.f.get_cached_doc.assert_not_called()
            clock.now.return_value = self.now
            self.f.get_cached_doc.return_value = Doc({self.m.ENABLED: 0})
            self.assertEqual(self.m.send_reminders(), 0)
        self.mail.configured_account.assert_not_called()

    def test_hooks_preserve_existing_jobs_and_register_once(self):
        hooks = {'scheduler_events': {'cron': {'* * * * *': ['existing.job']}}}
        self.m.configure_hooks(hooks)
        self.m.configure_hooks(hooks)
        self.assertEqual(hooks['scheduler_events']['cron']['* * * * *'], ['existing.job', self.m.METHOD])

    def test_same_approved_wording_with_uae_time_and_signature(self):
        body = self.m.message(self.m.plan(self.employee, self.day), self.now)
        self.assertIn('(UAE time)', body)
        self.assertIn('HR UAE', body)
        self.assertNotIn('Oman', body)
        self.assertNotIn('attendance request', body)
        self.assertNotIn('https://', body)
        self.assertNotIn('pay', body)


if __name__ == '__main__':
    unittest.main()
