import importlib.util
import sys
import types
import unittest
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
        self.modules=patch.dict(sys.modules,{'frappe':self.fake,'frappe.utils':utils})
        self.modules.start()
        spec=importlib.util.spec_from_file_location('dashboard_punch_test',Path(__file__).resolve().parents[1]/'dashboard_punch.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
        self.m.employee=lambda:'OWN-EMPLOYEE'
        self.state=dict(allowed=True,last_name='',last_type=None,location_required=False)
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
        self.state.update(last_name='LATEST',last_type='IN')
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

if __name__=='__main__':unittest.main()
