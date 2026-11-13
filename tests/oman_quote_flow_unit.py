import copy
import importlib
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
class ValidationError(Exception): pass
class Doc(dict):
    def __getattribute__(self, key):
        if not key.startswith('_') and dict.__contains__(self, key): return dict.__getitem__(self,key)
        return super().__getattribute__(key)
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value
    def __deepcopy__(self, memo): return Doc({k:copy.deepcopy(v,memo) for k,v in dict.items(self)})
    def get_doc_before_save(self): return self.get('_before')
    def check_permission(self, p): self.setdefault('_permissions', []).append(p)
    def as_dict(self): return {k:v for k,v in dict.items(self) if not k.startswith('_')}
    def set(self,k,v): self[k]=v
    def save(self): self.saved=self.get('saved',0)+1; return self
    def submit(self): self.check_permission('submit'); self.docstatus=1; return self
    def insert(self, **kwargs): self.name=self.get('name') or 'AUDIT-1'; return self
    def _validate_mandatory(self): self.mandatory_checked=True
    def _get_missing_mandatory_fields(self): return []
    def get_all_children(self): return []

def throw(message, *a, **kw): raise ValidationError(message)
frappe=types.ModuleType('frappe')
frappe.local=types.SimpleNamespace(site='erp-om.k.frappe.cloud')
frappe.defaults=types.SimpleNamespace(get_global_default=Mock(return_value='1'))
frappe.session=types.SimpleNamespace(user='sales@example.com')
frappe.whitelist=lambda *a,**kw: (lambda fn:fn)
frappe.throw=throw;frappe.PermissionError=ValidationError
frappe.db=Mock();frappe.get_doc=Mock();frappe.get_all=Mock();frappe.get_roles=Mock(return_value=['BS Scoped Sales'])
frappe.has_permission=Mock(return_value=True);frappe.as_json=lambda x:json.dumps(x,default=str)
utils=types.ModuleType('frappe.utils');utils.cint=lambda x:int(x or 0);utils.flt=lambda x:float(x or 0)
utils.today=lambda:'2026-11-09';utils.now_datetime=lambda:__import__('datetime').datetime(2026,11,9,14)
sys.modules['frappe']=frappe;sys.modules['frappe.utils']=utils
package=types.ModuleType('bsgroup');package.__path__=[str(ROOT/'bsgroup')];sys.modules['bsgroup']=package
flow=importlib.import_module('bsgroup.oman_quotation_flow')

