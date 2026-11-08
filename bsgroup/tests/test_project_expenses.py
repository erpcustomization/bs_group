import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Record(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__


class ProjectExpenseTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f._ = lambda text: text
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.PermissionError = PermissionError
        self.f.throw = lambda message, exc=ValueError: (_ for _ in ()).throw(exc(message))
        self.f.session = Record(user='staff@example.com')
        self.f.has_permission = Mock(return_value=True)
        self.f.get_roles = Mock(side_effect=lambda user=None: ['Expense Approver'] if user else ['Employee'])
        self.project = Record(name='PROJ-1', project_name='Project 1', company='Company A',
                              status='Open', custom_project_manager='MGR', check_permission=Mock())
        self.f.get_doc = Mock(return_value=self.project)
        self.employee = Record(company='Company A', user_id='staff@example.com', status='Active')
        self.manager = Record(user_id='manager@example.com', status='Active')
        self.f.db = Record(get_value=Mock(side_effect=self.value))
        self.f.get_all = Mock(return_value=[Record(name='EMP')])
        self.f.get_list = Mock(return_value=[])
        self.patch = patch.dict(sys.modules, {'frappe': self.f})
        self.patch.start()
        spec = importlib.util.spec_from_file_location('project_expenses_test', Path(__file__).resolve().parents[1]/'project_expenses.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.doc = Record(project='PROJ-1', employee='EMP', company='Company A', docstatus=0,
                          workflow_state='Draft', approval_status='Draft', expenses=[Record()], taxes=[Record()],
                          get_doc_before_save=Mock(return_value=None))

    def value(self, doctype, name, fields, **kwargs):
        if doctype == 'Employee': return self.manager if name == 'MGR' else self.employee
        if doctype == 'User': return 1
        if doctype == 'Company': return 'AED'
        if doctype == 'Task': return 'PROJ-1'

    def old(self, **kwargs):
        old = Record(project='PROJ-1', employee='EMP', docstatus=0, workflow_state='Draft')
        old.update(kwargs)
        self.doc.get_doc_before_save.return_value = old
        return old

    def tearDown(self): self.patch.stop()

    def test_missing_project_blocks_before_any_lookup(self):
        self.doc.project = None
        with self.assertRaisesRegex(ValueError, 'project is required'): self.m.validate(self.doc)
        self.f.get_doc.assert_not_called()

    def test_project_read_permission_enforced_for_api_and_panel(self):
        self.project.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): self.m.validate(self.doc)
        with self.assertRaises(PermissionError): self.m.context('PROJ-1')
        self.f.get_list.assert_not_called()

    def test_forged_approver_replaced_and_rows_bound(self):
        self.doc.expense_approver = 'other@example.com'
        self.m.validate(self.doc)
        self.assertEqual(self.doc.expense_approver, 'manager@example.com')
        self.assertEqual(self.doc.expenses[0].project, 'PROJ-1')
        self.assertEqual(self.doc.taxes[0].project, 'PROJ-1')

    def test_cross_company_rejected(self):
        self.doc.company = 'Company B'
        with self.assertRaisesRegex(ValueError, 'same company'): self.m.validate(self.doc)
        self.doc.company = 'Company A'
        self.employee.company = 'Company B'
        with self.assertRaisesRegex(ValueError, 'active employee'): self.m.validate(self.doc)

    def test_missing_employee_not_resolved_to_arbitrary_record(self):
        self.doc.employee = None
        with self.assertRaisesRegex(ValueError, 'employee is required'): self.m.validate(self.doc)

    def test_cannot_claim_for_another_user(self):
        self.employee.user_id = 'other@example.com'
        with self.assertRaises(PermissionError): self.m.validate(self.doc)

    def test_immutable_project_and_employee(self):
        old = self.old(project='PROJ-2')
        with self.assertRaisesRegex(ValueError, 'project on an existing'): self.m.validate(self.doc)
        old.project = 'PROJ-1'; old.employee = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'employee on an existing'): self.m.validate(self.doc)

    def test_missing_disabled_or_unprivileged_manager_blocks(self):
        self.project.custom_project_manager = None
        with self.assertRaisesRegex(ValueError, 'Project Manager'): self.m.validate(self.doc)
        self.project.custom_project_manager = 'MGR'; self.manager.status = 'Left'
        with self.assertRaisesRegex(ValueError, 'Project Manager'): self.m.validate(self.doc)
        self.manager.status = 'Active'; self.f.get_roles.return_value = []; self.f.get_roles.side_effect = None
        with self.assertRaisesRegex(ValueError, 'Expense Approver access'): self.m.validate(self.doc)
        self.f.get_roles.return_value = ['Expense Approver']
        self.f.db.get_value.side_effect = lambda dt, *a, **kw: 0 if dt == 'User' else self.value(dt, *a, **kw)
        with self.assertRaisesRegex(ValueError, 'disabled'): self.m.validate(self.doc)

    def test_manager_without_project_access_cannot_receive_claim(self):
        self.f.has_permission.return_value = False
        with self.assertRaisesRegex(ValueError, 'cannot access'): self.m.validate(self.doc)

    def test_wrong_manager_cannot_approve_or_reject(self):
        self.old(workflow_state='Pending Approval')
        for state in ['Approved by the Manager', 'Reject by the Manager']:
            self.doc.workflow_state = state
            with self.assertRaises(PermissionError): self.m.validate(self.doc)
        self.f.session.user = 'manager@example.com'
        self.m.validate(self.doc)

    def test_no_self_approval(self):
        self.old(workflow_state='Pending Approval')
        self.manager.user_id = self.employee.user_id
        self.doc.workflow_state = 'Approved by the Manager'
        with self.assertRaises(PermissionError): self.m.validate(self.doc)
        self.doc.workflow_state = 'Pending Approval'
        with self.assertRaisesRegex(ValueError, 'own expense'): self.m.validate(self.doc)

    def test_new_claim_cannot_skip_draft(self):
        for state in ['Pending Approval', 'Approved by the Manager', 'Approved']:
            self.doc.workflow_state = state
            with self.assertRaisesRegex(ValueError, 'start as drafts'): self.m.validate(self.doc)

    def test_row_and_task_project_mismatch_rejected(self):
        for table in ['expenses', 'taxes']:
            self.doc[table][0].project = 'PROJ-2'
            with self.assertRaisesRegex(ValueError, 'Every expense'): self.m.validate(self.doc)
            self.doc[table][0].project = 'PROJ-1'
        self.doc.task = 'TASK'
        native = self.f.db.get_value.side_effect
        self.f.db.get_value.side_effect = lambda dt, *a, **kw: 'PROJ-2' if dt == 'Task' else native(dt,*a,**kw)
        with self.assertRaisesRegex(ValueError, 'selected task'): self.m.validate(self.doc)

    def test_cancelled_project_rejected(self):
        self.project.status = 'Cancelled'
        with self.assertRaisesRegex(ValueError, 'cancelled project'): self.m.validate(self.doc)
        self.assertFalse(self.m.context('PROJ-1')['can_create'])

    def test_history_preserved_for_accounting_updates(self):
        self.old(docstatus=1, project=None); self.doc.project = None
        self.m.validate(self.doc)
        self.f.get_doc.assert_not_called()
        self.doc.project = 'PROJ-1'
        with self.assertRaisesRegex(ValueError, 'cannot be changed'): self.m.validate(self.doc)

    def test_employee_panel_uses_native_permissions_and_own_filter(self):
        result = self.m.context('PROJ-1')
        self.assertTrue(result['can_create'])
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'], {'project':'PROJ-1', 'employee':'EMP'})
        self.assertNotIn('ignore_permissions', self.f.get_list.call_args.kwargs)
        self.f.session.user = 'manager@example.com'
        self.m.context('PROJ-1')
        self.assertEqual(self.f.get_list.call_args.kwargs['filters'], {'project':'PROJ-1'})

    def test_ambiguous_employee_prevents_new_claim(self):
        self.f.get_all.return_value = [Record(name='EMP'), Record(name='EMP-2')]
        result = self.m.context('PROJ-1')
        self.assertFalse(result['can_create'])
        self.assertIsNone(result['employee'])


if __name__ == '__main__': unittest.main()
