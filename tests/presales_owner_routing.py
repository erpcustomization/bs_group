"""Run with Python; exercises production routing without writing records."""
import ast
from pathlib import Path
from unittest.mock import MagicMock

tree = ast.parse((Path(__file__).resolve().parents[1] / 'bsgroup/site_survey.py').read_text())
functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
             ('create_requests', 'default_presales_owner', 'survey_selected')]
for creator in ('Administrator', 'paul@bitssecureit.com', 'priya@bitssecureit.com'):
    for existing_owner in (None, '', 'another-presales@example.com'):
        frappe = MagicMock()
        frappe.session.user = creator
        frappe.conf.get.return_value = None
        frappe.get_roles.return_value = ['BS Scoped Presales']
        def value(dt, *args, **kwargs):
            return {'User': 1, 'Presales Request': 'PR-EXISTING' if existing_owner is not None else None}.get(dt)
        frappe.db.get_value.side_effect = value
        pre = MagicMock()
        pre.presales_owner = existing_owner
        pre.docstatus = 0
        frappe.get_doc.return_value = pre
        doc = MagicMock()
        doc.get.side_effect = lambda field: 1 if field == 'custom_presales_required' else None
        ns = dict(frappe=frappe, cint=lambda v: int(v or 0), nowdate=lambda: '2026-11-02',
                  FLAGS=('custom_elv_site_survey_required','custom_technical_site_survey_required'))
        exec(compile(ast.Module(body=functions,type_ignores=[]), 'site_survey.py', 'exec'), ns)
        ns['create_requests'](doc)
        if existing_owner is None:
            assert frappe.get_doc.call_args.args[0]['presales_owner'] == 'sanisha@bitssecureit.com'
            pre.save.assert_called_once_with(ignore_permissions=True)
        elif existing_owner == '':
            pre.db_set.assert_called_once_with('presales_owner','sanisha@bitssecureit.com')
        else:
            pre.db_set.assert_not_called()
        frappe.db.get_value.side_effect = None
        frappe.db.get_value.return_value = 0
        assert ns['default_presales_owner']() is None
print('PASS: admin/sales routing, unassigned repair, existing assignee preserved, disabled recipient excluded')
