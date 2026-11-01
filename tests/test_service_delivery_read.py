"""Isolated permission and pagination regression tests (no live ERP writes)."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class PermissionDenied(Exception):
    pass


class Missing(Exception):
    pass


class TicketEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType('frappe')
        self.f.PermissionError = PermissionDenied
        self.f.DoesNotExistError = Missing
        self.f.session = types.SimpleNamespace(user='manager@example.com')
        self.f.whitelist = lambda **kw: lambda fn: fn
        self.f.throw = lambda msg, exc=ValueError: (_ for _ in ()).throw(exc(msg))
        self.f.get_meta = Mock(return_value=types.SimpleNamespace(has_field=lambda f: True, fields=[]))
        self.f.get_list = Mock(side_effect=lambda dt, **kw: [kw['filters']['name']] if isinstance(kw.get('filters'), dict) and 'name' in kw['filters'] else [])
        self.client = types.ModuleType('frappe.client')
        self.client.get = Mock(side_effect=lambda dt, name: {'name': name, 'doctype': dt})
        self.patcher = patch.dict(sys.modules, {'frappe': self.f, 'frappe.client': self.client})
        self.patcher.start()
        spec = importlib.util.spec_from_file_location('evidence_test_module', ROOT / 'bsgroup/api/service_delivery_read.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.patcher.stop()

    def test_guest_rejected_before_lookup(self):
        self.f.session.user = 'Guest'
        with self.assertRaises(PermissionDenied):
            self.module.ticket_context('1767')
        self.f.get_list.assert_not_called()

    def test_parent_list_permission_denial_blocks_all_evidence(self):
        self.f.get_list.return_value = []
        self.f.get_list.side_effect = None
        with self.assertRaises(PermissionDenied):
            self.module.ticket_context('1767')
        self.client.get.assert_not_called()

    def test_document_permission_denial_blocks_all_evidence(self):
        self.client.get.side_effect = PermissionDenied('denied')
        with self.assertRaises(PermissionDenied):
            self.module.ticket_context('1767')

    def test_section_permission_failure_explicit(self):
        self.f.get_list.side_effect = PermissionDenied('denied')
        result = self.module._section('Communication', {}, 0, 20)
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('records', result)

    def test_pagination_no_silent_truncation(self):
        def listing(dt, **kw):
            if 'name' in kw['filters']:
                return [kw['filters']['name']]
            return ['a', 'b', 'c']
        self.f.get_list.side_effect = listing
        result = self.module._section('Communication', {}, 0, 2)
        self.assertTrue(result['has_more'])
        self.assertEqual(result['next_start'], 2)
        self.assertEqual(len(result['records']), 2)

    def test_each_evidence_query_is_ticket_scoped(self):
        result = self.module.ticket_context('1767')
        calls = self.f.get_list.call_args_list
        for call in calls:
            dt = call.args[0]
            filters = call.kwargs['filters']
            if dt in ('Communication', 'Comment'):
                self.assertEqual(filters, {'reference_doctype': 'HD Ticket', 'reference_name': '1767'})
        self.assertEqual(result['sections']['sla']['status'], 'not_configured')

    def test_bad_pagination_rejected(self):
        for kwargs in ({'start': -1}, {'limit': 0}, {'limit': 101}):
            with self.assertRaises(ValueError):
                self.module.ticket_context('1767', **kwargs)

    def test_sla_permission_denial_not_hidden(self):
        def read(dt, name):
            if dt == 'HD Service Level Agreement':
                raise PermissionDenied('denied')
            return {'name': name, 'sla': 'Default'}
        self.client.get.side_effect = read
        result = self.module.ticket_context('1767')
        self.assertEqual(result['sections']['sla']['status'], 'unavailable')

    def test_server_script_parses_and_advertises_read_tool(self):
        source = (ROOT / 'docs/integrations/ai_aira_mcp_server_script.py').read_text()
        self.f.form_dict = {'method': 'tools/list', 'jsonrpc': '2.0', 'id': 1}
        self.f.response = {}
        import json
        exec(compile(source, 'mcp', 'exec'), {'frappe': self.f, 'json': json})
        result = json.loads(self.f.response['filecontent'])['result']
        tool = next(t for t in result['tools'] if t['name'] == 'get_ticket_context')
        self.assertTrue(tool['annotations']['readOnlyHint'])
        search = next(t for t in result['tools'] if t['name'] == 'search_records')
        self.assertIn('start', search['inputSchema']['properties'])
        self.assertIn('modified_after', search['inputSchema']['properties'])


if __name__ == '__main__':
    unittest.main()
