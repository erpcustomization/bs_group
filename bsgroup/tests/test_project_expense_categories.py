import importlib.util, sys, types, unittest
from pathlib import Path
from unittest.mock import patch
class Row(dict):
    __getattr__=dict.get
class Tests(unittest.TestCase):
    def setUp(self):
        f=types.ModuleType('frappe');f._=lambda x:x;f.throw=lambda msg:(_ for _ in ()).throw(ValueError(msg))
        self.p=patch.dict(sys.modules,{'frappe':f});self.p.start()
        spec=importlib.util.spec_from_file_location('categories',Path(__file__).resolve().parents[1]/'project_expense_categories.py')
        self.m=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.m)
    def tearDown(self):self.p.stop()
    def doc(self,category=None,expense_type='Travel',old=None):
        return Row(project='P',expenses=[Row(name='ROW',idx=1,custom_project_expense_category=category,expense_type=expense_type)],get_doc_before_save=lambda:old)
    def test_categories_match_existing_types(self):
        for category,expense_type in self.m.CATEGORIES.items():self.m.validate(self.doc(category,expense_type))
    def test_missing_category_rejected(self):
        with self.assertRaisesRegex(ValueError,'Choose'):self.m.validate(self.doc())
    def test_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'matching'):self.m.validate(self.doc('Food','Travel'))
    def test_unknown_category_rejected(self):
        with self.assertRaisesRegex(ValueError,'Choose'):self.m.validate(self.doc('Unknown'))
    def test_historical_rows_preserved(self):
        old=Row(docstatus=0,expenses=[Row(name='ROW')]);self.m.validate(self.doc(old=old,expense_type='Medical'))
    def test_new_row_in_existing_claim_requires_category(self):
        old=Row(docstatus=0,expenses=[Row(name='OLD')])
        with self.assertRaisesRegex(ValueError,'Choose'):self.m.validate(self.doc(old=old))
    def test_submitted_history_preserved(self):self.m.validate(self.doc(old=Row(docstatus=1)))
    def test_nonproject_unchanged(self):self.m.validate(Row(project=None))
if __name__=='__main__':unittest.main()
