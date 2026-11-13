import copy, importlib, pathlib, unittest
from unittest.mock import Mock, patch
import oman_quote_flow_unit as fixture
frappe,Doc,flow,ValidationError=fixture.frappe,fixture.Doc,fixture.flow,fixture.ValidationError
desc=importlib.import_module('bsgroup.oman_item_description')

def clone(value):
 if isinstance(value,dict):return Doc({k:clone(v) for k,v in dict.items(value)})
 if isinstance(value,list):return [clone(v) for v in value]
 return value

class DescriptionTests(unittest.TestCase):
 def setUp(self):
  base=fixture.FlowTests();base.setUp();self.base=base;self.q=base.q;self.s=base.s
  frappe.defaults.get_global_default.side_effect=lambda key:1 if key in (flow.FLAG,desc.FLAG) else 0
  self.s.items[0].name='DCS-LINE-1';self.s.items[0].description='INTERNAL-PART-123 supplier wording'
  self.q.items=[Doc(name='Q-LINE-1',idx=1,item_code='ITEM',description=self.s.items[0].description,qty=1,rate=125,custom_oman_client_description='Office network equipment')]
  frappe.get_doc.side_effect=lambda dt,name=None,**kw:self.s if dt=='Deal Cost Sheet' else self.q
 def test_uae_and_older_submitted_are_excluded(self):
  frappe.local.site='erp-bitssecureit.u.frappe.cloud';self.assertFalse(desc.managed(self.q))
  frappe.local.site='erp-om.k.frappe.cloud';self.q.docstatus=1;self.assertFalse(desc.managed(self.q))
  self.q.set(desc.PARENT,1);self.assertTrue(desc.managed(self.q))
 def test_internal_costing_and_client_text_are_independent(self):
  self.q.items[0].description='changed internal text'
  desc.prepare(self.q)
  self.assertEqual(self.q.items[0].description,self.s.items[0].description)
  self.assertEqual(self.q.items[0].get(desc.FIELD),'Office network equipment')
  self.assertEqual(self.q.items[0].get(desc.SOURCE),'DCS-LINE-1');self.assertEqual(self.q.get(desc.PARENT),1)
 def test_blank_client_description_never_falls_back(self):
  for blank in ('','<p><br></p>','<p>&nbsp;</p>','<script>secret()</script>','Generic'):
   self.q.items[0].set(desc.FIELD,blank)
   with self.assertRaisesRegex(ValidationError,'CO Item Description'):desc.require_client_wording(self.q)
 def test_customer_can_choose_any_real_wording(self):
  self.q.items[0].set(desc.FIELD,'<p>Supply and install managed switches</p>');desc.require_client_wording(self.q)
  self.assertEqual(desc.visible_text('<p>Hello&nbsp;client</p>'),'Hello client')
 def test_costing_selection_prints_costing_and_does_not_require_co(self):
  row=self.q.items[0];row.set(desc.FIELD,'');row.set(desc.COSTING,1)
  desc.prepare(self.q);desc.require_client_wording(self.q)
  self.assertEqual(row.get(desc.CO),0)
  row.set(desc.COSTING,0);row.set(desc.CO,1);desc.prepare(self.q)
  self.assertEqual(row.get(desc.CO),1)
  with self.assertRaises(ValidationError):desc.require_client_wording(self.q)
 def test_switching_keeps_co_wording(self):
  row=self.q.items[0];row.set(desc.COSTING,1);desc.prepare(self.q)
  self.assertEqual(desc.preserved_wording(self.q,self.s)['DCS-LINE-1'][2],1)
  row.set(desc.COSTING,0);desc.prepare(self.q)
  self.assertEqual(row.get(desc.FIELD),'Office network equipment')
 def test_no_cross_assignment_when_costing_lines_reorder(self):
  second=clone(self.s.items[0]);second.name='DCS-LINE-2';second.description='INTERNAL-PART-999';self.s.items.append(second)
  row=clone(self.q.items[0]);row.name='Q-LINE-2';row.idx=2;row.description=second.description;row.set(desc.FIELD,'Second customer line');self.q.items.append(row)
  desc.prepare(self.q)
  self.q.items[1].set(desc.COSTING,1)
  revised=clone(self.s);revised.items.reverse();revised.items[0].selling_rate=140;revised.total_selling=265;self.q.total=265
  frappe.get_doc.side_effect=None;frappe.get_doc.return_value=self.q;frappe.db.get_value.return_value=Doc(item_name='Item',stock_uom='Nos')
  with self.base.mod('bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet',quotation_deal_identity=lambda s,q:''),self.base.mod('bsgroup.dcs.currency',money_tolerance=lambda c:.001),patch.object(flow,'snapshot'):
   flow.sync_draft(revised,previous_sheet=self.s)
  self.assertEqual(self.q.items[0][desc.FIELD],'Second customer line');self.assertEqual(self.q.items[0][desc.SOURCE],'DCS-LINE-2')
  self.assertEqual(self.q.items[0][desc.COSTING],1)
  self.assertEqual(self.q.items[1][desc.COSTING],0)
  self.assertEqual(self.q.items[1][desc.FIELD],'Office network equipment');self.assertEqual(self.q.name,'Q-1')
 def test_new_or_replaced_item_defaults_costing_and_does_not_reuse_co(self):
  desc.prepare(self.q);revised=clone(self.s);revised.items[0].item_code='NEW-ITEM'
  frappe.get_doc.side_effect=None;frappe.get_doc.return_value=self.q;frappe.db.get_value.return_value=Doc(item_name='New Item',stock_uom='Nos')
  with self.base.mod('bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet',quotation_deal_identity=lambda s,q:''),self.base.mod('bsgroup.dcs.currency',money_tolerance=lambda c:.001),patch.object(flow,'snapshot'):
   flow.sync_draft(revised,previous_sheet=self.s)
  self.assertEqual(self.q.items[0][desc.FIELD],'')
  self.assertEqual(self.q.items[0][desc.COSTING],1)
  self.assertEqual(self.q.items[0][desc.CO],0)
 def test_unset_oman_choice_defaults_to_costing_without_co(self):
  row=self.q.items[0];row.set(desc.FIELD,'');row.set(desc.COSTING,0);row.set(desc.CO,0)
  desc.prepare(self.q)
  self.assertEqual(row.get(desc.COSTING),1);self.assertEqual(row.get(desc.CO),0)
  desc.require_client_wording(self.q)
 def test_explicit_empty_co_choice_is_preserved(self):
  row=self.q.items[0];row.set(desc.FIELD,'');row.set(desc.COSTING,0);row.set(desc.CO,1)
  desc.prepare(self.q)
  self.assertEqual(row.get(desc.COSTING),0);self.assertEqual(row.get(desc.CO),1)
  with self.assertRaises(ValidationError):desc.require_client_wording(self.q)
 def test_oman_saved_pdf_context_keeps_its_existing_terms_policy(self):
  row=self.q.items[0];row.set(desc.FIELD,'');row.set(desc.COSTING,1)
  with self.base.mod('bsgroup.dcs.procurement',SEND_ROLES={'Sales Manager'}):
   data=flow.context('Q-1')
   self.assertTrue(data['save_feedback']);self.assertTrue(data['ready_to_convert'])
   self.assertEqual(data['pdf_issues'],[])
   row.set(desc.COSTING,0);row.set(desc.CO,1)
   data=flow.context('Q-1')
   self.assertFalse(data['ready_to_convert']);self.assertEqual(len(data['pdf_issues']),1)
   self.assertIn('CO Description is optional',data['pdf_issues'][0])
 def test_oman_default_migration_is_scoped_and_idempotent(self):
  migration=importlib.import_module('bsgroup.patches.v0_1.oman_quotation_description_defaults')
  fields={'Quotation Item-'+desc.COSTING:Mock(default='0'),'Quotation Item-'+desc.CO:Mock(default='1')}
  with patch.object(frappe.db,'exists',return_value=True),patch.object(frappe,'get_doc',side_effect=lambda dt,name:fields[name]) as get_doc,patch.object(frappe,'clear_cache',create=True):
   migration.execute();migration.execute()
   self.assertEqual(fields['Quotation Item-'+desc.COSTING].default,'1')
   self.assertEqual(fields['Quotation Item-'+desc.CO].default,'0')
   for field in fields.values():field.save.assert_called_once_with(ignore_permissions=True)
   get_doc.reset_mock()
   for site in ('erp-bitssecureit.u.frappe.cloud','unrelated.example.com'):
    frappe.local.site=site;migration.execute()
   get_doc.assert_not_called()
 def test_source_reference_cannot_be_reassigned_by_client(self):
  desc.prepare(self.q);self.q._before=clone(self.q);self.q.items[0].set(desc.SOURCE,'OTHER-LINE')
  with self.assertRaisesRegex(ValidationError,'source references'):desc.prepare(self.q)
 def test_context_blocks_pdf_until_client_wording_is_saved(self):
  frappe.get_doc.side_effect=None;frappe.get_doc.return_value=self.q
  with self.base.mod('bsgroup.dcs.procurement',SEND_ROLES={'Sales Manager'}):
   self.q.items[0].set(desc.FIELD,'');self.assertFalse(flow.context('Q-1')['ready_to_convert'])
   self.q.items[0].set(desc.FIELD,'Client line');self.assertTrue(flow.context('Q-1')['ready_to_convert'])
 def test_print_patch_covers_table_and_annexure_and_is_idempotent(self):
  source=(fixture.ROOT/'bsgroup/templates/enterprise_quortation.html').read_text(encoding='utf8')
  html=desc.print_html(source);self.assertEqual(desc.print_html(html),html)
  self.assertEqual(html.count('if not '+desc.PRINT_MODE+' and row.item_code'),2)
  self.assertIn('row.get("custom_oman_client_description")',html)
  self.assertIn('else (row.description or row.item_name or "")',html)
 def test_changed_print_layout_is_refused(self):
  with self.assertRaisesRegex(ValidationError,'print layout changed'):desc.print_html('new unknown template')
 def test_setup_cannot_run_for_sales_or_unrelated_site(self):
  with self.assertRaises(ValidationError):desc.install()
  frappe.session.user='Administrator';frappe.local.site='unrelated.example.com'
  with self.assertRaises(ValidationError):desc.install()

if __name__=='__main__':unittest.main(verbosity=2)
