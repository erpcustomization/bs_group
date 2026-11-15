import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

class Row(dict):
    __getattr__=dict.get
    __setattr__=dict.__setitem__

class Tests(unittest.TestCase):
    def setUp(self):
        self.f=types.ModuleType('frappe')
        self.f.session=Row(user='mohan@bitssecureit.com')
        self.f.PermissionError=PermissionError;self.f.TimestampMismatchError=ValueError
        self.f.throw=lambda msg,*args: (_ for _ in ()).throw(ValueError(msg))
        self.f.utils=Row(escape_html=lambda x:x)
        self.f.get_cached_value=Mock(return_value='AED')
        self.doc=Row(doctype='Labor Preapproval', name='LP', docstatus=0, workflow_state='Pending Approval',
            modified='v1',source='Project',reference='P',task='T',company='AE',total_labor_cost=4500,
            approved_person_days=30,labor_line_items=[Row(role__skill='Helper',no_of_persons=1,days=30,rate=150,total_cost=4500)],
            check_permission=Mock(),has_value_changed=Mock(return_value=True),as_dict=Mock(return_value={'name':'LP'}))
        self.f.get_doc=Mock(return_value=self.doc)
        self.workflow=types.SimpleNamespace(get_transitions=Mock(return_value=[Row(action='Approve'),Row(action='Reject')]),
            apply_workflow=Mock(return_value=Row(workflow_state='Approved',add_comment=Mock())))
        self.require=Mock();self.visible=Mock(return_value=['LP'])
        self.p=patch.dict(sys.modules,{'frappe':self.f,'frappe.utils':types.SimpleNamespace(get_datetime=lambda x:x),
            'frappe.model.workflow':self.workflow,'bsgroup.dcs.manager_approval':types.SimpleNamespace(FIXED_APPROVER='mohan@bitssecureit.com'),
            'bsgroup.approval_requests':types.SimpleNamespace(require_mohan=self.require),
            'bsgroup.procurement_lists':types.SimpleNamespace(visible_company_names=self.visible)})
        self.p.start()
        spec=importlib.util.spec_from_file_location('subject',Path(__file__).resolve().parents[1]/'labour_approvals.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
    def tearDown(self):self.p.stop()
    def test_review_has_real_allowance(self):
        d=self.m.review('LP');self.assertEqual(d['items'][0]['persons'],1);self.assertEqual(d['person_days'],30)
        self.assertEqual(d['actions'],['Approve','Reject']);self.doc.check_permission.assert_called_with('read')
    def test_native_workflow_used(self):
        self.assertEqual(self.m.decide('LP','v1','Approve','')['state'],'Approved')
        self.workflow.apply_workflow.assert_called_once_with({'name':'LP'},'Approve')
        self.f.get_doc.assert_called_with('Labor Preapproval','LP',for_update=True)
    def test_stale_blocked(self):
        with self.assertRaisesRegex(ValueError,'changed'):self.m.decide('LP','old','Approve','')
        self.workflow.apply_workflow.assert_not_called()
    def test_duplicate_decision_blocked(self):
        self.doc.docstatus=1;self.doc.workflow_state='Approved'
        with self.assertRaisesRegex(ValueError,'no longer'):self.m.decide('LP','v1','Approve','')
        self.workflow.apply_workflow.assert_not_called()
    def test_rejection_needs_reason(self):
        with self.assertRaisesRegex(ValueError,'reason'):self.m.decide('LP','v1','Reject','')
    def test_reason_recorded(self):
        self.m.decide('LP','v1','Reject','Revise headcount')
        self.workflow.apply_workflow.return_value.add_comment.assert_called_once_with('Comment','Revise headcount')
    def test_unsupported_action(self):
        with self.assertRaisesRegex(ValueError,'support'):self.m.decide('LP','v1','Return for Rework','reason')
    def test_company_scope(self):
        self.visible.return_value=[]
        with self.assertRaisesRegex(ValueError,'company'):self.m.review('LP')
    def test_non_mohan_decision_blocked(self):
        self.doc.workflow_state='Approved';self.f.session.user='manager'
        with self.assertRaisesRegex(ValueError,'Mohan'):self.m.guard_decision(self.doc)
    def test_mohan_decision_allowed(self):
        self.doc.workflow_state='Approved';self.m.guard_decision(self.doc)
    def test_normal_pending_save_allowed(self):
        self.f.session.user='staff';self.m.guard_decision(self.doc)
    def test_unchanged_historical_approval_allowed(self):
        self.doc.workflow_state='Approved';self.doc.has_value_changed.return_value=False
        self.f.session.user='staff';self.m.guard_decision(self.doc)
    def test_migration_idempotent_preserves_conditions_roles(self):
        transition=Row(state='Pending Approval',next_state='Approved',allowed='Projects Manager',condition='doc.total_labor_cost > 0')
        workflow=Row(transitions=[transition],save=Mock())
        self.f.get_all=Mock(return_value=['W']);self.f.get_doc.return_value=workflow;self.f.clear_cache=Mock()
        self.m.install();self.m.install()
        workflow.save.assert_called_once();self.assertEqual(transition.allowed,'Projects Manager')
        self.assertIn('doc.total_labor_cost > 0',transition.condition)
        self.assertIn('mohan@bitssecureit.com',transition.condition)

if __name__=='__main__':unittest.main()
