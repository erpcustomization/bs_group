"""Run without a bench: python bsgroup/tests/test_time_off_rules.py."""
import importlib.util
import sys
import types
import unittest
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

class Obj(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__

def getdate(value=None):
    return value if isinstance(value, date) else date.fromisoformat(value)

class TimeOffRules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fake = types.ModuleType('frappe')
        fake.whitelist = lambda *a, **kw: lambda f:f
        fake.throw = lambda message, *a: (_ for _ in ()).throw(ValueError(message))
        utils = types.ModuleType('frappe.utils')
        utils.getdate, utils.flt = getdate, lambda x: float(x or 0)
        dashboard = types.ModuleType('bsgroup.dashboard_leave')
        dashboard.dubai_today = lambda:'2026-11-06'
        dashboard.has_records = lambda *a:False
        cls.fake = fake
        cls.modules = patch.dict(sys.modules, {'frappe':fake,'frappe.utils':utils,'bsgroup.dashboard_leave':dashboard})
        cls.modules.start()
        spec=importlib.util.spec_from_file_location('time_off_under_test',Path(__file__).parents[1]/'time_off.py')
        cls.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.module)
    @classmethod
    def tearDownClass(cls): cls.modules.stop()
    def rows(self,balance,count=3):
        return [(date(2026,11,9)+timedelta(days=i),1,1,balance,'allocation1') for i in range(count)]
    def totals(self,parts):
        return (sum(x['days'] for x in parts if x['leave_type']==self.module.ANNUAL),sum(x['days'] for x in parts if x['leave_type']==self.module.UNPAID))
    def test_fully_paid(self):
        parts=self.module.split_emergency(self.rows(5));self.assertEqual(self.totals(parts),(3,0));self.assertEqual(len(parts),1)
    def test_zero_balance_unpaid(self):
        parts=self.module.split_emergency(self.rows(0));self.assertEqual(self.totals(parts),(0,3));self.assertEqual(len(parts),1)
    def test_partial_balance(self):
        parts=self.module.split_emergency(self.rows(2));self.assertEqual(self.totals(parts),(2,1));self.assertEqual(parts[1]['from_date'],'2026-11-11')
    def test_half_day_split(self):
        parts=self.module.split_emergency(self.rows(1.5));self.assertEqual(self.totals(parts),(1.5,1.5))
        halves=[p for p in parts if p['half_day']];self.assertEqual(len(halves),2);self.assertEqual(halves[0]['half_day_date'],halves[1]['half_day_date'])
    def test_holiday_not_charged_as_unpaid_while_paid_balance_exists(self):
        parts=self.module.split_emergency([(date(2026,11,8),0,1,5,'a')]);self.assertEqual(parts,[])
    def test_new_allocation_has_separate_balance(self):
        rows=self.rows(1,2);rows[1]=(*rows[1][:4],'allocation2')
        self.assertEqual(self.totals(self.module.split_emergency(rows)),(2,0))
    def test_unsupported_fraction_fails_closed(self):
        with self.assertRaises(ValueError):self.module.split_emergency(self.rows(.3))
    def test_past_and_reversed_dates(self):
        with self.assertRaises(ValueError):self.module.dates('2026-11-05','2026-11-08')
        with self.assertRaises(ValueError):self.module.dates('2026-11-10','2026-11-09')
    def test_certificate_one_day_allowed_two_days_denied(self):
        spec=importlib.util.spec_from_file_location('medical_under_test',Path(__file__).parents[1]/'utils'/'leave_application.py')
        module=importlib.util.module_from_spec(spec)
        self.fake._=lambda text:text
        sys.modules['bsgroup.dashboard_leave'].validate_self_service=lambda doc:None
        spec.loader.exec_module(module)
        doc=Obj(leave_type='Sick Leave',total_leave_days=1,flags=Obj())
        module.validate_medical_certificate(doc)
        doc.total_leave_days=2
        with self.assertRaises(ValueError):module.validate_medical_certificate(doc)
        doc.custom_medical_certificate='/private/files/certificate.pdf'
        module.validate_medical_certificate(doc)

    def test_apply_requires_contact_and_certificate_before_creating_records(self):
        self.fake.db=Obj(sql=lambda *a:None)
        self.fake.get_list=lambda *a,**kw:[]
        self.fake.parse_json=json.loads
        self.fake.new_doc=lambda *a: (_ for _ in ()).throw(AssertionError('Must validate before insert'))
        plan=dict(parts=[],total_days=2,annual_available=0,certificate_required=False)
        with patch.object(self.module,'own_employee',return_value=Obj(name='EMP-SELF',company='Company')), patch.object(self.module,'make_plan',return_value=plan):
            with self.assertRaisesRegex(ValueError,'emergency reason'):
                self.module.apply('Emergency Leave','2026-11-09','2026-11-10','a'*32,'[]')
            plan['certificate_required']=True
            with self.assertRaisesRegex(ValueError,'medical certificate'):
                self.module.apply('Sick Leave','2026-11-09','2026-11-10','a'*32,'[]')

    def test_duplicate_request_returns_existing_records(self):
        self.fake.db=Obj(sql=lambda *a:None)
        self.fake.get_list=lambda *a,**kw:['HR-LAP-existing']
        with patch.object(self.module,'own_employee',return_value=Obj(name='EMP-SELF')):
            self.assertEqual(self.module.apply('Annual Leave','2026-11-09','2026-11-10','a'*32,'[]'),{'names':['HR-LAP-existing']})

    def test_changed_split_requires_new_review(self):
        self.fake.db=Obj(sql=lambda *a:None)
        self.fake.get_list=lambda *a,**kw:[]
        self.fake.parse_json=json.loads
        with patch.object(self.module,'own_employee',return_value=Obj(name='EMP-SELF')), patch.object(self.module,'make_plan',return_value={'parts':[{'days':1}]}):
            with self.assertRaisesRegex(ValueError,'calculation changed'):
                self.module.apply('Emergency Leave','2026-11-09','2026-11-10','a'*32,'[]')

if __name__=='__main__':unittest.main()
