import importlib.util
import json
import re
import sys
import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch


class Record(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    def __getattribute__(self, name):
        if name == 'items' and name in self: return self[name]
        return super().__getattribute__(name)


class PlanTests(unittest.TestCase):
    def setUp(self):
        f = types.ModuleType('frappe')
        f._ = lambda s:s
        f.whitelist = lambda *a,**kw:lambda fn:fn
        f.throw = lambda s,*a:(_ for _ in ()).throw(ValueError(s))
        f.PermissionError=ValueError
        f.db=Record(exists=Mock(return_value=True),get_value=Mock(return_value=None))
        f.session=Record(user='sales@example.com');f.enqueue=Mock()
        u=types.ModuleType('frappe.utils')
        u.getdate=lambda s:date.fromisoformat(str(s)[:10])
        u.add_days=lambda s,n:u.getdate(s)+timedelta(days=n)
        u.now_datetime=datetime.now
        u.strip_html=lambda s:re.sub('<[^>]*>','',s)
        self.p=patch.dict(sys.modules,{'frappe':f,'frappe.utils':u});self.p.start()
        spec=importlib.util.spec_from_file_location('ai_plan_test',Path(__file__).resolve().parents[1]/'project_ai_plan.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m);self.f=f
        self.source=dict(start_date='2026-11-11',end_date='2026-11-20',quotation=[{'ref':'Q1'}],costing=[{'ref':'D1'}])
        self.row=dict(subject='Install supplied equipment',description='Inspect, install and test the quoted scope.',start_day=0,end_day=9,sources=['Q1','D1'])

    def tearDown(self):self.p.stop()

    def test_valid_plan_and_markdown_wrapper(self):
        result=self.m.validate_plan('```json\n'+json.dumps([self.row])+'\n```',self.source)
        self.assertEqual(result[0]['end_day'],9)

    def test_bad_json_types_and_oversized_plan(self):
        for raw in ('not json','{}','[]',json.dumps([self.row]*61)):
            with self.assertRaises((ValueError,TypeError)):self.m.validate_plan(raw,self.source)

    def test_unknown_sources_missing_coverage_and_duplicates_rejected(self):
        for rows in ([dict(self.row,sources=['Q1'])],[dict(self.row,sources=['OTHER'])],[self.row,self.row]):
            with self.assertRaises(ValueError):self.m.validate_plan(json.dumps(rows),self.source)

    def test_dates_bounded_and_integer_only(self):
        for change in ({'start_day':-1},{'end_day':10},{'start_day':8,'end_day':2},{'start_day':True},{'end_day':'9'}):
            with self.assertRaises(ValueError):self.m.validate_plan(json.dumps([dict(self.row,**change)]),self.source)

    def test_untrusted_extra_fields_cannot_assign_or_execute(self):
        row=dict(self.row,assigned_to='Administrator',status='Completed',doctype='User',code='malicious')
        result=self.m.validate_plan(json.dumps([row]),self.source)[0]
        self.assertEqual(set(result),{'subject','description','start_day','end_day','sources'})

    def test_source_allowlist_excludes_finance_contacts_files_and_users(self):
        line=Record(item_code='Camera',item_name='Camera',description='<b>Install camera</b>',qty=2,uom='Nos',rate=98765,cost_rate=87654)
        q=Record(items=[line],party_name='SECRET CUSTOMER',custom_customer_po='/private/files/SECRET.pdf')
        sheet=Record(items=[line],resources=[Record(resource_type='Technician',no_of_persons=2,no_of_days=3,hours=8,cost_rate=76543)],subject='SECRET SUBJECT')
        p=Record(expected_start_date='2026-11-11',expected_end_date='2026-11-20',custom_project_manager='SECRET EMPLOYEE')
        source=self.m.source_snapshot(q,sheet,p,['elv'])
        content=json.dumps(source)
        for forbidden in ('SECRET','98765','87654','76543','private/files','<b>'):self.assertNotIn(forbidden,content)
        self.assertEqual(source['quotation'][0]['ref'],'Q1');self.assertEqual(source['costing'][0]['ref'],'D1')
        self.assertEqual(source['resources'][0]['no_of_persons'],'2')

    def test_enqueue_occurs_only_after_transaction_commit(self):
        self.m.enqueue('RUN-1')
        args=self.f.enqueue.call_args.kwargs
        self.assertTrue(args['enqueue_after_commit']);self.assertEqual(args['run_name'],'RUN-1')

    def test_configuration_must_be_enabled_and_have_a_key(self):
        settings=Record(is_enabled=1,ai_provider='Anthropic (Claude)',api_key='encrypted')
        self.f.get_single=Mock(return_value=settings)
        self.assertTrue(self.m.available())
        for key,value in [('is_enabled',0),('ai_provider','Unconfigured'),('api_key','')]:
            before=settings[key];settings[key]=value;self.assertFalse(self.m.available());settings[key]=before


if __name__=='__main__':unittest.main()
