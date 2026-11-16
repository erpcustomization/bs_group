import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class Row(dict):
    __getattr__ = dict.get


class CategoryBackfillTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f._ = lambda text: text
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.local = Row(site='erp-om.k.frappe.cloud')
        self.f.db = Mock()
        self.f.db.exists.return_value = False
        self.f.get_meta = Mock(return_value=Row(has_field=lambda field: True))
        self.f.get_all = Mock(return_value=[])
        self.f.get_doc = Mock()
        self.f.clear_document_cache = Mock()
        custom = types.ModuleType('frappe.custom.doctype.custom_field.custom_field')
        custom.create_custom_fields = Mock()
        self.modules = patch.dict(sys.modules, {'frappe': self.f,
            'frappe.custom.doctype.custom_field.custom_field': custom})
        self.modules.start()
        spec = importlib.util.spec_from_file_location('bsgroup.project_modules', ROOT/'project_modules.py')
        self.pm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.pm)
        self.pm_patch = patch.dict(sys.modules, {'bsgroup.project_modules': self.pm})
        self.pm_patch.start()
        spec = importlib.util.spec_from_file_location('category_backfill_test', ROOT/'project_category_backfill.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        self.pm_patch.stop()
        self.modules.stop()

    def test_explicit_corrections_override_wrong_saved_category(self):
        for name, title, expected in [
            ('PROJ-2367','Amana AMC - ECS/NCS & ELV all sites - 2025-26',['elv']),
            ('PROJ-0157','Embassy of the Republic of Indonesia - IT Infrastructure AMC - 2025-26',['infra']),
        ]:
            self.assertEqual(self.m.proposed_categories(Row(name=name,project_name=title,custom_bs_3cx_projects=1)), (expected,''))

    def test_existing_choices_and_review_notes_are_preserved(self):
        self.assertEqual(self.m.proposed_categories(Row(project_name='ELV project', custom_bs_supply_projects=1,
            custom_bs_category_review_note='Existing note')), (None,None))

    def test_scope_and_unknowns_are_flagged(self):
        for title, expected in [('3CX AMC',['3cx']),('CCTV and Network',['elv','infra']),
                                ('Supply of laptops',['supply']),('NCS AMC',['elv']),('Dar Global AMC',['infra'])]:
            categories,note = self.m.proposed_categories(Row(project_name=title))
            self.assertEqual(categories,expected)
            self.assertIn('Needs category review',note)
        self.assertIn('provisional',self.m.proposed_categories(Row(project_name='Hasis AMC'))[1])

    def test_category_writes_only_and_append_only_audit(self):
        self.f.get_all.return_value=[Row(name='P1',project_name='Unknown',status='Completed')]
        self.m.execute()
        args,kwargs=self.f.db.set_value.call_args
        self.assertEqual(args[:2],('Project','P1'))
        self.assertEqual(set(args[2]),{v[1] for v in self.pm.MODULES.values()}|{self.m.REVIEW_FIELD})
        self.assertEqual(kwargs,{'update_modified':False})
        version=self.f.get_doc.call_args_list[0].args[0]
        self.assertEqual(version['doctype'],'Version')
        self.assertTrue(json.loads(version['data'])['changed'])
        self.assertEqual(self.f.get_doc.call_args_list[-1].args[0]['patch'],self.m.PATCH)
        self.f.get_doc.return_value.save.assert_not_called()

    def test_repeat_migration_does_not_reapply_or_overwrite_later_choices(self):
        self.f.db.exists.return_value=True
        self.m.execute()
        self.f.get_all.assert_not_called()
        self.f.db.set_value.assert_not_called()

    def test_other_sites_untouched(self):
        self.f.local.site='staging.example.com'
        self.m.execute()
        self.f.db.set_value.assert_not_called()
        self.f.get_all.assert_not_called()

    def test_review_flag_does_not_change_amc_partition(self):
        row=Row(project_name='Hasis AMC',custom_bs_infra_projects=1,custom_bs_category_review_note='Needs category review')
        result=self.pm.classify(row)
        self.assertTrue(result['is_amc'])
        self.assertTrue(result['review_required'])
        self.assertEqual(result['categories'],['infra'])


if __name__ == '__main__':
    unittest.main()
