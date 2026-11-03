"""Exercise production link-back checks without changing records."""
import ast
from pathlib import Path
from unittest.mock import MagicMock

tree = ast.parse((Path(__file__).resolve().parents[1]/'bsgroup/presales_dcs_handoff.py').read_text())
fn = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='link_back')
for case in ('new_link','repeat','conflict','wrong_request','wrong_deal','cancelled','superseded','unsubmitted'):
    f = MagicMock()
    f.throw.side_effect = ValueError
    f.db.get_value.return_value = 'DCS1' if case=='repeat' else 'DCS2' if case=='conflict' else None
    request = MagicMock(); request.name='PR1'; request.docstatus=0 if case=='unsubmitted' else 1
    sheet = MagicMock(); sheet.name='DCS1'; sheet.docstatus=2 if case=='cancelled' else 0
    sheet.presales_request='OTHER' if case=='wrong_request' else 'PR1'
    sheet.custom_record_authority='Superseded' if case=='superseded' else ''
    ns={'frappe':f,'_same_deal':lambda s,p:case!='wrong_deal'}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),'handoff.py','exec'),ns)
    try:
        ns['link_back'](request,sheet)
        assert case in ('new_link','repeat')
        if case=='new_link': request.db_set.assert_called_once_with('custom_deal_cost_sheet','DCS1')
        else: request.db_set.assert_not_called()
    except ValueError:
        assert case not in ('new_link','repeat')
        request.db_set.assert_not_called()
    print('PASS',case)
