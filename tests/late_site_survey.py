"""Late intake must preserve costing, enforce access and be retry-safe."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import Mock

class Row(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__

class LateSurveyTests(TestCase):
    def setUp(self):
        self.opp = Row(name='OPP-TEST', docstatus=0, status='Presales Request',
            custom_business_type='Service', custom_presales_required=1,
            check_permission=Mock())
        self.pre = Row(name='PR-TEST', status='Costing in Progress', opportunity='OPP-TEST',
            custom_site_survey_request='SSR-TEST', meta=Row(get_label=lambda x:x))
        for field in ('presales_owner','due_date','priority','solution_summary','scope_details'):
            self.pre[field] = 'existing'
        self.survey = Row(name='SSR-TEST', flags=Row(), insert=Mock())
        self.writes=[]
        def get_doc(dt, name=None, **kw):
            if isinstance(dt, dict):
                self.survey.update(dt)
                return self.survey
            return self.opp if dt=='Opportunity' else self.pre
        def value(dt, *args, **kw):
            return 'PR-TEST' if dt=='Presales Request' else None
        def fail(message):
            raise ValueError(message)
        self.frappe=SimpleNamespace(get_doc=Mock(side_effect=get_doc),
            db=SimpleNamespace(get_value=Mock(side_effect=value),set_value=Mock()),
            get_all=Mock(return_value=[]),session=Row(user='sales@test'),throw=fail)
        tree=ast.parse((Path(__file__).resolve().parents[1]/'bsgroup/site_survey.py').read_text())
        tree.body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
        for n in tree.body:
            if isinstance(n,ast.FunctionDef): n.decorator_list=[]
        self.env={'frappe':self.frappe,'_':lambda x:x,'cint':lambda x:int(x or 0),'nowdate':lambda:'2026-11-16'}
        exec(compile(tree,'site_survey','exec'),self.env)
        self.args=dict(opportunity='OPP-TEST',team='ELV',instructions='Inspect network',
            location='Test site',contact_name='Test contact',contact_phone='000')

    def test_late_request_preserves_existing_work_and_qualification(self):
        result=self.env['request_supplementary_survey'](**self.args)
        self.assertTrue(result['created'])
        self.frappe.get_doc.assert_any_call('Opportunity','OPP-TEST',for_update=True)
        self.opp.check_permission.assert_called_once_with('write')
        self.survey.insert.assert_called_once_with(ignore_permissions=True)
        self.assertEqual(self.survey.presales_request,'PR-TEST')
        self.assertEqual(self.survey.supplementary_survey,1)
        self.assertEqual(self.pre.status,'Costing in Progress')
        self.assertEqual([c.args[2] for c in self.frappe.db.set_value.call_args_list],
            ['custom_site_survey_request','custom_site_survey_request'])

    def test_retry_returns_existing_request_without_writes(self):
        self.frappe.db.get_value.return_value='SSR-EXISTING'
        self.frappe.db.get_value.side_effect=None
        for _ in range(3):
            self.assertEqual(self.env['request_supplementary_survey'](**self.args),
                {'name':'SSR-EXISTING','created':False})
        self.survey.insert.assert_not_called()
        self.frappe.db.set_value.assert_not_called()

    def test_permission_denial_precedes_read_or_write(self):
        self.opp.check_permission.side_effect=PermissionError
        with self.assertRaises(PermissionError): self.env['request_supplementary_survey'](**self.args)
        self.frappe.db.get_value.assert_not_called()
        self.frappe.db.set_value.assert_not_called()

    def test_invalid_and_closed_requests_rejected(self):
        for key,value in [('team','bad'),('instructions',' '),('contact_phone','')]:
            with self.assertRaises(ValueError): self.env['request_supplementary_survey'](**{**self.args,key:value})
        self.opp.status='Closed'
        with self.assertRaises(ValueError): self.env['request_supplementary_survey'](**self.args)
        self.survey.insert.assert_not_called()

    def test_late_survey_does_not_block_presales_but_original_survey_does(self):
        row=Row(opportunity='OPP-TEST',status='Requested',supplementary_survey=1)
        self.frappe.db.get_value.side_effect=None
        self.frappe.db.get_value.return_value=row
        self.env['validate_presales'](self.pre)
        row.supplementary_survey=0
        with self.assertRaisesRegex(ValueError,'awaiting site survey'):
            self.env['validate_presales'](self.pre)

    def test_late_completion_never_creates_costing(self):
        self.env['create_costing_after_survey'](Row(status='Completed',presales_request=None,supplementary_survey=1))
        self.frappe.get_doc.assert_not_called()

    def test_details_authorize_source_before_reading_survey(self):
        self.env['linked_survey_details']('Opportunity','OPP-TEST')
        self.opp.check_permission.assert_called_once_with('read')
        self.assertEqual(self.frappe.get_all.call_args.kwargs['filters'],{'opportunity':'OPP-TEST'})
        self.opp.check_permission.side_effect=PermissionError
        self.frappe.get_all.reset_mock()
        with self.assertRaises(PermissionError): self.env['linked_survey_details']('Opportunity','OPP-TEST')
        self.frappe.get_all.assert_not_called()

if __name__=='__main__': main()
