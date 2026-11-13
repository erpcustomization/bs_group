import json, pathlib, unittest
from unittest.mock import Mock, patch
import oman_quote_flow_unit as fixture
frappe, Doc, flow, ValidationError = fixture.frappe, fixture.Doc, fixture.flow, fixture.ValidationError


class UAEFlowTests(unittest.TestCase):
    def setUp(self):
        self.base=fixture.FlowTests();self.base.setUp();self.q=self.base.q;self.s=self.base.s
        frappe.local.site='erp-bitssecureit.u.frappe.cloud'
        frappe.defaults.get_global_default.side_effect=lambda key: int(key in (flow.UAE_FLAG,'bs_oman_client_descriptions'))
        frappe.get_doc.return_value=self.s
        self.q.is_new=lambda:True

    def test_uae_requires_its_own_opt_in(self):
        self.assertTrue(flow.enabled())
        self.assertTrue(flow.template_selection_enabled())
        frappe.defaults.get_global_default.side_effect=lambda key:int(key==flow.FLAG)
        self.assertFalse(flow.enabled())
        self.assertFalse(flow.template_selection_enabled())

    def test_uae_template_chooser_uses_saved_choice_and_local_default(self):
        frappe.get_doc.return_value=self.q
        default=flow.print_formats()[1]
        frappe.get_all.return_value=[default,'Quotation Classic']
        self.assertEqual(flow.pdf_templates('Q-1')['selected'],default)
        self.q[flow.PDF_TEMPLATE_FIELD]='Quotation Classic'
        self.assertEqual(flow.pdf_templates('Q-1')['selected'],'Quotation Classic')
        self.assertIn('print',self.q._permissions)
        with self.base.mod('bsgroup.dcs.procurement',SEND_ROLES={'Sales Manager'}):
            with patch('bsgroup.oman_item_description.managed',return_value=False):
                self.assertTrue(flow.context('Q-1')['choose_pdf_template'])

    def test_uae_selected_template_preserves_co_and_costing_in_pdf_only(self):
        self.q.items=[Doc(description='Internal PART-101',item_code='PART-101',item_name='Internal name',
            custom_oman_use_costing_description=0,custom_oman_client_description='Customer equipment',qty=2,rate=100),
            Doc(description='Costing item',item_code='PART-102',custom_oman_use_costing_description=1,qty=1,rate=50)]
        self.q[flow.PDF_TEMPLATE_FIELD]='Quotation Classic'
        frappe.db.get_value.side_effect=lambda dt,*a,**kw:Doc(doc_type='Quotation',disabled=0) if dt=='Print Format' else 'UAE Letterhead'
        with patch.object(frappe,'get_print',create=True,return_value=b'pdf') as printer:
            flow.render_pdf(self.q,template='Quotation Modern')
            self.assertEqual(printer.call_args.args[2],'Quotation Modern')
            printed=printer.call_args.kwargs['doc']
            self.assertEqual(printed.items[0].description,'Customer equipment')
            self.assertEqual(printed.items[0].item_code,'')
            self.assertEqual(printed.items[1].description,'Costing item')
            self.assertEqual(self.q.items[0].description,'Internal PART-101')
            self.assertEqual(self.q.items[0].item_code,'PART-101')
            self.assertEqual(printer.call_args.kwargs['letterhead'],'UAE Letterhead')
            flow.render_pdf(self.q,no_letterhead=1)
            self.assertEqual(printer.call_args.args[2],'Quotation Classic')

    def test_uae_template_field_migration_is_site_scoped(self):
        from bsgroup.patches.v0_1.uae_quotation_pdf_template import execute
        from bsgroup.patches.v0_1.oman_quotation_pdf_template import execute as oman_execute
        create=Mock()
        with self.base.mod('frappe.custom.doctype.custom_field.custom_field',create_custom_fields=create):
            oman_execute();create.assert_not_called()
            execute();create.assert_called_once()
            field=create.call_args.args[0]['Quotation'][0]
            self.assertEqual(field['fieldname'],flow.PDF_TEMPLATE_FIELD)
            self.assertTrue(field['read_only']);self.assertTrue(field['no_copy'])
            create.reset_mock();frappe.local.site='erp-om.k.frappe.cloud'
            execute();create.assert_not_called()

    def test_optional_co_for_legacy_uae_rows_and_explicit_co_preserved(self):
        from bsgroup import oman_item_description as desc
        self.s.items[0].name='SOURCE-1'
        row=Doc(name='ROW-1',idx=1,item_code='ITEM',description='Scope',qty=1,rate=125,
                custom_oman_use_costing_description=0,custom_oman_use_co_description=0,
                custom_oman_client_description='')
        self.q.items=[row]
        desc.prepare(self.q)
        self.assertEqual(row.get(desc.COSTING),1)
        self.assertEqual(desc.missing_rows(self.q),[])
        row.set(desc.COSTING,0);row.set(desc.CO,1)
        desc.prepare(self.q)
        self.assertEqual(row.get(desc.COSTING),0)
        with self.assertRaises(ValidationError):desc.require_client_wording(self.q)
        row.set(desc.FIELD,'Client wording')
        desc.prepare(self.q);desc.require_client_wording(self.q)
        self.assertEqual(row.get(desc.FIELD),'Client wording')

    def test_uae_pdf_context_distinguishes_optional_co_and_required_terms(self):
        self.q.items=[Doc(idx=1,description='Costing wording',custom_oman_use_costing_description=1,
                         custom_oman_client_description='')]
        frappe.get_doc.side_effect=lambda dt,*args,**kwargs:self.q if dt=='Quotation' else self.s
        with self.base.mod('bsgroup.dcs.procurement',SEND_ROLES={'Sales Manager'}):
            data=flow.context('Q-1')
            self.assertTrue(data['save_feedback'])
            self.assertTrue(data['ready_to_convert'])
            self.assertEqual(len(data['pdf_issues']),1)
            self.assertIn('Terms and Conditions',data['pdf_issues'][0])
            self.q.tc_name='Approved';self.q.terms='<p>Approved terms</p>'
            self.assertEqual(flow.context('Q-1')['pdf_issues'],[])

    def test_terminal_status_reloads_persisted_values_only_in_uae(self):
        for site, reloads in [('erp-bitssecureit.u.frappe.cloud', 1), ('erp-om.k.frappe.cloud', 0)]:
            with self.subTest(site=site):
                frappe.local.site=site
                self.q.docstatus=0; self.q.custom_pipeline_stage='Draft'
                self.q.reload=Mock()
                with patch.object(flow,'_quotation',return_value=self.q), patch.object(flow,'snapshot'):
                    flow._change_status('Q-1','Lost','M1',reason='Customer declined')
                self.assertEqual(self.q.reload.call_count,reloads)
                self.assertEqual(self.q.custom_pipeline_stage,'Lost')
                self.assertEqual(self.q.docstatus,1)

    def test_editable_status_does_not_reload_or_submit(self):
        self.q.reload=Mock()
        with patch.object(flow,'_quotation',return_value=self.q), patch.object(flow,'snapshot'):
            flow._change_status('Q-1','Delayed','M1',reason='Awaiting customer')
        self.q.reload.assert_not_called()
        self.assertEqual(self.q.docstatus,0)

    def test_duplicate_insert_checks_all_quotes_under_dcs_lock(self):
        frappe.get_all.return_value=['Q-EXISTING']
        with self.assertRaisesRegex(ValidationError,'already exists'):flow.validate(self.q)
        frappe.get_doc.assert_called_with('Deal Cost Sheet','DCS-1',for_update=True)
        # The lookup is not restricted to the creator, so another user's quote is detected.
        self.assertEqual(frappe.get_all.call_args.kwargs['filters'],{'custom_deal_cost_sheet':'DCS-1','docstatus':['!=',2]})

    def test_duplicate_pair_blocks_revision_even_with_return_link(self):
        frappe.get_all.return_value=['Q-1','Q-2']
        with self.assertRaisesRegex(ValidationError,'multiple active'):flow.guard_dcs_revision(self.s)
        self.assertIsNone(flow.linked_quotation(self.s))
        self.assertEqual(self.s.custom_quotation,'Q-1')

    def test_conflict_context_is_read_only_and_flags_review(self):
        frappe.get_all.return_value=['Q-1','Q-2']
        result=flow.dcs_context('DCS-1')
        self.assertTrue(result['conflict']);self.assertFalse(result['auto_sync'])
        frappe.db.set_value.assert_not_called()

    def test_discount_policy_and_historical_isolation(self):
        self.q.apply_discount_on='Grand Total';flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Net Total')
        self.q.update(docstatus=1,custom_oman_flow=0,apply_discount_on='Grand Total')
        self.assertFalse(flow.pilot(self.q));flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Grand Total')

    def test_uae_administrator_setup_only(self):
        self.assertFalse(flow.setup_authorised())
        frappe.get_roles.return_value=['System Manager'];self.assertTrue(flow.setup_authorised())
        frappe.local.site='unrelated.example.com';self.assertFalse(flow.setup_authorised())

    def test_uae_template_supports_private_description_and_revision(self):
        from bsgroup.oman_item_description import print_html
        path=pathlib.Path(__file__).resolve().parents[1]/'bsgroup/bs_group/print_format/enterprise_quotation_3/enterprise_quotation_3.json'
        html=json.loads(path.read_text(encoding='utf-8'))['html']
        result=print_html(html)
        self.assertIn('custom_oman_use_costing_description',result)
        self.assertIn('custom_oman_client_description',result)
        self.assertEqual(result,print_html(result))
        self.assertEqual(html.count('{%- set rev = doc.name.split("-")|last if doc.amended_from else "0" -%}'),1)
        self.assertEqual(flow.print_formats(),('EnterPrise Quotation 3','Enterprise Quotation - UAE Workflow'))

    def test_hook_registration_preserves_existing_and_is_idempotent(self):
        from bsgroup.quotation_workflow_hooks import configure
        ns=dict(doc_events={'Quotation':{'validate':'existing.validate'}},doctype_js={},doctype_list_js={})
        configure(ns);configure(ns)
        self.assertEqual(ns['doc_events']['Quotation']['validate'],['bsgroup.oman_quotation_flow.validate','existing.validate'])
        self.assertEqual(ns['doc_events']['Deal Cost Sheet']['on_submit'],['bsgroup.oman_quotation_flow.dcs_submitted'])

if __name__=='__main__':unittest.main(verbosity=2)
