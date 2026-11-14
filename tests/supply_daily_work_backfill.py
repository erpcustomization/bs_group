import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Row(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.daily = types.ModuleType('bsgroup.project_daily_work')
        self.daily.enabled = Mock(return_value=True)
        self.daily.install = Mock()
        plan = types.ModuleType('bsgroup.project_plan')
        plan.WORK_SUBJECT = 'Project Plan daily work'
        self.modules = patch.dict(sys.modules, {'frappe': self.f,
            'bsgroup.project_daily_work': self.daily, 'bsgroup.project_plan': plan})
        self.modules.start()
        spec = importlib.util.spec_from_file_location('recovery', Path(__file__).resolve().parents[1] /
            'bsgroup/patches/v0_1/uae_supply_daily_work_20261114.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.project = Row(project_name='Supply Surveillance HDD - QTN-2026-01317', company='AE')
        self.employee = Row(name='EMP-1', employee_name='Manikandan D')
        self.notes = [Row(name='note-' + str(i), reference_name=task, creation='2026-11-14 ' + time,
            comment_email='author@example.com', comment_by='Manikandan D',
            content="<p><strong>Today's work — 2026-11-14</strong></p><p>" + text + '</p>')
            for i, ((task, time), text) in enumerate(self.m.EXPECTED.items())]
        self.rows = []
        self.sheet = Row(name='TS-RECOVERED')
        self.sheet.append = lambda field, value: self.rows.append(Row(value, parent=self.sheet.name, docstatus=0))
        self.sheet.save = Mock()
        self.f.db = Row(exists=Mock(return_value=True), get_value=Mock(return_value='PROJ-2525'))
        self.f.get_all = Mock(side_effect=self.get_all)
        self.f.get_doc = Mock(side_effect=lambda dt, *a, **kw: self.project if dt == 'Project' else self.sheet)
        self.f.new_doc = Mock(return_value=self.sheet)
        self.f.logger = Mock(return_value=Mock())

    def get_all(self, dt, **kwargs):
        if dt == 'Comment': return self.notes
        if dt == 'Employee': return [self.employee]
        if dt == 'Timesheet Detail':
            return [r for r in self.rows if r.custom_bs_work_entry == kwargs['filters']['custom_bs_work_entry']]
        if dt == 'Timesheet': return []
        raise AssertionError(dt)

    def tearDown(self): self.modules.stop()

    def test_preserves_author_date_and_all_seven_source_ids(self):
        self.m.execute()
        self.assertEqual(len(self.rows), 7)
        self.assertEqual(self.sheet.user, 'author@example.com')
        self.assertEqual(self.sheet.owner, self.sheet.user)
        self.assertEqual(self.sheet.employee, 'EMP-1')
        self.assertEqual(self.sheet.custom_date, '2026-11-14')
        self.assertEqual({r.custom_bs_work_entry for r in self.rows}, {n.name for n in self.notes})
        self.assertTrue(all(r.hours == 0 and r.custom_bs_work_date == '2026-11-14' for r in self.rows))
        self.sheet.save.assert_called_once()

    def test_repeat_is_noop(self):
        self.m.execute()
        self.m.execute()
        self.assertEqual(len(self.rows), 7)
        self.sheet.save.assert_called_once()

    def test_changed_source_aborts_before_save(self):
        self.notes[-1].content = '<p>Changed</p>'
        with self.assertRaises(AssertionError): self.m.execute()
        self.sheet.save.assert_not_called()
        self.assertEqual(self.rows, [])

    def test_wrong_employee_aborts(self):
        self.employee.employee_name = 'Other User'
        with self.assertRaises(AssertionError): self.m.execute()
        self.sheet.save.assert_not_called()

    def test_oman_untouched(self):
        self.daily.enabled.return_value = False
        self.m.execute()
        self.f.get_all.assert_not_called()

    def test_duplicate_source_links_abort(self):
        self.m.execute()
        self.rows.append(self.rows[0])
        with self.assertRaises(AssertionError): self.m.execute()
        self.sheet.save.assert_called_once()


if __name__ == '__main__': unittest.main()
