"""Behaviour checks without a running Frappe site."""
import ast
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from html import escape
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).parents[1]


class Doc(dict):
    def update(self, values):
        # Frappe Document.update accepts a mapping, not keyword arguments.
        super().update(values)
        return self

    def set(self, key, value):
        self[key] = value

    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        self.f.throw.side_effect = lambda message, *a: (_ for _ in ()).throw(ValueError(message))
        self.f.session.user = 'assignee@example.com'
        self.env = dict(frappe=self.f, _=lambda s:s, ContextVar=ContextVar,
            contextmanager=contextmanager, escape=escape, strip_html=lambda s:s,
            now_datetime=lambda:'NOW', DT='Delivery Request', _internal=ContextVar('test', default=False))
        source=ast.parse((ROOT/'bsgroup/supply_delivery.py').read_text())
        functions=[n for n in source.body if isinstance(n, ast.FunctionDef)]
        for fn in functions:
            if fn.name!='writing': fn.decorator_list=[]
        exec(compile(ast.Module(body=functions,type_ignores=[]),'<delivery>','exec'),self.env)
        self.task=Doc(name='T1',project='P1',company='OM',status='Open',custom_bs_delivery_pr='PR1',custom_bs_delivery_coordinator='assignee@example.com',custom_bs_delivery_person='driver@example.com',save=MagicMock(),reload=MagicMock())
        self.pr=Doc(name='PR1',custom_project='P1',company='OM',docstatus=1,workflow_state='Approved',status='Pending')
        self.project=Doc(name='P1',company='OM',status='Open',reload=MagicMock(),save=MagicMock(),add_comment=MagicMock())
        self.delivery=Doc(name='DEL1',project='P1',company='OM',task='T1',purchase_request='PR1',status='Open',coordinator='assignee@example.com',delivery_person='driver@example.com',coordinator_notes='Arranged delivery',coordinator_proof='/private/files/arrangement.pdf',delivery_notes='Delivered to site',delivery_proof='/private/files/proof.pdf',save=MagicMock(),completed_by=None)
        self.docs={'Task':self.task,'Project':self.project,'Material Request':self.pr,'Delivery Request':self.delivery}
        self.f.get_doc.side_effect=lambda dt,*a,**k:self.docs[dt]
        self.f.db.get_value.return_value='T1'
        self.env['assignees']=lambda task:{'assignee@example.com','driver@example.com'}
        self.capture=MagicMock(return_value={'timesheet':'TS1'})
        sys.modules['bsgroup.project_daily_work']=SimpleNamespace(capture=self.capture)

    def test_procurement_states_never_complete_delivery(self):
        for state,approval,docstatus,expected in [('Pending','Draft',0,'Open'),('Pending','Rejected',0,'On Hold'),('Stopped','Approved',1,'On Hold'),('Ordered','Approved',1,'In Progress'),('Received','Approved',1,'In Progress'),('Cancelled','Approved',2,'On Hold')]:
            self.pr.update(dict(status=state,workflow_state=approval,docstatus=docstatus))
            self.assertEqual(self.env['procurement_stage'](self.pr)[1],expected)

    def test_only_pure_supply_is_collapsed(self):
        self.assertTrue(self.env['supply_only'](['supply']))
        self.assertFalse(self.env['supply_only'](['supply','elv']))

    def test_close_requires_assigned_user(self):
        self.env['assignees']=lambda task:set()
        with self.assertRaisesRegex(ValueError,'Only a user assigned'):self.env['complete']('DEL1')
        self.capture.assert_not_called()

    def test_close_requires_approval_notes_and_private_attached_proof(self):
        self.pr.docstatus=0
        with self.assertRaisesRegex(ValueError,'approved purchase'):self.env['complete']('DEL1')
        self.pr.docstatus=1
        self.delivery.coordinator_notes=' '
        with self.assertRaisesRegex(ValueError,'Attach delivery proof'):self.env['complete']('DEL1')
        self.delivery.coordinator_notes='Arranged delivery'
        self.f.db.exists.return_value=False
        with self.assertRaisesRegex(ValueError,'private document'):self.env['complete']('DEL1')
        self.capture.assert_not_called()

    def test_both_people_required_and_each_submission_is_idempotent(self):
        self.f.db.exists.return_value=True
        self.f.get_all.return_value=['Completed']
        result=self.env['complete']('DEL1')
        self.assertEqual(result['timesheet'],'TS1')
        self.assertEqual(self.task.status,'Open')
        self.assertEqual(self.project.status,'Open')
        self.assertEqual(self.delivery.status,'Awaiting delivery person')
        self.env['complete']('DEL1')
        self.capture.assert_called_once()
        self.f.session.user='driver@example.com'
        self.env['complete']('DEL1')
        self.assertEqual(self.task.status,'Completed')
        self.assertEqual(self.project.status,'Completed')
        self.assertEqual(self.delivery.completed_by,'driver@example.com')
        self.env['complete']('DEL1')
        self.assertEqual(self.capture.call_count,2)
        self.assertEqual(self.capture.call_args_list[0].args[3],'delivery-DEL1-coordinator')
        self.assertEqual(self.capture.call_args_list[1].args[3],'delivery-DEL1-delivery')

    def test_participant_cannot_edit_other_person_or_submitted_work(self):
        old=Doc(self.delivery)
        self.delivery.is_new=lambda:False
        self.delivery.get_doc_before_save=lambda:old
        self.delivery.delivery_notes='Changed by coordinator'
        with self.assertRaisesRegex(ValueError,'own delivery work'):self.env['validate'](self.delivery)
        self.delivery.delivery_notes=old.delivery_notes
        old.coordinator_completed_on='EARLIER'
        self.delivery.coordinator_completed_on='EARLIER'
        self.delivery.coordinator_notes='Edited after submission'
        with self.assertRaisesRegex(ValueError,'Submitted evidence'):self.env['validate'](self.delivery)

    def test_reconciliation_reuses_request_and_retains_completed_evidence(self):
        self.f.db.exists.return_value=True
        self.f.db.get_value.return_value='DEL1'
        self.assertEqual(self.env['synchronize']('T1'),'DEL1')
        self.assertEqual(self.env['synchronize']('T1'),'DEL1')
        self.assertEqual(self.delivery.save.call_count,1)
        self.delivery.status='Completed'
        self.pr.docstatus=2
        self.env['synchronize']('T1')
        self.assertEqual(self.delivery.status,'Completed')

    def test_unassigned_task_does_not_create_request(self):
        self.f.db.get_value.return_value=None
        self.env['assignees']=lambda task:set()
        self.assertIsNone(self.env['synchronize']('T1'))
        self.assertFalse(any(c.args[0]=='Delivery Request' for c in self.f.get_doc.call_args_list))

    def test_ordinary_task_is_not_blocked(self):
        old=Doc(custom_bs_delivery_pr=None)
        task=Doc(custom_bs_delivery_pr='',get_doc_before_save=lambda:old)
        self.env['protect_task'](task)
        task.custom_bs_delivery_pr='PR1'
        with self.assertRaisesRegex(ValueError,'managed automatically'):self.env['protect_task'](task)

    def test_ai_rejects_multiple_supply_activities(self):
        source=ast.parse((ROOT/'bsgroup/project_ai_plan.py').read_text())
        fn=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='validate_plan')
        sys.modules['bsgroup.supply_delivery']=SimpleNamespace(supply_only=self.env['supply_only'])
        env={'json':json,'getdate':date.fromisoformat,'text':lambda s,*a:s,'supply_only':self.env['supply_only']}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'<plan>','exec'),env)
        scope=dict(modules=['supply'],start_date='2026-11-15',end_date='2026-11-20',quotation=[{'ref':'Q1'}],costing=[{'ref':'D1'}])
        row=dict(subject='Delivery',description='Deliver switch',start_day=0,end_day=5,sources=['Q1','D1'])
        self.assertEqual(len(env['validate_plan'](json.dumps([row]),scope)),1)
        with self.assertRaisesRegex(ValueError,'exactly one'):env['validate_plan'](json.dumps([row,row]),scope)
        row['sources']=['Q1']
        with self.assertRaisesRegex(ValueError,'cover all'):env['validate_plan'](json.dumps([row]),scope)


if __name__=='__main__': unittest.main()
