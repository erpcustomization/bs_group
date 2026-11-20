import sys
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

frappe = types.ModuleType('frappe')
frappe.whitelist = lambda **kw: lambda fn: fn
frappe.db = Mock()
frappe.session = types.SimpleNamespace(user='Administrator')
frappe.local = types.SimpleNamespace(site='uae-test')
frappe.set_user = lambda user: setattr(frappe.session, 'user', user)
frappe.get_doc = Mock()
frappe.get_all = Mock()
frappe.sendmail = Mock(return_value='QUEUE')
frappe.DuplicateEntryError = type('DuplicateEntryError', (Exception,), {})
utils = types.ModuleType('frappe.utils')
utils.get_datetime = lambda value: value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
sys.modules.update({'frappe':frappe, 'frappe.utils':utils,
    'bsgroup.hr_email':types.SimpleNamespace(site_profile=lambda: {'region':'UAE'}),
    'bsgroup.approval_requests':types.SimpleNamespace(pending=Mock(), require_mohan=Mock()),
    'bsgroup.dcs.manager_approval':types.SimpleNamespace(FIXED_APPROVER='mohan@bitssecureit.com')})
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('approval_reminders',Path(__file__).parents[1]/'bsgroup/approval_reminders.py')
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

class Tests(unittest.TestCase):
    def setUp(self):
        frappe.db.reset_mock(); frappe.db.exists.return_value=False
        frappe.get_doc.reset_mock(); frappe.get_doc.side_effect=None
        frappe.sendmail.reset_mock(); frappe.sendmail.return_value='QUEUE'
        self.now=datetime(2026,11,21,9,tzinfo=r.TZ)
        self.row=dict(kind='sales',name='D1',subject='A & B',requested_by='Paul',state='Pending Manager',since='2026-11-18 08:00:00',age_basis='Current revision',days=3)

    def test_strict_48_hour_boundary(self):
        self.assertFalse(r.overdue('2026-11-19 09:00:00',self.now))
        self.assertTrue(r.overdue('2026-11-19 08:59:59',self.now))
        self.assertFalse(r.overdue('2026-11-22 08:00:00',self.now))

    def test_daily_window_includes_weekends(self):
        self.assertTrue(r.due(self.now))
        self.assertFalse(r.due(self.now.replace(hour=8,minute=59)))
        self.assertFalse(r.due(self.now.replace(hour=10)))

    def test_current_revision_age(self):
        doc=Mock(name='D1'); doc.name='D1';doc.custom_revision_reference='R2'
        frappe.get_doc.return_value=doc
        frappe.db.get_value.return_value=types.SimpleNamespace(dcs='D1',changed_on='2026-11-20 16:00:00',creation='2026-11-20 16:00:00')
        since,basis=r.pending_since(self.row)
        self.assertEqual(basis,'Current revision')
        self.assertFalse(r.overdue(since,self.now))

    def test_workflow_resubmission_age(self):
        doc=types.SimpleNamespace(doctype='Material Request',name='MR1',modified='2026-11-21 08:00:00')
        frappe.get_doc.return_value=doc
        frappe.get_all.return_value=[types.SimpleNamespace(creation='2026-11-20 12:00:00',data='{"changed":[["workflow_state","Rejected","Pending Approval"]]}')]
        self.assertEqual(r.pending_since(dict(kind='purchase',name='MR1',state='Pending Approval'))[0],'2026-11-20 12:00:00')

    def test_permission_context_restored_on_failure(self):
        with patch.object(r,'pending',side_effect=ValueError('fail')):
            with self.assertRaises(ValueError):r.collect(self.now)
        self.assertEqual(frappe.session.user,'Administrator')

    def test_preview_preserves_mohan_session(self):
        frappe.session.user=r.FIXED_APPROVER
        with patch.object(r,'pending',return_value={'requests':[]}),patch.object(frappe,'set_user') as switch:
            self.assertEqual(r.collect(self.now),[])
            switch.assert_not_called()
        frappe.session.user='Administrator'

    def test_empty_digest_no_queue(self):
        with patch.object(r,'datetime') as clock,patch.object(r,'collect',return_value=[]):
            clock.now.return_value=self.now
            self.assertEqual(r.send_reminder(),0)
        frappe.sendmail.assert_not_called()

    def test_one_queue_then_retry_skipped(self):
        with patch.object(r,'datetime') as clock,patch.object(r,'collect',return_value=[self.row]):
            clock.now.return_value=self.now
            self.assertEqual(r.send_reminder(),1)
            frappe.db.exists.return_value=True
            self.assertEqual(r.send_reminder(),0)
        frappe.sendmail.assert_called_once()
        self.assertEqual(frappe.sendmail.call_args.kwargs['recipients'],['mohan@bitssecureit.com'])

    def test_concurrent_marker_collision(self):
        frappe.get_doc.return_value.db_insert.side_effect=frappe.DuplicateEntryError()
        with patch.object(r,'datetime') as clock,patch.object(r,'collect',return_value=[self.row]):
            clock.now.return_value=self.now
            self.assertEqual(r.send_reminder(),0)
        frappe.sendmail.assert_not_called()
        frappe.get_doc.return_value.db_insert.side_effect=None

    def test_queue_failure_rolls_back_marker(self):
        frappe.sendmail.side_effect=RuntimeError('smtp setup')
        with patch.object(r,'datetime') as clock,patch.object(r,'collect',return_value=[self.row]):
            clock.now.return_value=self.now
            with self.assertRaises(RuntimeError):r.send_reminder()
        frappe.db.rollback.assert_called_once_with(save_point='approval_digest')
        frappe.sendmail.side_effect=None

    def test_html_escaped_and_sites_separate(self):
        subject,body=r.compose([self.row],self.now)
        self.assertIn('A &amp; B',body)
        self.assertIn('UAE',subject)
        first=r.marker(self.now.date());frappe.local.site='oman-test'
        self.assertNotEqual(first,r.marker(self.now.date()))
        frappe.local.site='uae-test'

if __name__=='__main__':unittest.main()
