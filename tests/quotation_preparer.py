import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

ROOT = Path(__file__).parents[1]

class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.f = MagicMock()
        sys.modules['frappe'] = self.f
        spec = importlib.util.spec_from_file_location('preparer', ROOT/'bsgroup/quotation_preparer.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.f.session.user = 'paul@example.com'
        self.f.get_doc.return_value = dict(full_name='Paul', email='paul@example.com', mobile_no='123')
        self.f.db.get_value.return_value = dict(designation='Sales Manager', company_email='paul@example.com')

    def test_converter_not_owner(self):
        doc = dict(owner='sanisha@example.com', company='UAE', custom_designation='Managing Director')
        result = self.m.quotation_preparer(doc)
        self.assertEqual(result, dict(name='Paul', designation='Sales Manager', phone='123', email='paul@example.com'))
        self.assertEqual(doc['owner'], 'sanisha@example.com')
        self.f.db.get_value.assert_called_once_with('Employee', dict(user_id='paul@example.com', status='Active', company='UAE'), ['designation','cell_number','company_email'], as_dict=True)

    def test_missing_profile_never_uses_quotation_or_fixed_name(self):
        self.f.db.get_value.return_value = None
        self.f.get_doc.return_value = dict(first_name='Paul', email='paul@example.com')
        result = self.m.quotation_preparer(dict(company='Oman', custom_designation='Managing Director'))
        self.assertEqual(result['designation'], '')
        self.assertEqual(result['phone'], '')
        self.assertEqual(result['name'], 'Paul')

    def test_regional_proposal_replacement_idempotent(self):
        old = '<div><div class="cover-closing">With Regards,</div>\n<p class="sig-name">{{ doc.owner_name or "Gopinath Sundaram" }}</p>\n<p>{{ doc.owner_title }}</p>\n</div>\n{{ footer() }}'
        new = self.m.patch_html(old)
        self.assertNotIn('Gopinath', new)
        self.assertNotIn('doc.owner', new)
        self.assertIn('preparer.email | e', new)
        self.assertEqual(new, self.m.patch_html(new))

    def test_enterprise_layouts_keep_authorised_signatory(self):
        for name in ('enterprise.html', 'enterprise_quortation.html'):
            old = (ROOT/'bsgroup/templates'/name).read_text(encoding='utf-8')
            new = self.m.patch_html(old)
            self.assertNotEqual(old, new)
            self.assertIn('{{ auth_name }}', new)
            self.assertNotIn('{{ signatory }}</b>', new)
            self.assertEqual(new, self.m.patch_html(new))
            # Verify syntactically balanced Jinja using the actual renderer parser.
            from jinja2 import Environment
            Environment().parse(new)

    def test_unknown_layout_untouched(self):
        self.assertEqual(self.m.patch_html('<p>Other format</p>'), '<p>Other format</p>')

    def test_signature_switches_user_and_escapes_profile_text(self):
        from jinja2 import Environment
        template = Environment().from_string(self.m.SIGNATURE)
        paul = template.render(doc=dict(company='UAE'), quotation_preparer=self.m.quotation_preparer)
        self.f.session.user = 'sanisha@example.com'
        self.f.get_doc.return_value = dict(full_name='Sanisha <Sales>', email='sanisha@example.com', phone='456')
        self.f.db.get_value.return_value = dict(designation='Sales Executive')
        sanisha = template.render(doc=dict(company='UAE'), quotation_preparer=self.m.quotation_preparer)
        self.assertIn('Paul', paul)
        self.assertNotIn('Paul', sanisha)
        self.assertIn('Sanisha &lt;Sales&gt;', sanisha)
        self.assertIn('Sales Executive', sanisha)
        self.assertIn('sanisha@example.com', sanisha)
        self.assertIn('456', sanisha)

if __name__ == '__main__':
    unittest.main()
