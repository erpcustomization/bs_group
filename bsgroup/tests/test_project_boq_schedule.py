import copy
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
    def append(self, field, row):
        self.setdefault(field, []).append(Doc(row))


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        f = types.ModuleType('frappe'); f._ = lambda s:s; f.whitelist = lambda **kw:lambda fn:fn
        f.throw = lambda s:(_ for _ in ()).throw(ValueError(s))
        f.get_meta = Mock(return_value=Doc(has_field=lambda field:True,get_field=lambda field:None))
        f.db = Doc(exists=Mock(return_value=True)); f.reload_doc=Mock();f.clear_cache=Mock();f.only_for=Mock()
        utils = types.ModuleType('frappe.utils');utils.getdate=lambda value:value
        utils.strip_html=lambda value:re.sub('<[^>]*>','',value)
        custom = types.ModuleType('frappe.custom.doctype.custom_field.custom_field');custom.create_custom_fields=Mock()
        self.patch = patch.dict(sys.modules,{'frappe':f,'frappe.utils':utils,'frappe.custom.doctype.custom_field.custom_field':custom});self.patch.start()
        spec=importlib.util.spec_from_file_location('schedule_test',Path(__file__).resolve().parents[1]/'project_boq_schedule.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m);self.f=f;self.custom=custom
        self.row=Doc(name='ROW-1',idx=1,source_quotation='Q1',source_item='QI1',item_code='I',item_name='Camera',description='Camera setup',qty=2,uom='Nos',start_date=None,end_date=None)
        self.old=Doc({self.m.FIELD:[copy.deepcopy(self.row)]})
        self.doc=Doc({self.m.FIELD:[self.row]},get_doc_before_save=lambda:self.old)

    def tearDown(self):self.patch.stop()

    def test_dates_independent_optional_and_saved_on_original_row(self):
        for start,end in [(None,None),('2026-11-09',None),(None,'2026-11-10'),('2026-11-09','2026-11-09'),('2026-11-09','2026-11-12')]:
            self.row.start_date=start;self.row.end_date=end;self.m.validate(self.doc)

    def test_invalid_date_order_rejected_even_during_import(self):
        self.row.start_date='2026-11-12';self.row.end_date='2026-11-09'
        with self.assertRaisesRegex(ValueError,'row 1'):self.m.validate(self.doc)
        with self.m.importing(),self.assertRaises(ValueError):self.m.validate(self.doc)

    def test_source_edit_delete_and_forged_rows_rejected(self):
        self.row.qty=9
        with self.assertRaises(ValueError):self.m.validate(self.doc)
        self.doc[self.m.FIELD]=[]
        with self.assertRaises(ValueError):self.m.validate(self.doc)
        self.doc[self.m.FIELD]=[self.row];self.old[self.m.FIELD]=[]
        with self.assertRaises(ValueError):self.m.validate(self.doc)

    def test_import_copies_every_line_without_prices_and_is_idempotent(self):
        line=Doc(name='QI1',item_code='I',item_name='Camera',description='<b>Camera setup</b>',qty=2,uom='Nos',rate=1234,amount=2468)
        q=types.SimpleNamespace(name='Q1',items=[line,Doc(line,name='QI2')]);project=Doc()
        self.m.append_quotation(project,q)
        self.assertEqual(len(project[self.m.FIELD]),2)
        self.assertEqual(project[self.m.FIELD][0].description,'Camera setup')
        self.assertNotIn('rate',project[self.m.FIELD][0]);self.assertNotIn('amount',project[self.m.FIELD][0])
        project[self.m.FIELD][0].start_date='2026-11-09'
        self.m.append_quotation(project,q)
        self.assertEqual(len(project[self.m.FIELD]),2)
        self.assertEqual(project[self.m.FIELD][0].start_date,'2026-11-09')

    def test_import_scope_resets_after_failure(self):
        self.old[self.m.FIELD]=[]
        with self.assertRaises(RuntimeError):
            with self.m.importing():
                self.m.validate(self.doc)
                raise RuntimeError()
        with self.assertRaises(ValueError):self.m.validate(self.doc)

    def test_setup_requires_system_manager_and_does_not_rewrite_existing_field(self):
        self.f.only_for.side_effect=PermissionError()
        with self.assertRaises(PermissionError):self.m.setup()
        self.f.reload_doc.assert_not_called()
        self.f.only_for.side_effect=None
        self.f.get_meta.return_value.get_field=lambda name:Doc(fieldtype='Table',options=self.m.CHILD)
        self.m.setup();self.custom.create_custom_fields.assert_not_called()

    def test_schema_exposes_dates_without_prices_or_new_roles(self):
        path=Path(__file__).resolve().parents[1]/'bs_group/doctype/bs_project_boq_line/bs_project_boq_line.json'
        schema=json.loads(path.read_text());fields={r['fieldname']:r for r in schema['fields']}
        self.assertEqual(schema['istable'],1);self.assertFalse(schema['permissions'])
        self.assertEqual({key for key,row in fields.items() if not row.get('read_only')},{'start_date','end_date'})
        self.assertFalse({'rate','amount','cost_rate','margin'} & fields.keys())


if __name__=='__main__':unittest.main()
