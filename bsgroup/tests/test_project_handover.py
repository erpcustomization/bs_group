from contextlib import nullcontext
import importlib.util
import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Doc(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    def __getattribute__(self, key):
        if key == "items" and key in self: return self[key]
        return super().__getattribute__(key)
    def set(self, key, value): self[key] = value


class ProjectHandoverTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f._ = lambda value: value
        self.f.throw = lambda value, *args: (_ for _ in ()).throw(ValueError(value))
        self.f.PermissionError=ValueError
        self.f.session=Doc(user='sales@example.com')
        self.f.get_roles=Mock(return_value=['BS Scoped Sales'])
        self.f.get_meta = Mock(return_value=Doc(has_field=lambda field: True))
        self.old_project = Doc(name='PROJ-OLD', company='AE', status='Completed', custom_boq='<p>Existing scope</p>',
            custom_bs_infra_projects=1, check_permission=Mock(), save=Mock())
        self.project = Doc(name='PROJ-NEW', check_permission=Mock(), save=Mock())
        self.f.get_doc = Mock(return_value=self.old_project)
        self.f.new_doc = Mock(return_value=self.project)
        utils = types.ModuleType('frappe.utils')
        utils.getdate = lambda value: value
        utils.strip_html = lambda value: re.sub('<[^>]*>', '', value)
        modules = types.ModuleType('bsgroup.project_modules')
        modules.MODULES = {key: (key, 'custom_bs_'+key+'_projects') for key in ('supply','elv','infra','3cx')}
        schedule = types.ModuleType('bsgroup.project_boq_schedule')
        schedule.append_quotation = Mock(); schedule.importing = nullcontext
        roles_spec=importlib.util.spec_from_file_location('bsgroup.dcs.sales_handover_access',Path(__file__).resolve().parents[1]/'dcs/sales_handover_access.py')
        roles=importlib.util.module_from_spec(roles_spec);roles_spec.loader.exec_module(roles)
        self.p = patch.dict(sys.modules, {'frappe':self.f,'frappe.utils':utils,'bsgroup.project_modules':modules,'bsgroup.project_boq_schedule':schedule,'bsgroup.dcs.sales_handover_access':roles})
        self.p.start()
        spec = importlib.util.spec_from_file_location('handover_test',Path(__file__).resolve().parents[1]/'project_handover.py')
        self.m = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.m)
        self.q = Doc(name='Q-1', quotation_to='Customer', party_name='C-1', company='AE', custom_deal_cost_sheet='DCS-1',check_permission=Mock())
        self.q.items = [Doc(item_code='I-1',item_name='Camera',description='<b>Installation</b>',qty=2,uom='Nos',
            rate=1234,amount=2468,cost_rate=999,discount_amount=888)]
        self.sheet = Doc(name='DCS-1',project='PROJ-1', company='AE', subject='Security installation',check_permission=Mock())
        self.details = dict(project_type='Major Project', custom_project_manager='EMP-1',
            expected_start_date='2026-11-09', expected_end_date='2026-11-30',project_template='Template A')

    def tearDown(self): self.p.stop()

    def test_price_free_scope_allowlist_and_escaping(self):
        self.q.name = '<Q-1>'
        html = self.m.boq_html(self.q)
        for forbidden in ('1234','2468','999','888','<b>','<Q-1>'): self.assertNotIn(forbidden,html)
        for expected in ('&lt;Q-1&gt;','I-1','Camera','Installation','<td>2</td>','Nos'): self.assertIn(expected,html)

    def test_selection_validation_and_multiple_modules(self):
        self.assertEqual(self.m.selections('["supply","elv","supply"]'),['supply','elv'])
        for bad in (None,[],['bad'],{},'bad',[{}]):
            with self.assertRaises(ValueError): self.m.selections(bad)

    def test_legacy_project_is_not_reused_or_modified(self):
        self.assertEqual(self.m.save_project(self.q,self.sheet,['supply','elv'],self.details),'PROJ-NEW')
        self.project.check_permission.assert_called_once_with('create')
        self.assertNotIn('Existing scope',self.project.custom_boq)
        self.assertTrue(all(self.project['custom_bs_'+key+'_projects'] for key in ('supply','elv')))
        self.assertIsNone(self.project.custom_bs_infra_projects)
        self.f.get_doc.assert_not_called();self.old_project.save.assert_not_called()
        self.f.new_doc.assert_called_once_with('Project');self.project.save.assert_called_once_with()

    def test_permission_denial_cannot_save_or_classify(self):
        self.project.check_permission.side_effect = PermissionError()
        with self.assertRaises(PermissionError): self.m.save_project(self.q,self.sheet,['supply'],self.details)
        self.project.save.assert_not_called();self.assertIsNone(self.project.custom_bs_supply_projects)

    def test_sales_handover_only_creates_project_from_validated_source(self):
        self.project.check_permission.side_effect=PermissionError()
        with self.m.sales_handover(self.q,self.sheet):
            self.assertEqual(self.m.save_project(self.q,self.sheet,['supply'],self.details),'PROJ-NEW')
        self.project.save.assert_called_once_with(ignore_permissions=True)
        self.q.check_permission.assert_called_once_with('write')
        self.sheet.check_permission.assert_called_once_with('write')
        with self.assertRaises(PermissionError):self.m.save_project(self.q,self.sheet,['supply'],self.details)

    def test_handover_context_does_not_leak_after_failure_or_to_other_source(self):
        with self.assertRaises(RuntimeError):
            with self.m.sales_handover(self.q,self.sheet):
                self.assertTrue(self.m._scoped_handover(self.q,self.sheet))
                self.sheet.name='OTHER'
                self.assertFalse(self.m._scoped_handover(self.q,self.sheet))
                raise RuntimeError()
        self.assertIsNone(self.m._sales_handover.get())

    def test_handover_rejects_non_sales_unrelated_source_and_denied_documents(self):
        for role in ['Technical Engineer','BS Scoped Presales','System Manager','Employee','Purchase User']:
            self.f.get_roles.return_value=[role]
            with self.assertRaises(ValueError):
                with self.m.sales_handover(self.q,self.sheet):pass
        self.f.get_roles.return_value=['BS Scoped Sales']
        self.q.custom_deal_cost_sheet='OTHER'
        with self.assertRaises(ValueError):
            with self.m.sales_handover(self.q,self.sheet):pass
        self.q.custom_deal_cost_sheet=self.sheet.name
        self.sheet.check_permission.side_effect=PermissionError()
        with self.assertRaises(PermissionError):
            with self.m.sales_handover(self.q,self.sheet):pass
        self.project.save.assert_not_called()

    def test_legacy_project_does_not_waive_new_project_details(self):
        with self.m.sales_handover(self.q,self.sheet):
            with self.assertRaises(ValueError):self.m.save_project(self.q,self.sheet,['supply'])
        self.sheet.project=None
        with self.m.sales_handover(self.q,self.sheet):
            with self.assertRaises(ValueError):self.m.save_project(self.q,self.sheet,['supply'],{})
        self.project.save.assert_not_called()

    def test_legacy_project_never_becomes_the_destination_in_popup(self):
        for field,value in [('company','OM'),('status','Completed'),('status','Cancelled')]:
            self.old_project[field]=value
            context=self.m.context(self.q,self.sheet)
            self.assertIsNone(context['project']);self.assertEqual(context['project_modules'],[])
        self.f.get_doc.assert_not_called();self.old_project.save.assert_not_called()

    def test_quotation_subject_names_the_new_project(self):
        self.q.custom_subject='WiFi kitchen upgrade'
        self.m.save_project(self.q,self.sheet,['infra'],self.details)
        self.assertEqual(self.project.project_name,'WiFi kitchen upgrade - Q-1')
        self.assertEqual(self.m.context(self.q,self.sheet)['project_description'],'WiFi kitchen upgrade')

    def test_new_project_keeps_native_required_fields_template_and_permissions(self):
        self.sheet.project=None
        self.m.save_project(self.q,self.sheet,['supply','3cx'],json.dumps(self.details))
        self.project.check_permission.assert_called_once_with('create')
        self.assertEqual(self.project.project_template,'Template A')
        self.assertEqual(self.project.customer,'C-1')
        self.assertEqual(self.project.company,'AE')
        self.project.save.assert_called_once_with()

    def test_new_project_requires_complete_valid_dates(self):
        self.sheet.project=None
        with self.assertRaises(ValueError): self.m.save_project(self.q,self.sheet,['elv'],{})
        self.details['expected_end_date']='2026-11-01'
        with self.assertRaises(ValueError): self.m.save_project(self.q,self.sheet,['elv'],self.details)
        self.project.save.assert_not_called()

    def test_missing_installation_or_empty_boq_blocks_save(self):
        self.q.items=[]
        with self.assertRaises(ValueError): self.m.save_project(self.q,self.sheet,['elv'])
        self.f.get_meta.return_value=Doc(has_field=lambda field:False)
        with self.assertRaises(ValueError): self.m.save_project(self.q,self.sheet,['elv'])
        self.project.save.assert_not_called()


if __name__ == '__main__': unittest.main()
