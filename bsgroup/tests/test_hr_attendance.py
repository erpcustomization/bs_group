import importlib.util
import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, patch


class Row(dict):
    __getattr__ = dict.get


class HRCalendarTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.whitelist = lambda **kw: lambda f: f
        self.f.PermissionError = PermissionError
        self.f.throw = lambda message, exc=ValueError: (_ for _ in ()).throw(exc(message))
        self.f.has_permission = Mock(return_value=True)
        self.f.get_roles = lambda: ['System Manager']
        self.f.get_list = Mock(return_value=[])
        self.f.db = types.SimpleNamespace(exists=Mock(return_value=False), get_value=Mock())
        self.employee = Mock(company='UAE')
        self.request = Mock(employee='EMP-1', company='UAE')
        self.doc = Mock(docstatus=0)
        self.doc.name = 'ATT-1'
        self.f.get_doc = Mock(side_effect=lambda dt, *a: self.doc if isinstance(dt, dict) else self.employee if dt=='Employee' else self.request)
        utils = types.ModuleType('frappe.utils')
        utils.nowdate = lambda: '2026-11-07'
        utils.escape_html = lambda x: x
        management = types.ModuleType('bsgroup.hr_management')
        management._guard = Mock()
        self.guard = management._guard
        self.patch = patch.dict(sys.modules, {'frappe':self.f,'frappe.utils':utils,'bsgroup.hr_management':management})
        self.patch.start()
        spec = importlib.util.spec_from_file_location('calendar_test',Path(__file__).resolve().parents[1]/'hr_attendance.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        self.patch.stop()

    def record(self, **changes):
        args=dict(employee='EMP-1',attendance_date='2026-11-06',status='Present',employee_request='REQ-1',reason='Employee reported missed punch; verified by HR')
        args.update(changes)
        return self.m.record_manual(**args)

    def test_leap_month_and_year_boundary(self):
        self.assertEqual(self.m.month_bounds('2024-02'),(date(2024,2,1),date(2024,3,1)))
        self.assertEqual(self.m.month_bounds('2026-12'),(date(2026,12,1),date(2027,1,1)))
        with self.assertRaises(ValueError): self.m.month_bounds('2026-13')

    def test_calendar_keeps_all_punches_and_does_not_turn_manual_present_into_punch(self):
        result=self.m.calendar_days(date(2026,11,1),date(2026,12,1),
            [dict(name='out',time='2026-11-02 18:00:00',log_type='OUT'),dict(name='in',time='2026-11-02 09:00:00',log_type='IN')],[],
            [dict(name='att',attendance_date='2026-11-03',status='Present',docstatus=1)],[],'2026-11-07')
        self.assertEqual(len(result),30)
        self.assertEqual([p['name'] for p in result[1]['punches']],['in','out'])
        self.assertEqual(result[2]['punches'],[])
        self.assertEqual(result[2]['attendance'][0]['status'],'Present')
        self.assertTrue(result[7]['future'])

    def test_leave_requires_submission_and_approval_and_handles_split_half_day(self):
        leaves=[dict(name='L1',from_date='2026-10-31',to_date='2026-11-02',docstatus=1,status='Approved',half_day=1,half_day_date='2026-11-02'),
                dict(name='L2',from_date='2026-11-03',to_date='2026-11-03',docstatus=0,status='Approved')]
        days=self.m.calendar_days(date(2026,11,1),date(2026,12,1),[],leaves,[],[],'2026-11-07')
        self.assertTrue(days[0]['leaves'][0]['approved'])
        self.assertFalse(days[0]['leaves'][0]['is_half_day'])
        self.assertTrue(days[1]['leaves'][0]['is_half_day'])
        self.assertFalse(days[2]['leaves'][0]['approved'])

    def test_guard_precedes_reads_and_writes(self):
        self.guard.side_effect=PermissionError()
        with self.assertRaises(PermissionError): self.m.month_view('2026-11')
        with self.assertRaises(PermissionError): self.record()
        self.f.get_list.assert_not_called()
        self.f.get_doc.assert_not_called()

    def test_out_of_scope_employee_rejected_before_attendance_queries(self):
        self.f.get_list.return_value=[Row(name='EMP-2')]
        with self.assertRaises(PermissionError): self.m.month_view('2026-11','EMP-1')
        self.assertEqual(self.f.get_list.call_count,1)
        self.f.get_doc.assert_not_called()

    def test_restricted_dataset_explicit_and_no_permission_bypass(self):
        self.f.get_list.side_effect=lambda dt,**kw: [Row(name='EMP-1')] if dt=='Employee' else []
        self.f.has_permission.side_effect=lambda dt,*a: dt!='Employee Checkin'
        result=self.m.month_view('2026-11','EMP-1')
        self.assertEqual(result['restricted'],['Employee Checkin'])
        for call in self.f.get_list.call_args_list:
            self.assertNotIn('ignore_permissions',call.kwargs)
            self.assertNotEqual(call.args[0],'Employee Checkin')

    def test_manual_requires_request_reason_past_or_today_and_allowed_status(self):
        for changes in ({'employee_request':''},{'reason':' '},{'attendance_date':'2026-11-08'},{'status':'On Leave'}):
            with self.assertRaises(ValueError): self.record(**changes)
        self.doc.insert.assert_not_called()

    def test_cross_employee_request_denied(self):
        self.request.employee='EMP-2'
        with self.assertRaises(ValueError): self.record()
        self.doc.insert.assert_not_called()

    def test_existing_attendance_and_approved_leave_cannot_be_overwritten(self):
        for dt in ('Attendance','Leave Application'):
            self.f.db.exists.side_effect=lambda name,filters: name==dt
            with self.assertRaises(ValueError): self.record()
        self.doc.insert.assert_not_called()

    def test_manual_only_creates_draft_with_audit_and_native_permissions(self):
        self.assertEqual(self.record(),dict(name='ATT-1',docstatus=0))
        self.doc.insert.assert_called_once_with()
        self.doc.submit.assert_not_called()
        self.employee.check_permission.assert_called_once_with('read')
        self.request.check_permission.assert_called_once_with('read')
        self.assertIn('REQ-1',self.doc.add_comment.call_args.args[1])
        self.assertIn('verified by HR',self.doc.add_comment.call_args.args[1])
        self.assertEqual(self.f.get_doc.call_args.args[0]['doctype'],'Attendance')

    def test_targeted_repair_rejects_non_admin_before_mutation(self):
        self.f.only_for=Mock(side_effect=PermissionError())
        with self.assertRaises(PermissionError): self.m.repair_mithun_november()
        self.f.get_doc.assert_not_called()

    def test_repair_is_scoped_to_reviewed_original_pairs(self):
        self.assertEqual([x[0] for x in self.m.MITHUN_REPAIR],['2026-11-06','2026-11-07'])
        self.assertEqual([x[1] for x in self.m.MITHUN_REPAIR],['HR-ATT-2026-03642','HR-ATT-2026-03658'])
        self.assertTrue(all([p[1] for p in x[2]]==['IN','OUT'] for x in self.m.MITHUN_REPAIR))

    def test_repair_uses_native_row_calculator_and_preserves_original_punches(self):
        utils=sys.modules['frappe.utils']
        utils.getdate=lambda v: date.fromisoformat(str(v)[:10])
        utils.get_datetime=lambda v: datetime.fromisoformat(str(v))
        self.f.only_for=Mock()
        self.f._dict=Row
        shift=Mock(allow_check_out_after_shift_end_time=360,working_hours_threshold_for_absent=2,working_hours_threshold_for_half_day=8)
        shift.name='General - UAE'
        def calculate(rows,*thresholds):
            # HRMS requires both dictionary indexing and attribute access, unlike Document.
            self.assertEqual([r['log_type'] for r in rows],['IN','OUT'])
            hours=round((rows[1].time-rows[0].time).total_seconds()/3600,2)
            return ('Present',hours,False,False,rows[0].time,rows[1].time)
        shift.get_attendance.side_effect=calculate
        objects={('Shift Type',shift.name):shift}
        logs=[]
        for day,old_name,punches in self.m.MITHUN_REPAIR:
            old=Mock(docstatus=1,employee='1047',attendance_date=day,status='Absent',shift=shift.name,company='UAE')
            old.name=old_name
            objects[('Attendance',old_name)]=old
            for name,kind,stamp in punches:
                data=Row(name=name,employee='1047',log_type=kind,time=datetime.fromisoformat(stamp))
                log=Mock(**data,skip_auto_attendance=0,attendance=old_name if kind=='IN' else None,offshift=0,shift=shift.name)
                log.name=name
                log.as_dict.return_value=data
                objects[('Employee Checkin',name)]=log
                logs.append(log)
        created=[]
        def get_doc(dt,*args,**kwargs):
            if not isinstance(dt,dict):return objects[(dt,args[0])]
            d=Mock(**dt);d.name='NEW-'+dt['attendance_date'];created.append(d);return d
        self.f.get_doc.side_effect=get_doc
        self.f.get_list.side_effect=[[x[0] for x in pair[2]] for pair in self.m.MITHUN_REPAIR]
        native=types.ModuleType('hrms.hr.doctype.employee_checkin.employee_checkin')
        native.update_attendance_in_checkins=Mock()
        with patch.dict(sys.modules,{'hrms.hr.doctype.employee_checkin.employee_checkin':native}):
            results=self.m.repair_mithun_november()
        self.assertEqual([r['working_hours'] for r in results],[12.27,10.38])
        self.assertEqual(len(created),2)
        for d in created:
            d.insert.assert_called_once_with();d.submit.assert_called_once_with()
        self.assertEqual(native.update_attendance_in_checkins.call_count,2)
        for log in logs:
            self.assertEqual(log.time,log.as_dict.return_value.time)
            log.save.assert_called_once_with()


if __name__=='__main__': unittest.main()
