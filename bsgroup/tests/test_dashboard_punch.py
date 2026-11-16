import importlib.util
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

class PunchTests(unittest.TestCase):
    def setUp(self):
        self.saved=[]
        self.fake=types.ModuleType('frappe')
        self.fake.whitelist=lambda **kw:lambda f:f
        self.fake.PermissionError=PermissionError
        self.fake.throw=lambda message,*args:(_ for _ in ()).throw(ValueError(message))
        self.fake.db=types.SimpleNamespace(sql=lambda *a:None)
        utils=types.ModuleType('frappe.utils')
        utils.now_datetime=lambda:'SERVER-NOW'
        utils.cint=int
        utils.get_datetime=lambda value: datetime.fromisoformat(value) if isinstance(value,str) else value
        place=types.ModuleType('bsgroup.attendance_place')
        place.describe_location=lambda *args:None
        self.modules=patch.dict(sys.modules,{'frappe':self.fake,'frappe.utils':utils,'bsgroup.attendance_place':place})
        self.modules.start()
        spec=importlib.util.spec_from_file_location('dashboard_punch_test',Path(__file__).resolve().parents[1]/'dashboard_punch.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.m.employee=lambda:'OWN-EMPLOYEE'
        self.real_context=self.m.context
        self.state=dict(allowed=True,last_name='',last_type=None,location_required=False,can_check_in=True,can_check_out=False)
        self.m.context=lambda:self.state
        def document(values):
            self.saved.append(values)
            return types.SimpleNamespace(name='CHECKIN',log_type=values['log_type'],time=values['time'],insert=lambda:None)
        self.fake.get_doc=document
    def tearDown(self):self.modules.stop()
    def test_own_employee_and_server_time(self):
        self.m.punch('IN')
        self.assertEqual(self.saved[0]['employee'],'OWN-EMPLOYEE')
        self.assertEqual(self.saved[0]['time'],'SERVER-NOW')
    def test_stale_or_duplicate_punch_rejected(self):
        self.state.update(last_name='LATEST',last_type='IN',can_check_in=False,can_check_out=True)
        with self.assertRaises(ValueError):self.m.punch('OUT','OLD')
        with self.assertRaises(ValueError):self.m.punch('IN','LATEST')
        self.assertEqual(self.saved,[])
    def test_out_requires_in(self):
        with self.assertRaises(ValueError):self.m.punch('OUT')
    def test_permissions_and_location_preserved(self):
        self.state['allowed']=False
        with self.assertRaises(ValueError):self.m.punch('IN')
        self.state.update(allowed=True,location_required=True)
        with self.assertRaises(ValueError):self.m.punch('IN')
        with self.assertRaises(ValueError):self.m.punch('IN',latitude='nan',longitude=55)
        self.m.punch('IN',latitude=25,longitude=55)
        self.assertEqual(self.saved[0]['latitude'],25)
    def test_insert_errors_are_not_bypassed(self):
        def doc(values):
            def insert():raise PermissionError('Native permission denied')
            return types.SimpleNamespace(insert=insert)
        self.fake.get_doc=doc
        with self.assertRaises(PermissionError):self.m.punch('IN')

    def test_new_shift_in_inserts_only_one_in_and_keeps_prior_record(self):
        self.state.update(last_name='OLD-IN',last_type='IN',can_check_in=True,can_check_out=False)
        with self.assertRaises(ValueError):self.m.punch('OUT','OLD-IN')
        self.m.punch('IN','OLD-IN')
        self.assertEqual(len(self.saved),1)
        self.assertEqual(self.saved[0]['log_type'],'IN')
        self.assertEqual(self.state['last_name'],'OLD-IN')

    def test_shift_boundaries(self):
        module=types.ModuleType('hrms.hr.doctype.shift_assignment.shift_assignment')
        dt=datetime.fromisoformat
        def window(start,end):return dict(actual_start=dt(start),actual_end=dt(end))
        cases=[
            ('old day','2026-11-13T09:00:00','2026-11-16T09:00:00',window('2026-11-16T08:00:00','2026-11-16T23:00:00'),{},True),
            ('same shift','2026-11-16T08:15:00','2026-11-16T09:00:00',window('2026-11-16T08:00:00','2026-11-16T23:00:00'),{},False),
            ('overnight','2026-11-15T22:00:00','2026-11-16T02:00:00',window('2026-11-15T21:00:00','2026-11-16T07:00:00'),{},False),
            ('next night','2026-11-15T22:00:00','2026-11-16T22:00:00',window('2026-11-16T21:00:00','2026-11-17T07:00:00'),{},True),
            ('second shift same day','2026-11-16T07:00:00','2026-11-16T16:00:00',window('2026-11-16T15:00:00','2026-11-16T23:00:00'),{},True),
            ('off shift next day','2026-11-15T09:00:00','2026-11-16T07:00:00',{},window('2026-11-15T08:00:00','2026-11-15T23:00:00'),True),
            ('overnight fallback','2026-11-15T22:00:00','2026-11-16T02:00:00',{},window('2026-11-15T21:00:00','2026-11-16T07:00:00'),False),
            ('unassigned same day','2026-11-16T08:00:00','2026-11-16T09:00:00',{},{},False),
            ('unassigned next day','2026-11-15T08:00:00','2026-11-16T09:00:00',{},{},True),
        ]
        with patch.dict(sys.modules,{'hrms.hr.doctype.shift_assignment.shift_assignment':module}):
            for label,stamp,now,current,previous,expected in cases:
                with self.subTest(label=label):
                    module.get_actual_start_end_datetime_of_shift=lambda emp,t,**kw:current if t==dt(now) else previous
                    row=types.SimpleNamespace(log_type='IN',time=stamp)
                    self.assertEqual(self.m.previous_shift_open('OWN-EMPLOYEE',row,dt(now)),expected)
                    self.assertEqual(row.time,stamp)
            self.assertFalse(self.m.previous_shift_open('OWN-EMPLOYEE',None,dt(now)))
            self.assertFalse(self.m.previous_shift_open('OWN-EMPLOYEE',types.SimpleNamespace(log_type='OUT'),dt(now)))

    def test_context_and_submission_new_shift_then_duplicate(self):
        row=types.SimpleNamespace(name='OLD',log_type='IN',time='2026-11-13 09:00:00',latitude=None,longitude=None)
        self.m.context=self.real_context
        self.m.latest=lambda emp:row
        self.m.previous_shift_open=lambda emp,record,now:record.name=='OLD'
        self.fake.has_permission=lambda *args:True
        self.fake.db.get_single_value=lambda doctype,field:field=='allow_employee_checkin_from_mobile_app'
        state=self.m.context()
        self.assertTrue(state['can_check_in'])
        self.assertFalse(state['can_check_out'])
        self.assertTrue(state['previous_checkout_missing'])
        self.m.punch('IN','OLD')
        self.assertEqual([d['log_type'] for d in self.saved],['IN'])
        row=types.SimpleNamespace(name='NEW',log_type='IN',time='SERVER-NOW',latitude=None,longitude=None)
        state=self.m.context()
        self.assertFalse(state['can_check_in'])
        self.assertTrue(state['can_check_out'])
        with self.assertRaises(ValueError):self.m.punch('IN','OLD')
        with self.assertRaises(ValueError):self.m.punch('IN','NEW')
        self.assertEqual(len(self.saved),1)

if __name__=='__main__':unittest.main()
