"""Regression boundaries for stock-item draft handover validation."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class Doc(SimpleNamespace):
    def get(self, key):
        return getattr(self, key, None)


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'bsgroup/procurement_material_request.py'
        tree = ast.parse(path.read_text())
        tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
        self.utils = SimpleNamespace(**{n: Mock() for n in (
            'set_stock_levels', 'validate_item_and_get_basic_data',
            'validate_stock_item_warehouse', 'validate_end_of_life', 'validate_duplicate_items')})
        self.utils.validate_item_and_get_basic_data.return_value = Doc(is_stock_item=1, end_of_life=None, disabled=0)
        self.env = dict(utils=self.utils, BuyingController=Doc(validate=Mock()), validate_status=Mock())
        exec(compile(tree, str(path), 'exec'), self.env)
        self.row = Doc(item_code='STOCK-KIT', qty=1, warehouse=None)
        self.doc = Doc(docstatus=0, material_request_type='Purchase', custom_bsp_managed=1,
                       custom_bsp_source_snapshot='{}', custom_bsp_quotation='Q', custom_deal_cost_sheet='D',
                       items=[self.row])

    def test_source_draft_allows_missing_warehouse_and_keeps_item_checks(self):
        self.assertTrue(self.env['deferred_warehouse'](self.doc))
        self.env['validate_draft_items'](self.doc)
        self.utils.validate_stock_item_warehouse.assert_not_called()
        self.utils.validate_end_of_life.assert_called_once_with('STOCK-KIT', None, 0)
        self.utils.validate_duplicate_items.assert_called_once_with(self.doc)
        self.assertIsNone(self.row.warehouse)
        self.assertIsNone(self.row.get('delivered_by_supplier'))

    def test_submitted_and_non_purchase_never_defer(self):
        for status in (1, 2):
            self.doc.docstatus = status
            self.assertFalse(self.env['deferred_warehouse'](self.doc))
        self.doc.docstatus = 0
        self.doc.material_request_type = 'Material Transfer'
        self.assertFalse(self.env['deferred_warehouse'](self.doc))

    def test_ordinary_requests_never_defer(self):
        for key in ('custom_bsp_managed', 'custom_bsp_source_snapshot', 'custom_bsp_quotation', 'custom_deal_cost_sheet'):
            old = getattr(self.doc, key)
            setattr(self.doc, key, None)
            self.assertFalse(self.env['deferred_warehouse'](self.doc))
            setattr(self.doc, key, old)

    def test_supplied_warehouse_is_still_checked(self):
        self.row.warehouse = 'Stores - AE'
        self.env['validate_draft_items'](self.doc)
        self.utils.validate_stock_item_warehouse.assert_called_once()

    def test_disabled_item_still_blocks(self):
        self.utils.validate_end_of_life.side_effect = ValueError('disabled')
        with self.assertRaisesRegex(ValueError, 'disabled'):
            self.env['validate_draft_items'](self.doc)

    def test_native_validation_used_for_submission(self):
        native = Mock()
        class Base:
            def validate(self):
                native()
        class Request(self.env['SalesHandoverRequestMixin'], Base, Doc):
            pass
        request = Request(**vars(self.doc))
        request.docstatus = 1
        request.validate()
        native.assert_called_once()


if __name__ == '__main__':
    unittest.main()
