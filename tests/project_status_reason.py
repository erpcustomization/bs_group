import ast
from html import escape
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import MagicMock

source = ast.parse((Path(__file__).parents[1] / 'bsgroup/project_plan.py').read_text())
function = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'set_task_status')
function.decorator_list = []


class StatusReasonTests(unittest.TestCase):
    def setUp(self):
        self.item = SimpleNamespace(name='T1', status='Open', modified='v1',
            meta=SimpleNamespace(has_field=lambda x: True), save=MagicMock())
        self.frappe = MagicMock()
        self.frappe.throw.side_effect = lambda text, *args: (_ for _ in ()).throw(ValueError(text))
        self.frappe.has_permission.return_value = False
        self.frappe.session.user = 'assigned@example.com'
        self.env = dict(frappe=self.frappe, _=lambda x:x, escape=escape, get_datetime=lambda x:x,
            PLAN_STATUSES=('Open','In Progress','Delayed','On Hold','Postponed','Customer Delayed','Completed'),
            REASON_STATUSES={'Delayed','On Hold','Postponed','Customer Delayed'},
            _read_task=lambda *a, **k:(SimpleNamespace(status='Open'),self.item), _is_assigned=lambda x:True)
        sys.modules['bsgroup.project_daily_work'] = SimpleNamespace(enabled=lambda:True)
        exec(compile(ast.Module(body=[function],type_ignores=[]),'<status endpoint>','exec'),self.env)

    def test_reason_required_for_each_pause_state(self):
        for status in self.env['REASON_STATUSES']:
            with self.subTest(status=status), self.assertRaisesRegex(ValueError,'reason'):
                self.env['set_task_status']('P1','T1',status,'v1','  ')
        self.item.save.assert_not_called()

    def test_assignee_can_save_reason_and_escaped_history(self):
        self.env['set_task_status']('P1','T1','Customer Delayed','v1','Customer <requested> a later visit')
        self.assertEqual(self.item.custom_bs_status_reason,'Customer <requested> a later visit')
        self.assertEqual(self.item.status,'Customer Delayed')
        self.item.save.assert_called_once_with(ignore_permissions=True)
        self.assertIn('&lt;requested&gt;',self.frappe.get_doc.call_args.args[0]['content'])

    def test_unassigned_user_denied(self):
        self.env['_is_assigned'] = lambda x:False
        with self.assertRaisesRegex(ValueError,'cannot change'):
            self.env['set_task_status']('P1','T1','On Hold','v1','Reason')
        self.item.save.assert_not_called()

    def test_old_version_denied_and_resumption_clears_visible_reason(self):
        with self.assertRaisesRegex(ValueError,'changed'):
            self.env['set_task_status']('P1','T1','Delayed','old','Reason')
        self.item.custom_bs_status_reason='Old delay'
        self.env['set_task_status']('P1','T1','In Progress','v1')
        self.assertEqual(self.item.custom_bs_status_reason,'')


if __name__ == '__main__':
    unittest.main()
