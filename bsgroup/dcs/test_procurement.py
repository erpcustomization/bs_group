"""Synthetic integration tests; run only on isolated staging."""
import json
from io import BytesIO
from pypdf import PdfWriter

def sample_pdf():
    stream=BytesIO(); writer=PdfWriter(); writer.add_blank_page(width=100,height=100); writer.write(stream); return stream.getvalue()

import unittest
from unittest.mock import patch
import frappe
from frappe.utils.file_manager import save_file
from frappe.utils import add_days, nowdate
from bsgroup import procurement as buying
from bsgroup.dcs import procurement as p
from bsgroup.tests.dcs_fixtures import make_dcs, make_user
from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation

class ProcurementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert frappe.local.site == 'rel1-test.local', 'Run only on the isolated test site'
        frappe.set_user('Administrator')
        frappe.db.savepoint('procurement_suite')
        cls.manager=make_user('zztest-pr-manager@example.com',['Sales Manager'])
        cls.buyer=make_user('zztest-pr-buyer@example.com',['Purchase User'])
        cls.tech=make_user('zztest-pr-tech@example.com',['Technical Engineer'])
        cls.sales=make_user('zztest-pr-sales@example.com',['Sales User'])

    @classmethod
    def tearDownClass(cls):
        frappe.set_user('Administrator')
        frappe.db.rollback(save_point='procurement_suite')

    def setUp(self):
        frappe.set_user('Administrator')
        frappe.db.savepoint('procurement_test')
        self.dcs=make_dcs(suffix='PR-'+frappe.generate_hash(length=8),submit=True,deal_owner=self.manager,
            company='Bits Secure IT Infrastructure LLC - AE',currency='AED',
            items=[dict(item_code='ZZTEST-CLAUDE-DCS-ITEM-A',qty=1,cost_rate=1000,selling_rate=1500)])
        frappe.set_user(self.manager)
        self.q=frappe.get_doc('Quotation',make_quotation(self.dcs.name))
        self.q.flags.ignore_mandatory=True
        self.q.flags.ignore_links=True
        self.q.custom_pipeline_stage='Sent'
        self.q.submit()

    def tearDown(self):
        frappe.set_user('Administrator')
        frappe.db.rollback(save_point='procurement_test')

    def upload(self,q=None):
        q=q or self.q
        f=save_file('ZZTEST-Customer-PO.pdf',sample_pdf(), 'Quotation',q.name,is_private=1,df='custom_customer_po')
        q.custom_customer_po=f.file_url
        q.custom_customer_po_reference='ZZTEST-PO-'+q.name
        return f

    def win(self):
        self.upload()
        self.q.custom_pipeline_stage='Won'
        self.q.save()
        self.dcs.reload()

    def send(self):
        with patch.object(frappe,'get_print',return_value=sample_pdf()), \
             patch.object(p,'costing_pdf',return_value=sample_pdf()):
            return p.send_to_procurement(self.q.name,add_days(nowdate(),7),"Stores - AE")

    def test_won_requires_po_and_has_no_award_side_effect(self):
        self.q.custom_pipeline_stage='Won'
        self.q.custom_customer_po_reference='ZZTEST-PO'
        with self.assertRaises(frappe.ValidationError): self.q.save()
        self.assertNotEqual(frappe.db.get_value('Deal Cost Sheet',self.dcs.name,'custom_award_state'),'Awarded')
        self.assertEqual(frappe.db.get_value('Quotation',self.q.name,'custom_pipeline_stage'),'Sent')

    def test_won_requires_reference(self):
        self.upload();self.q.custom_customer_po_reference='';self.q.custom_pipeline_stage='Won'
        with self.assertRaises(frappe.ValidationError): self.q.save()

    def test_external_and_unrelated_files_are_refused(self):
        self.q.custom_pipeline_stage='Won';self.q.custom_customer_po_reference='ZZTEST-PO'
        self.q.custom_customer_po='https://example.com/po.pdf'
        with self.assertRaises(frappe.ValidationError): self.q.save()
        self.upload();frappe.db.set_value('File',{'file_url':self.q.custom_customer_po},'attached_to_name','another-quotation')
        with self.assertRaises(frappe.ValidationError): self.q.save()

    def test_won_records_award_and_freezes_matching_revision(self):
        self.win()
        self.assertEqual(self.dcs.custom_award_state,'Awarded')
        self.assertEqual(self.dcs.custom_award_reference,self.q.custom_customer_po_reference)
        self.assertEqual(self.dcs.custom_frozen_revision_no,self.dcs.custom_dcs_revision_no)
        self.assertEqual(self.dcs.custom_frozen_total_cost,1000)
        self.assertEqual(self.dcs.custom_frozen_total_selling,1500)

    def test_send_creates_standard_pr_with_private_evidence_and_replays(self):
        self.win();r=self.send();packet=frappe.get_doc(buying.MR,r['name'])
        self.assertFalse(r['already_sent']);self.assertEqual(packet.custom_bsp_quotation,self.q.name)
        self.assertEqual(packet.material_request_type,'Purchase')
        self.assertEqual(packet.docstatus,0)
        files=frappe.get_all('File',filters={'attached_to_doctype':buying.MR,'attached_to_name':packet.name},fields=['is_private','file_url'])
        self.assertEqual(len(files),3);self.assertTrue(all(f.is_private for f in files))
        manifest=json.loads(packet.custom_bsp_source_snapshot)
        self.assertEqual({f['kind'] for f in manifest['files']},{'quotation','customer_po','costing'})
        self.assertEqual(manifest['costing']['total_cost'],1000)
        self.assertEqual(frappe.db.count('Notification Log',{'document_name':packet.name,'for_user':self.buyer}),0)
        self.assertEqual(self.send(),{'name':packet.name,'doctype':buying.MR,'already_sent':True})
        self.assertEqual(frappe.db.count('DCS Governance Event',{'dcs':self.dcs.name,'event_code':'DCS_PROCUREMENT_SENT'}),1)
        self.assertEqual(frappe.db.count(buying.MR,{'custom_deal_cost_sheet':self.dcs.name}),1)
        self.assertEqual(frappe.db.count('Notification Log',{'document_name':packet.name,'for_user':self.buyer}),0)
        frappe.set_user(self.buyer)
        self.assertTrue(frappe.has_permission(buying.MR,'read',doc=packet))
        file=frappe.get_doc('File',{'attached_to_doctype':buying.MR,'attached_to_name':packet.name})
        self.assertTrue(frappe.has_permission('File','read',doc=file))

    def test_unwon_and_unauthorised_send_refused(self):
        with self.assertRaises(frappe.ValidationError): self.send()
        for user in (self.tech,self.sales,'Guest'):
            frappe.set_user(user)
            with self.assertRaises(frappe.PermissionError): self.send()
        self.assertEqual(frappe.db.count(buying.MR,{'custom_deal_cost_sheet':self.dcs.name}),0)

    def test_standard_pr_does_not_depend_on_legacy_notification_recipients(self):
        self.win()
        with patch.object(p,'procurement_users',side_effect=AssertionError('Legacy notification path used')):
            result=self.send()
        self.assertEqual(result['doctype'],buying.MR)
        self.assertEqual(frappe.db.count(buying.MR,{'custom_deal_cost_sheet':self.dcs.name}),1)
        self.assertEqual(frappe.db.count(p.DT,{'dcs':self.dcs.name}),0)

    def test_stale_quote_refused(self):
        self.upload();self.q.custom_pipeline_stage='Won'
        self.q.custom_dcs_revision_reference='ZZTEST-stale-revision'
        with self.assertRaises(frappe.ValidationError): self.q.save()

    def test_packet_and_files_immutable_and_marker_not_forgeable(self):
        self.win();r=self.send();self.q.reload()
        with self.assertRaises(frappe.PermissionError):
            self.q.custom_purchase_request='FAKE';self.q.save()
        packet=frappe.get_doc(buying.MR,r['name']);packet.custom_bsp_customer_po='FORGED'
        with self.assertRaises(frappe.PermissionError): packet.save(ignore_permissions=True)
        file=frappe.get_doc('File',{'attached_to_doctype':buying.MR,'attached_to_name':packet.name})
        with self.assertRaises(frappe.PermissionError): file.delete(ignore_permissions=True)
        self.q.reload();self.q.custom_customer_po_reference='replacement'
        with self.assertRaises(frappe.ValidationError): self.q.save()

    def test_won_source_po_cannot_be_deleted_or_published(self):
        self.win();file=frappe.get_doc('File',{'file_url':self.q.custom_customer_po,'attached_to_doctype':'Quotation'})
        with self.assertRaises(frappe.PermissionError): file.delete(ignore_permissions=True)
        file.is_private=0
        with self.assertRaises(frappe.PermissionError): file.save(ignore_permissions=True)

    def test_snapshot_excludes_confidential_obligations(self):
        self.win();data=p.costing_snapshot(self.dcs)
        self.assertEqual(set(data),{'dcs','company','currency','subject','revision','revision_no','award_sequence','total_cost','total_selling','items','resources','additional_charges'})
        frappe.set_user(self.tech)
        self.assertFalse(p.has_permission(frappe._dict(dcs=self.dcs.name,quotation=self.q.name,company=self.dcs.company),'read'))



    def test_print_failure_does_not_create_partial_request(self):
        self.win()
        with patch.object(frappe,'get_print',side_effect=RuntimeError('Synthetic PDF failure')):
            with self.assertRaises(RuntimeError): p.send_to_procurement(self.q.name,add_days(nowdate(),7),"Stores - AE")
        self.assertEqual(frappe.db.count(buying.MR,{'custom_deal_cost_sheet':self.dcs.name}),0)
        self.assertFalse(frappe.db.get_value('Quotation',self.q.name,'custom_bsp_material_request'))

    def test_sent_quotation_cancellation_is_refused(self):
        self.win();self.send();self.q.reload()
        with self.assertRaises(frappe.ValidationError): self.q.cancel()


    def test_reaward_after_reversal_records_a_new_award_sequence(self):
        from bsgroup.api.dcs.award import dcs_award_reversal
        self.win()
        frappe.set_user('Administrator')
        md=make_user('zztest-pr-md@example.com',['Managing Director','Sales Manager'])
        frappe.set_user(md)
        result=dcs_award_reversal(dcs=self.dcs.name,reason='ZZTEST reversal',acknowledge=1,mode='reverse')
        self.assertEqual(result['ok'],1,result)
        frappe.set_user(self.manager)
        self.q.reload();self.q.custom_pipeline_stage='Follow-up';self.q.save()
        self.q.custom_pipeline_stage='Won';self.q.save();self.dcs.reload()
        self.assertEqual(self.dcs.custom_award_sequence_no,2)
        self.assertEqual(self.dcs.custom_award_state,'Awarded')


    def test_existing_letter_award_accepts_customer_po_reference(self):
        from bsgroup.api.dcs.award import dcs_record_award
        result=dcs_record_award(dcs=self.dcs.name,award_reference='ZZTEST-LETTER-OF-AWARD',evidence_type='Letter of Award')
        self.assertEqual(result['ok'],1,result)
        self.win()
        self.assertEqual(self.dcs.custom_award_reference,'ZZTEST-LETTER-OF-AWARD')
        self.assertNotEqual(self.dcs.custom_award_reference,self.q.custom_customer_po_reference)
        self.assertTrue(self.send()['name'])


    def test_costing_pdf_preserves_omr_precision_and_plain_descriptions(self):
        self.win();data=p.costing_snapshot(self.dcs);data['currency']='OMR'
        data['total_cost']=970.96;data['total_selling']=1138.425
        data['items'][0]['description']='<p>Installed equipment</p>'
        with patch('frappe.utils.pdf.get_pdf',return_value=b'PDF') as render:
            p.costing_pdf(data)
        html=render.call_args.args[0]
        self.assertIn('970.960',html);self.assertIn('1,138.425',html)
        self.assertIn('Installed equipment',html);self.assertNotIn('&lt;p&gt;',html)
