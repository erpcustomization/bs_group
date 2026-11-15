import importlib.util
import json
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

class Row(dict):
    __getattr__=dict.get
    __setattr__=dict.__setitem__

class LabourTests(unittest.TestCase):
    def setUp(self):
        self.f=types.ModuleType('frappe')
        self.f._=lambda x:x
        self.f.whitelist=lambda **kw:lambda f:f
        self.f.throw=lambda text,*a:(_ for _ in ()).throw(ValueError(text))
        self.f.parse_json=json.loads
        self.f.session=Row(user='staff')
        self.f.db=Row(exists=Mock(return_value=False))
        self.f.get_cached_value=Mock(return_value='AED')
        self.project=Row(name='P',company='AE')
        self.task=Row(name='T')
        self.line=Row(name='LINE',no_of_persons=3,days=2,rate=25,role__skill='Helper')
        self.approval=Row(name='LP',docstatus=1,workflow_state='Approved',source='Project',reference='P',task='T',company='AE',labor_line_items=[self.line],approved_person_days=6,total_labor_cost=150)
        self.expense=Row(flags=Row(),save=Mock(),insert=Mock(),modified='v1')
        self.f.get_doc=Mock(return_value=self.approval)
        self.f.new_doc=Mock(return_value=self.expense)
        self.legacy=types.SimpleNamespace(get_consumed_person_days=Mock(return_value=0),get_consumed_cost=Mock(return_value=0))
        self.p=patch.dict(sys.modules,{'frappe':self.f,'frappe.utils':types.SimpleNamespace(getdate=lambda x=None:date.fromisoformat(str(x)) if x else date(2026,11,16),flt=lambda x:float(x or 0)),
            'bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval':self.legacy})
        self.p.start()
        spec=importlib.util.spec_from_file_location('labour_test',Path(__file__).resolve().parents[1]/'project_labor_work.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.m.enabled=Mock(return_value=True);self.m.has_preapproval=Mock(return_value=True)
        self.m.usage=Mock(return_value=[]);self.m.totals=Mock(return_value=(0,0))
        self.payload=dict(used='Yes',approval='LP',line='LINE',persons=2,expected_modified='')

    def tearDown(self):self.p.stop()
    def record(self,payload=None):return self.m.record(self.project,self.task,self.payload if payload is None else payload,'WORK','Installed',date(2026,11,16))

    def test_no_creates_no_expense(self):
        self.record({'used':'No'});self.f.new_doc.assert_not_called()
    def test_missing_answer_blocks_preapproved_project(self):
        with self.assertRaisesRegex(ValueError,'Yes or No'):self.record({})
    def test_no_preapproval_normal_work_unchanged(self):
        self.m.has_preapproval.return_value=False
        self.assertIsNone(self.record({}))
    def test_exact_amount_and_author_from_server(self):
        self.payload.update(rate=1,amount=1,recorded_by='forged')
        self.record()
        self.assertEqual(self.expense.amount,50)
        self.assertEqual(self.expense.recorded_by,'staff')
        self.assertEqual(self.expense.work_date,date(2026,11,16))
        self.f.get_doc.assert_called_with('Labor Preapproval','LP',for_update=True)
    def test_daily_limit_blocks(self):
        self.payload['persons']=4
        with self.assertRaisesRegex(ValueError,'daily headcount'):self.record()
        self.f.new_doc.assert_not_called()
    def test_total_line_allowance_blocks(self):
        self.m.usage.return_value=[Row(labor_line='LINE',persons=5,amount=125)]
        with self.assertRaisesRegex(ValueError,'labour type'):self.record()
    def test_legacy_attendance_counts_toward_limit(self):
        self.legacy.get_consumed_person_days.return_value=5
        with self.assertRaisesRegex(ValueError,'person-day'):self.record()
    def test_legacy_payments_count_toward_limit(self):
        self.legacy.get_consumed_cost.return_value=125
        with self.assertRaisesRegex(ValueError,'cost limit'):self.record()
    def test_invalid_counts(self):
        for value in [0,-1,1.2,'NaN','Infinity','abc',None]:
            self.payload['persons']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.record()
    def test_wrong_scope_or_unapproved(self):
        for field,value in [('reference','OTHER'),('task','OTHER'),('company','OM'),('docstatus',0),('workflow_state','Pending Approval')]:
            old=self.approval[field];self.approval[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.record()
            self.approval[field]=old
    def current(self,**kw):
        self.expense.update(name='EX',recorded_by='staff',work_entry='OLD',modified='v1',**kw)
        self.f.db.exists.side_effect=lambda dt,*a,**k:dt==self.m.DT
        self.f.get_doc.side_effect=lambda dt,*a,**k:self.expense if dt==self.m.DT else self.approval
    def test_same_request_retry_does_not_save_twice(self):
        self.current();self.expense.work_entry='WORK'
        self.assertEqual(self.record(),'EX');self.expense.save.assert_not_called();self.f.new_doc.assert_not_called()
    def test_daily_correction_updates_existing_not_inserts(self):
        self.current();self.payload['expected_modified']='v1'
        self.record();self.expense.save.assert_called_once();self.expense.insert.assert_not_called()
    def test_other_user_cannot_duplicate_daily_expense(self):
        self.current();self.expense.recorded_by='other'
        with self.assertRaisesRegex(ValueError,'already been recorded'):self.record()
    def test_stale_daily_correction_blocked(self):
        self.current()
        with self.assertRaisesRegex(ValueError,'changed'):self.record()
    def test_manual_attendance_duplicate_blocked(self):
        self.f.db.exists.side_effect=lambda dt,*a,**k:dt=='Labor Attendance'
        with self.assertRaisesRegex(ValueError,'attendance already'):self.record()
    def test_key_is_shared_across_users_but_not_days_or_lines(self):
        self.assertEqual(self.m.expense_key('LP','L','2026-11-16'),self.m.expense_key('LP','L','2026-11-16'))
        self.assertNotEqual(self.m.expense_key('LP','L','2026-11-16'),self.m.expense_key('LP','L','2026-11-17'))
        self.assertNotEqual(self.m.expense_key('LP','L','2026-11-16'),self.m.expense_key('LP','OTHER','2026-11-16'))

if __name__=='__main__':unittest.main()