class FlowTests(unittest.TestCase):
    def setUp(self):
        frappe.local.site='erp-om.k.frappe.cloud';frappe.defaults.get_global_default.return_value='1'
        frappe.defaults.get_global_default.side_effect=lambda key: frappe.defaults.get_global_default.return_value if key==flow.FLAG else 0
        frappe.session.user='sales@example.com';frappe.get_roles.return_value=['BS Scoped Sales']
        frappe.get_doc.reset_mock();frappe.get_doc.side_effect=None
        frappe.get_all.reset_mock();frappe.get_all.return_value=[];frappe.db.reset_mock();frappe.db.get_value.side_effect=None
        self.q=Doc(name='Q-1',docstatus=0,custom_deal_cost_sheet='DCS-1',custom_pipeline_stage='Draft',
            custom_oman_revision_no=0,custom_oman_flow=1,modified='M1',currency='OMR',flags=Doc(),total=125)
        self.s=Doc(name='DCS-1',custom_quotation='Q-1',docstatus=1,currency='OMR',company='OM',total_selling=125,
            items=[Doc(item_code='ITEM',item_name='Item',description='Scope',qty=1,cost_rate=80,selling_rate=125)],addtional_charges=[])
    def mod(self,name,**members):
        m=types.ModuleType(name)
        for key,value in members.items():setattr(m,key,value)
        return patch.dict(sys.modules,{name:m})
    def test_gate_never_enables_uae(self):
        frappe.local.site='erp-bitssecureit.u.frappe.cloud';self.assertFalse(flow.enabled())
        frappe.local.site='erp-om.k.frappe.cloud';frappe.defaults.get_global_default.return_value='0';self.assertFalse(flow.enabled())
    def test_discount_basis_normalized_before_native_calculation(self):
        for amount, percentage in ((0,0),(10,0),(0,10)):
            self.q.update(apply_discount_on='Grand Total',discount_amount=amount,additional_discount_percentage=percentage)
            flow.before_validate(self.q)
            self.assertEqual(self.q.apply_discount_on,'Net Total')
            self.assertEqual((self.q.discount_amount,self.q.additional_discount_percentage),(amount,percentage))
            self.assertEqual(self.q.total,125)
    def test_discount_policy_is_oman_only(self):
        self.q.apply_discount_on='Grand Total'
        frappe.local.site='erp-bitssecureit.u.frappe.cloud'
        flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Grand Total')
        frappe.local.site='erp-om.k.frappe.cloud';frappe.defaults.get_global_default.return_value='0'
        flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Grand Total')
    def test_discount_basis_retains_submitted_and_cancelled_history(self):
        for status in (1,2):
            self.q.docstatus=status;self.q.apply_discount_on='Grand Total'
            flow.before_validate(self.q)
            self.assertEqual(self.q.apply_discount_on,'Grand Total')
        self.q.docstatus=1;self.q._before=Doc(docstatus=1)
        flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Grand Total')
    def test_finalizing_draft_uses_net_basis(self):
        self.q.docstatus=1;self.q._before=Doc(docstatus=0);self.q.apply_discount_on='Grand Total'
        flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Net Total')
    def test_legacy_and_other_documents_not_enrolled(self):
        self.q.custom_deal_cost_sheet=None;self.q.custom_oman_flow=0;self.q.apply_discount_on='Grand Total'
        flow.before_validate(self.q)
        self.assertEqual(self.q.apply_discount_on,'Grand Total')
    def test_print_requires_saving_discounted_drafts_first(self):
        for amount, percentage in ((10,0),(0,5)):
            self.q.update(apply_discount_on='Grand Total',discount_amount=amount,additional_discount_percentage=percentage)
            with self.assertRaisesRegex(ValidationError,'Save this quotation'):flow.require_net_discount(self.q)
            self.q.apply_discount_on='Net Total';flow.require_net_discount(self.q)
        self.q.docstatus=1;self.q.apply_discount_on='Grand Total';flow.require_net_discount(self.q)
    def test_print_callback_accepts_framework_settings(self):
        settings={'print_with_letterhead':0}
        self.q.update(apply_discount_on='Net Total',discount_amount=10)
        flow.require_net_discount(self.q,'before_print',settings)
        flow.require_net_discount(self.q,method='before_print',print_settings=settings)
        self.q.apply_discount_on='Grand Total'
        with self.assertRaisesRegex(ValidationError,'Save this quotation'):
            flow.require_net_discount(self.q,'before_print',settings)
        self.q.docstatus=1;flow.require_net_discount(self.q,'before_print',settings)
        frappe.local.site='erp-bitssecureit.u.frappe.cloud'
        self.q.docstatus=0;flow.require_net_discount(self.q,'before_print',settings)
    def test_legacy_submitted_excluded(self):
        self.q.docstatus=1;self.q.custom_oman_flow=0;self.assertFalse(flow.pilot(self.q))
    def test_client_cannot_clear_pilot_to_bypass_lock(self):
        self.q._before=copy.deepcopy(self.q);self.q._before.docstatus=1;self.q._before.custom_pipeline_stage='Won'
        self.q.docstatus=1;self.q.custom_oman_flow=0
        self.assertTrue(flow.pilot(self.q))
        with self.assertRaisesRegex(ValidationError,'frozen'):flow.validate(self.q)
    def test_win_and_loss_block_revisions(self):
        for stage in ('Won','Lost'):
            self.q.custom_pipeline_stage=stage
            with self.assertRaises(ValidationError):flow.check_editable(self.q)
    def test_cancelled_and_delayed_remain_editable(self):
        for stage in ('Draft','Sent','Delayed','Cancelled','Expired'):
            self.q.custom_pipeline_stage=stage;flow.check_editable(self.q)
    def test_native_cancel_and_submit_not_editable(self):
        for status in (1,2):
            self.q.docstatus=status
            with self.assertRaises(ValidationError):flow.check_editable(self.q)
    def test_manual_status_change_rejected(self):
        self.q._before=copy.deepcopy(self.q);self.q.custom_pipeline_stage='Won'
        with self.assertRaisesRegex(ValidationError,'Change Status'):flow.validate(self.q)
    def test_direct_revision_number_change_rejected(self):
        self.q._before=copy.deepcopy(self.q);self.q.custom_oman_revision_no=42
        with self.assertRaisesRegex(ValidationError,'revision numbers'):flow.validate(self.q)
    def test_native_submit_requires_terminal_action(self):
        self.q._before=copy.deepcopy(self.q);self.q.docstatus=1
        with self.assertRaisesRegex(ValidationError,'finalise'):flow.validate(self.q)
    def test_legacy_submitted_cannot_opt_in(self):
        self.q._before=copy.deepcopy(self.q);self.q._before.docstatus=1;self.q._before.custom_oman_flow=0;self.q.docstatus=1
        with self.assertRaisesRegex(ValidationError,'Historical'):flow.validate(self.q)
    def test_reason_for_delayed_cancelled_lost(self):
        for stage in ('Delayed','Cancelled','Lost'):
            self.q.custom_pipeline_stage=stage;self.q.docstatus=1 if stage=='Lost' else 0
            with self.assertRaisesRegex(ValidationError,'reason'):flow.validate_stage(self.q)
            self.q.custom_lost_reason='Explained';self.assertTrue(flow.validate_stage(self.q));self.q.custom_lost_reason=''
    def test_terminal_requires_native_submission(self):
        for stage in ('Won','Lost'):
            self.q.custom_pipeline_stage=stage
            with self.assertRaisesRegex(ValidationError,'submission'):flow.validate_stage(self.q)
    def test_auto_creation_is_idempotent(self):
        self.s.custom_quotation=None;docs={'DCS-1':self.s,'Q-1':self.q};calls=[]
        def create(sheet):calls.append(sheet.name);return 'Q-1'
        def get(dt,name,**kw):return docs[name]
        frappe.get_doc.side_effect=get
        with self.mod('bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet',_create_quotation=create,
                refuse_stale_quotation_source=lambda s:None,quotation_deal_identity=lambda s,q:''):
            with patch.object(flow,'snapshot'):
                self.assertEqual(flow.ensure_draft(self.s),'Q-1');self.assertEqual(flow.ensure_draft(self.s),'Q-1')
        self.assertEqual(calls,['DCS-1']);self.assertEqual(self.s.custom_quotation,'Q-1')
        self.assertTrue(any(c.kwargs.get('for_update') for c in frappe.get_doc.call_args_list))
    def test_conflicting_links_refuse_creation(self):
        frappe.get_doc.return_value=self.s;frappe.get_all.return_value=['Q1','Q2']
        create=Mock()
        with self.mod('bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet',_create_quotation=create,
                refuse_stale_quotation_source=lambda s:None,quotation_deal_identity=lambda s,q:''):
            with self.assertRaisesRegex(ValidationError,'multiple'):flow.ensure_draft(self.s)
        create.assert_not_called()
    def test_non_sales_cannot_win(self):
        frappe.get_doc.return_value=self.q
        frappe.get_roles.return_value=['BS Scoped Presales']
        from bsgroup.dcs.sales_handover_access import AWARD_ROLES
        with self.mod('bsgroup.dcs.procurement',SEND_ROLES=AWARD_ROLES,source_items=Mock(),handover_warehouses=Mock(),send_to_procurement=Mock()):
            with self.assertRaisesRegex(ValidationError,'Sales or commercial-manager'):flow.won_context('Q-1')
    def test_all_sales_roles_can_open_won_handover(self):
        from bsgroup.dcs.sales_handover_access import AWARD_ROLES
        self.q.company=self.s.company
        frappe.get_doc.side_effect=lambda dt,name,**kw:self.q if dt=='Quotation' else self.s
        def send_to_procurement(quotation, schedule_date=None, warehouse=None): pass
        with self.mod('bsgroup.dcs.procurement',SEND_ROLES=AWARD_ROLES,
                source_items=lambda s:[{'is_stock_item':True}],handover_warehouses=lambda c:['Stores'],send_to_procurement=send_to_procurement):
            for role in AWARD_ROLES:
                with self.subTest(role=role):
                    frappe.get_roles.return_value=[role]
                    result=flow.won_context('Q-1')
                    self.assertEqual(result['warehouses'],['Stores']);self.assertTrue(result['stock_items'])
        self.assertIn('write',self.q._permissions);self.assertIn('write',self.s._permissions)
    def test_stale_status_request_rejected(self):
        frappe.get_doc.return_value=self.q
        with self.assertRaisesRegex(ValidationError,'changed'):flow._change_status('Q-1','Delayed','old',reason='Delay')
        self.assertIsNone(self.q.saved)
    def test_won_replay_reuses_requisition(self):
        self.q.docstatus=1;self.q.custom_pipeline_stage='Won';self.q.custom_bsp_material_request='MR-1'
        frappe.get_doc.return_value=self.q
        result=flow._change_status('Q-1','Won','old')
        self.assertTrue(result['already_sent']);self.assertEqual(result['requisition'],'MR-1');self.assertIsNone(self.q.saved)
    def test_draft_sync_keeps_quote_and_increments_revision(self):
        frappe.get_doc.return_value=self.q;frappe.db.get_value.return_value=Doc(item_name='Item',stock_uom='Nos')
        with self.mod('bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet',quotation_deal_identity=lambda s,q:''),self.mod('bsgroup.dcs.currency',money_tolerance=lambda c:0.001),patch.object(flow,'snapshot') as history:
            flow.sync_draft(self.s)
            self.assertEqual(self.q.name,'Q-1');self.assertEqual(self.q.custom_oman_revision_no,1)
            self.assertEqual(self.q.items[0]['rate'],125);self.assertEqual(history.call_count,2)
    def test_sync_checks_write_and_identity(self):
        frappe.get_doc.return_value=self.q;self.q.currency='AED'
        with self.mod('bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet',quotation_deal_identity=lambda s,q:''),self.mod('bsgroup.dcs.currency',money_tolerance=lambda c:0.001):
            with self.assertRaisesRegex(ValidationError,'currency'):flow.sync_draft(self.s)
        self.assertIn('write',self.q._permissions);self.assertIsNone(self.q.saved)
    def test_install_denied_outside_supported_sites_and_for_sales(self):
        with self.assertRaises(ValidationError):flow.install()
        frappe.session.user='Administrator';frappe.local.site='unrelated.example.com'
        with self.assertRaises(ValidationError):flow.install()
    def test_read_only_context_filters_win_by_role(self):
        frappe.get_doc.return_value=self.q
        from bsgroup.dcs.sales_handover_access import AWARD_ROLES
        with self.mod('bsgroup.dcs.procurement',SEND_ROLES=AWARD_ROLES):
            frappe.get_roles.return_value=['Technical Engineer']
            result=flow.context('Q-1');self.assertNotIn('Won',result['statuses']);self.assertTrue(result['editable'])
            for role in AWARD_ROLES:
                frappe.get_roles.return_value=[role];self.assertIn('Won',flow.context('Q-1')['statuses'])

    def test_pdf_uses_approved_format_and_letterhead(self):
        frappe.db.exists.return_value=True
        frappe.db.get_value.side_effect=lambda dt,*a,**kw:Doc(doc_type='Quotation',disabled=0) if dt=='Print Format' else 'Oman Letterhead'
        with patch.object(frappe,'get_print',create=True,return_value=b'pdf') as printer:
            self.assertEqual(flow.render_pdf(self.q),b'pdf')
        self.assertEqual(printer.call_args.args,('Quotation','Q-1',flow.PILOT_PRINT_FORMAT))
        self.assertEqual(printer.call_args.kwargs['letterhead'],'Oman Letterhead')
        self.assertFalse(printer.call_args.kwargs['no_letterhead'])
        self.assertNotIn('pdf_generator',printer.call_args.kwargs)

    def test_template_choices_require_quote_print_permission_and_are_oman_only(self):
        frappe.get_doc.return_value=self.q
        frappe.get_all.return_value=['Template A','Template B',flow.PILOT_PRINT_FORMAT]
        self.q[flow.PDF_TEMPLATE_FIELD]='Template B'
        result=flow.pdf_templates('Q-1')
        self.assertEqual(result['selected'],'Template B')
        self.assertEqual(result['templates'],['Standard','Template A','Template B',flow.PILOT_PRINT_FORMAT])
        self.assertIn('print',self.q._permissions)
        self.assertEqual(frappe.get_all.call_args.kwargs['filters'],{'doc_type':'Quotation','disabled':0})
        frappe.local.site='erp-bitssecureit.u.frappe.cloud'
        self.assertFalse(flow.template_selection_enabled())

    def test_invalid_pdf_templates_rejected(self):
        frappe.db.get_value.side_effect=None
        for value in (None,Doc(doc_type='Sales Invoice',disabled=0),Doc(doc_type='Quotation',disabled=1)):
            frappe.db.get_value.return_value=value
            with self.assertRaisesRegex(ValidationError,'enabled Quotation'):flow.validate_pdf_template('Wrong')
        with self.assertRaisesRegex(ValidationError,'enabled Quotation'):flow.validate_pdf_template('')
        self.assertEqual(flow.validate_pdf_template('Standard'),'Standard')

    def test_selected_pdf_template_and_co_wording_use_print_copy_only(self):
        self.q.items=[Doc(description='INTERNAL PART-123',item_code='PART-123',item_name='Internal name',
            custom_oman_use_costing_description=0,custom_oman_client_description='Customer package',qty=2,rate=100),
            Doc(description='Costing text',item_code='PART-456',custom_oman_use_costing_description=1,qty=1,rate=50)]
        self.q[flow.PDF_TEMPLATE_FIELD]='Template B'
        frappe.db.get_value.side_effect=lambda dt,*a,**kw:Doc(doc_type='Quotation',disabled=0) if dt=='Print Format' else 'Oman Letterhead'
        with self.mod('bsgroup.oman_item_description',require_client_wording=lambda q:None,managed=lambda q:True,
            PARENT='custom_oman_client_descriptions',FIELD='custom_oman_client_description',COSTING='custom_oman_use_costing_description',visible_text=str),patch.object(frappe,'get_print',create=True,return_value=b'pdf') as printer:
            flow.render_pdf(self.q,template='Template A')
            self.assertEqual(printer.call_args.args[2],'Template A')
            printed=printer.call_args.kwargs['doc']
            self.assertEqual(printed.items[0].description,'Customer package')
            self.assertEqual(printed.items[0].item_name,'Customer package')
            self.assertEqual(printed.items[0].item_code,'')
            self.assertEqual(printed.items[1].description,'Costing text')
            self.assertEqual(printed.items[1].item_code,'PART-456')
            self.assertEqual(self.q.items[0].item_code,'PART-123')
            self.assertEqual(self.q.items[0].description,'INTERNAL PART-123')
            flow.render_pdf(self.q,no_letterhead=1)
            self.assertEqual(printer.call_args.args[2],'Template B','Procurement reuses the issued template')
            self.assertEqual(printer.call_args.kwargs['no_letterhead'],1)

    def test_pdf_requires_current_saved_revision(self):
        frappe.get_doc.return_value=self.q
        with patch.object(flow,'render_pdf') as printer:
            with self.assertRaisesRegex(ValidationError,'changed'):flow.convert_pdf('Q-1','old')
        printer.assert_not_called();self.assertIn('print',self.q._permissions)

    def test_pdf_remembers_template_only_after_successful_generation(self):
        file=Doc(name='FILE-1',file_url='/private/files/q.pdf')
        frappe.get_doc.side_effect=lambda dt,*a,**kw:file if isinstance(dt,dict) else self.q if dt=='Quotation' else self.s
        frappe.db.get_value.return_value=Doc(doc_type='Quotation',disabled=0)
        with self.mod('bsgroup.dcs.quotation_control',validate_position=lambda s,q:None),patch.object(flow,'render_pdf',return_value=b'pdf') as printer,patch.object(flow,'snapshot') as audit:
            result=flow.convert_pdf('Q-1','M1',template='Template B')
            self.assertEqual(result['template'],'Template B')
            self.assertEqual(printer.call_args.kwargs['template'],'Template B')
            frappe.db.set_value.assert_called_once_with('Quotation','Q-1',flow.PDF_TEMPLATE_FIELD,'Template B',update_modified=False)
            self.assertIn('template: Template B',audit.call_args.args[1])
            self.assertEqual(self.q.modified,'M1')
            frappe.db.set_value.reset_mock();printer.side_effect=ValidationError('Invalid layout')
            with self.assertRaisesRegex(ValidationError,'Invalid layout'):flow.convert_pdf('Q-1','M1',template='Template A')
            frappe.db.set_value.assert_not_called()

    def test_status_operation_context_cannot_leak_after_error(self):
        with self.assertRaises(RuntimeError):
            with flow.operation(self.q,'status'):
                self.assertEqual(flow._operation.get(),('Q-1','status'))
                raise RuntimeError('Synthetic failure')
        self.assertIsNone(flow._operation.get())

    def test_legacy_reverse_link_is_adopted_only_inside_revision(self):
        self.s.custom_quotation=None;frappe.get_all.return_value=['Q-1'];frappe.get_doc.return_value=self.q
        self.assertTrue(flow.guard_dcs_revision(self.s));self.assertIsNone(self.s.custom_quotation)
        frappe.db.set_value.assert_not_called()
        with self.mod('bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet',quotation_deal_identity=lambda s,q:''):
            self.assertTrue(flow.guard_dcs_revision(self.s,attach=True))
        self.assertEqual(self.s.custom_quotation,'Q-1');self.assertIn('write',self.q._permissions)

    def test_ambiguous_legacy_links_are_never_guessed(self):
        self.s.custom_quotation=None;frappe.get_all.return_value=['Q-1','Q-2']
        self.assertIsNone(flow.linked_quotation(self.s))
        with self.assertRaisesRegex(ValidationError,'multiple'):flow.guard_dcs_revision(self.s,attach=True)
        frappe.db.set_value.assert_not_called()

    def test_historical_submitted_reverse_link_is_not_adopted(self):
        self.s.custom_quotation=None;frappe.get_all.return_value=['Q-1'];frappe.get_doc.return_value=self.q
        self.q.docstatus=1;self.q.custom_oman_flow=0
        self.assertFalse(flow.guard_dcs_revision(self.s,attach=True));frappe.db.set_value.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
