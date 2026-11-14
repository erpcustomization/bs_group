"""Exercise the real handover validation up to the source-PO boundary."""
import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

class ReachedPO(Exception): pass

class WarehouseTests(unittest.TestCase):
    def setUp(self):
        source=Path(__file__).resolve().parents[1]/'bsgroup/dcs/procurement.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='send_to_procurement')
        fn.decorator_list=[]
        def reject(message): raise ValueError(message)
        self.po=Mock(side_effect=ReachedPO)
        self.env=dict(frappe=SimpleNamespace(db=SimpleNamespace(get_value=Mock(return_value=None)),throw=reject),
            buying=SimpleNamespace(MR='Material Request'),source_documents=lambda *a,**kw:(SimpleNamespace(name='Q'),SimpleNamespace(company='AE')),
            handover_key=lambda s:'key',source_items=lambda s:[{'is_stock_item':1}],
            getdate=date.fromisoformat,nowdate=lambda:'2026-11-14',handover_warehouses=lambda c:['Stores - AE'],
            po_file=self.po,_=lambda s:s)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),self.env)
        self.send=self.env['send_to_procurement']

    def test_stock_handover_accepts_no_warehouse(self):
        with self.assertRaises(ReachedPO): self.send('Q','2026-11-15')
        self.po.assert_called_once()

    def test_explicit_warehouse_still_validated(self):
        with self.assertRaisesRegex(ValueError,'enabled warehouse'): self.send('Q','2026-11-15','Other Company')
        self.po.assert_not_called()
        with self.assertRaises(ReachedPO): self.send('Q','2026-11-15','Stores - AE')

    def test_required_date_still_enforced(self):
        for day in (None,'2026-11-13'):
            with self.assertRaisesRegex(ValueError,'required-by'): self.send('Q',day)
        self.po.assert_not_called()

if __name__=='__main__': unittest.main()
