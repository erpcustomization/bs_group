import json, pathlib, re, unittest
from unittest.mock import Mock, patch
import oman_quote_flow_unit as fixture
from jinja2 import Environment
from bsgroup import quotation_optional_terms as terms

frappe, Doc = fixture.frappe, fixture.Doc
ROOT = pathlib.Path(__file__).resolve().parents[1]


class OptionalTermsTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.FlowTests();self.base.setUp()
        frappe.local.site='erp-bitssecureit.u.frappe.cloud'

    def test_real_enterprise_templates_accept_blank_terms_and_retain_other_checks(self):
        for name in ('enterprise_quotation_3','enterprise_quotation_format_2'):
            source=json.loads((ROOT/f'bsgroup/bs_group/print_format/{name}/{name}.json').read_text(encoding='utf-8'))['html']
            result=terms.patch_html(source)
            self.assertNotEqual(source,result)
            self.assertEqual(result,terms.patch_html(result))
            env=Environment();env.parse(result)
            condition=re.search(r'{%- if (not doc.custom_scope_overview[^%]+)%}',result).group(1).strip()
            blocked=env.compile_expression(condition)
            doc=Doc(custom_scope_overview='Scope',custom_warranty='OEM warranty',valid_till='2026-12-01',tc_name='',terms='')
            self.assertFalse(blocked(doc=doc,warr_ok=True))
            self.assertTrue(blocked(doc=doc,warr_ok=False),'Warranty checks stay enforced')
            doc.valid_till='';self.assertTrue(blocked(doc=doc,warr_ok=True),'Validity remains required')
            doc.valid_till='2026-12-01';doc.custom_scope_overview=''
            self.assertTrue(blocked(doc=doc,warr_ok=True),'Scope remains required')
            self.assertIn('{% if doc.terms %}<div class="sec tc',result)
            show_terms=env.compile_expression('doc.terms')
            self.assertFalse(show_terms(doc=doc))
            doc.terms='<p>Entered contractual wording</p>'
            self.assertEqual(show_terms(doc=doc),doc.terms,'Manual terms do not require choosing a template')
            self.assertIn('frappe.render_template(doc.terms, {"doc": doc})',result)
            self.assertIn('b.pay|length',result,'Payment checks are retained')

    def test_install_is_uae_only_and_does_not_modify_quotations(self):
        fields={n:Doc(reqd=1,mandatory_depends_on='eval:doc.company') for n in ('tc_name','terms')}
        doc=Doc(name='Enterprise',html='or not warr_ok or not doc.tc_name or not doc.valid_till')
        doc.save=Mock(side_effect=lambda **kwargs:Doc.save(doc))
        frappe.get_all.return_value=['Enterprise'];frappe.get_doc.return_value=doc
        def set_property(dt,name,prop,value,kind): fields[name][prop]=value
        setter=Mock(side_effect=set_property)
        with patch.object(frappe,'get_meta',create=True,return_value=Doc(get_field=fields.get)),patch.object(frappe,'clear_cache',create=True),self.base.mod('frappe.custom.doctype.property_setter.property_setter',make_property_setter=setter):
            terms.install();self.assertEqual(doc.saved,1);self.assertEqual(setter.call_count,4)
            doc.save.assert_called_once_with(ignore_permissions=True)
            terms.install();self.assertEqual(doc.saved,1);self.assertEqual(setter.call_count,4)
            self.assertTrue(all(c.args[0]=='Print Format' for c in frappe.get_doc.call_args_list))
            frappe.get_doc.reset_mock();setter.reset_mock();frappe.local.site='erp-om.k.frappe.cloud'
            terms.install();frappe.get_doc.assert_not_called();setter.assert_not_called()
        self.assertEqual(terms.patch_html('<p>{{ doc.terms }}</p>'),'<p>{{ doc.terms }}</p>')


if __name__=='__main__':unittest.main(verbosity=2)
