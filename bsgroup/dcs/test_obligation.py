"""Synthetic transaction tests. Run only on isolated staging."""
import json
import unittest
from unittest.mock import patch
import frappe
from bsgroup.dcs import obligation as o
from frappe.utils import flt
from bsgroup.tests.dcs_fixtures import make_dcs, make_user

class ObligationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        frappe.set_user("Administrator")
        cls.sales=make_user("zztest-c-sales@example.com",["Sales User"])
        cls.other=make_user("zztest-c-other@example.com",["Sales User"])
        cls.finance=make_user("zztest-c-finance@example.com",["Commercial Controller"])
        cls.md=make_user("zztest-c-md@example.com",["Managing Director"])
        cls.ops=make_user("zztest-c-ops@example.com",["Operations Manager"])
        cls.admin=make_user("zztest-c-admin@example.com",["System Manager"])
        cls.presales=make_user("zztest-c-presales@example.com",["Presales"])
        cls.tech=make_user("zztest-c-tech@example.com",["Technical Engineer"])
        cls.finance_patch=patch.object(o,"FINANCE",cls.finance)
        cls.finance_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.finance_patch.stop()
        frappe.set_user("Administrator")

    def setUp(self):
        frappe.set_user("Administrator")
        frappe.db.savepoint("phase_c_test")
        self.sheet=make_dcs(suffix="C-"+frappe.generate_hash(length=8),deal_owner=self.sales,submit=True)
        self.values=dict(obligation_type="Consulting",payee="ZZTEST Synthetic Partner",
            agreement_reference="ZZTEST-Agreement",calculation_method="Fixed amount",
            fixed_amount=100,percentage=0,payment_conditions="Synthetic milestone",
            reason="Synthetic forecast")
        frappe.set_user(self.sales)

    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point="phase_c_test")

    def proposal(self, **values):
        return o.save_proposal(self.sheet.name,{**self.values,**values})

    def move(self, r, action, user=None):
        if user: frappe.set_user(user)
        return o.transition(r["name"],action,r["revision"],"ZZTEST "+action)

    def approved(self, **values):
        r=self.proposal(**values)
        r=self.move(r,"Submit")
        r=self.move(r,"Finance Approve",self.finance)
        if r["status"]=="Pending MD":r=self.move(r,"MD Approve",self.md)
        return r

    def test_forecast_is_not_a_commitment(self):
        self.proposal()
        f=o.financials(self.sheet)
        self.assertEqual(f["delivery_contribution"],500)
        self.assertEqual(f["forecast_obligations"],100)
        self.assertEqual(f["approved_commitments"],0)
        self.assertEqual(f["forecast_net_contribution"],400)

    def test_finance_approval_at_above_floor(self):
        r=self.approved()
        self.assertEqual(r["status"],"Approved")
        self.assertEqual(o.financials(self.sheet)["approved_commitments"],100)
        o.assert_clearance(self.sheet)

    def test_exact_20_does_not_escalate(self):
        r=self.approved(fixed_amount=200)
        doc=frappe.get_doc(o.DT,r["name"])
        self.assertEqual(doc.status,"Approved")
        self.assertFalse(doc.md_by)
        self.assertEqual(o.financials(self.sheet)["forecast_net_margin"],20)

    def test_below_floor_needs_finance_then_md(self):
        r=self.proposal(fixed_amount=201)
        r=self.move(r,"Submit")
        with self.assertRaises(frappe.PermissionError):self.move(r,"MD Approve",self.md)
        r=self.move(r,"Finance Approve",self.finance)
        self.assertEqual(r["status"],"Pending MD")
        self.assertEqual(o.financials(self.sheet)["approved_commitments"],0)
        with self.assertRaises(frappe.ValidationError):o.assert_clearance(self.sheet)
        r=self.move(r,"MD Approve",self.md)
        self.assertEqual(r["status"],"Approved")
        o.assert_clearance(self.sheet)

    def test_multiple_obligations_use_combined_net_margin(self):
        self.approved(fixed_amount=150)
        frappe.set_user(self.sales)
        r=self.proposal(fixed_amount=100);r=self.move(r,"Submit")
        r=self.move(r,"Finance Approve",self.finance)
        self.assertEqual(r["status"],"Pending MD")

    def test_self_approval_finance_denied(self):
        frappe.set_user(self.finance)
        r=self.proposal();r=self.move(r,"Submit")
        with self.assertRaises(frappe.PermissionError):self.move(r,"Finance Approve")

    def test_self_approval_md_denied(self):
        frappe.set_user(self.md)
        r=self.proposal(fixed_amount=201);r=self.move(r,"Submit")
        r=self.move(r,"Finance Approve",self.finance)
        with self.assertRaises(frappe.PermissionError):self.move(r,"MD Approve",self.md)

    def test_other_sales_owner_denied_even_if_shared(self):
        r=self.proposal()
        frappe.set_user(self.other)
        self.assertEqual(o.overview(self.sheet.name),{})
        with self.assertRaises(frappe.PermissionError):o.detail(r["name"])
        self.assertFalse(frappe.has_permission(o.DT,"read",doc=r["name"]))

    def test_excluded_roles_all_routes(self):
        r=self.proposal()
        for user in [self.ops,self.presales,self.tech,self.admin,"Guest","manikandan@bitssecureit.com"]:
            with self.subTest(user=user):
                frappe.set_user(user)
                self.assertEqual(o.overview(self.sheet.name),{})
                with self.assertRaises(frappe.PermissionError):o.detail(r["name"])
                with self.assertRaises(frappe.PermissionError):self.proposal()
                self.assertFalse(frappe.has_permission(o.DT,"read",doc=r["name"]))
                if user!="Guest":
                    try:rows=frappe.get_list(o.DT,fields=["name","fixed_amount"],limit_page_length=0)
                    except frappe.PermissionError:rows=[]
                    self.assertEqual(rows,[])

    def test_explicit_deny_overrides_md_and_sales_roles(self):
        with patch("frappe.get_roles",return_value=["Managing Director","Sales User","System Manager"]):
            self.assertFalse(o.eligible("manikandan@bitssecureit.com"))

    def test_native_write_flags_cannot_forge_approval(self):
        r=self.proposal()
        doc=frappe.get_doc(o.DT,r["name"])
        doc.status="Approved";doc.flags.dcs_api_write=True;doc.flags.ignore_permissions=True
        with self.assertRaises(frappe.PermissionError):doc.save(ignore_permissions=True)

    def test_native_creation_cannot_forge_proposal(self):
        doc=frappe.get_doc({"doctype":o.DT,"dcs":self.sheet.name,"status":"Approved"})
        doc.flags.dcs_api_write=True
        with self.assertRaises(frappe.PermissionError):doc.insert(ignore_permissions=True)

    def test_export_print_share_not_allowed(self):
        r=self.proposal()
        for right in ["export","print","email","share","write","delete"]:
            self.assertFalse(frappe.has_permission(o.DT,right,doc=r["name"]))

    def test_revisions_preserve_committed_and_invalidate_decision(self):
        r=self.approved()
        frappe.set_user(self.sales)
        r=o.save_proposal(self.sheet.name,{**self.values,"fixed_amount":150},r["name"],r["revision"])
        f=o.financials(self.sheet)
        self.assertEqual(f["approved_commitments"],100)
        self.assertEqual(f["forecast_obligations"],150)
        with self.assertRaises(frappe.ValidationError):o.assert_clearance(self.sheet)

    def test_stale_concurrent_edit_denied(self):
        r=self.proposal()
        o.save_proposal(self.sheet.name,self.values,r["name"],r["revision"])
        with self.assertRaises(frappe.ValidationError):
            o.save_proposal(self.sheet.name,self.values,r["name"],r["revision"])

    def test_duplicate_decision_denied(self):
        r=self.proposal();r=self.move(r,"Submit")
        self.move(r,"Finance Approve",self.finance)
        with self.assertRaises(frappe.ValidationError):self.move(r,"Finance Approve",self.finance)

    def test_delivery_revision_invalidates_approval(self):
        self.approved()
        self.sheet.custom_working_total_selling=1400
        with self.assertRaises(frappe.ValidationError):o.assert_clearance(self.sheet)

    def test_pending_md_position_change_cannot_bypass_finance(self):
        r=self.proposal(fixed_amount=201);r=self.move(r,"Submit")
        r=self.move(r,"Finance Approve",self.finance)
        frappe.db.set_value("Deal Cost Sheet",self.sheet.name,"custom_working_total_selling",1400)
        with self.assertRaises(frappe.ValidationError):self.move(r,"MD Approve",self.md)

    def test_rejection_excludes_unapproved_forecast(self):
        r=self.proposal();r=self.move(r,"Submit")
        r=self.move(r,"Reject",self.finance)
        self.assertEqual(o.financials(self.sheet)["forecast_obligations"],0)
        o.assert_clearance(self.sheet)

    def test_audit_history_is_private_and_immutable(self):
        r=self.approved()
        events=frappe.get_all(o.EVENT,filters={"obligation":r["name"]},fields=["name","snapshot"])
        self.assertEqual(len(events),3)
        event=frappe.get_doc(o.EVENT,events[0].name)
        event.reason="Forged"
        with self.assertRaises(frappe.PermissionError):event.save(ignore_permissions=True)
        with self.assertRaises(frappe.PermissionError):frappe.delete_doc(o.EVENT,event.name,ignore_permissions=True)
        frappe.set_user(self.admin)
        self.assertFalse(frappe.has_permission(o.EVENT,"read",doc=event))
        self.assertEqual(frappe.get_list(o.EVENT,fields=["name"]),[])

    def test_no_public_history_or_dcs_amount_changes(self):
        before=self.sheet.as_dict()
        r=self.approved()
        fresh=frappe.get_doc("Deal Cost Sheet",self.sheet.name).as_dict()
        for field in ["total_cost","total_selling","margin_value","margin_percent","custom_working_total_cost","custom_working_total_selling"]:
            self.assertEqual(before[field],fresh[field])
        for dt,fields in o.REFS.items():
            self.assertFalse(frappe.db.exists(dt,{fields[0]:o.DT,fields[1]:r["name"]}))

    def test_auxiliary_records_cannot_leak(self):
        r=self.proposal()
        for dt,fields in o.REFS.items():
            if dt=="File":continue
            doc=frappe.get_doc({"doctype":dt,fields[0]:o.DT,fields[1]:r["name"]})
            with self.assertRaises(frappe.PermissionError):o.auxiliary_guard(doc)

    def test_attachment_must_be_private(self):
        r=self.proposal()
        doc=frappe.get_doc(dict(doctype="File",file_name="ZZTEST-evidence.txt",is_private=0,
            attached_to_doctype=o.DT,attached_to_name=r["name"]))
        with self.assertRaises(frappe.ValidationError):o.auxiliary_guard(doc)

    def test_private_attachment_owner_cannot_bypass(self):
        r=self.proposal()
        file=frappe.get_doc(dict(doctype="File",file_name="ZZTEST.txt",is_private=1,
            attached_to_doctype=o.DT,attached_to_name=r["name"],owner=self.other))
        frappe.set_user(self.other)
        self.assertFalse(o.auxiliary_permission(file,"read"))

    def test_omr_percentage_and_zero_selling(self):
        self.sheet.currency="OMR";self.sheet.custom_working_total_selling=1234.567
        doc=frappe._dict(calculation_method="Percentage of customer selling",percentage=1,currency="OMR")
        self.assertEqual(o.amount(doc,1234.567),12.346)
        self.sheet.custom_working_total_selling=0
        self.assertIsNone(o.financials(self.sheet)["forecast_net_margin"])

    def test_invalid_amounts_and_mass_assignment(self):
        for value in [-1,"NaN","inf","bad"]:
            with self.subTest(value=value),self.assertRaises(frappe.ValidationError):
                self.proposal(fixed_amount=value)
        with self.assertRaises(frappe.ValidationError):self.proposal(status="Approved")
        with self.assertRaises(frappe.ValidationError):self.proposal(percentage=101)

    def test_awarded_sheet_refuses_new_obligations(self):
        frappe.db.set_value("Deal Cost Sheet",self.sheet.name,"custom_award_state","Awarded")
        with self.assertRaises(frappe.ValidationError):self.proposal()

    def test_no_obligation_clearance_preserves_existing_behavior(self):
        o.assert_clearance(self.sheet)

    def test_real_private_upload_and_download_permissions(self):
        import base64
        r=self.proposal()
        file=o.upload_support(r["name"],"ZZTEST-private.txt",base64.b64encode(b"ZZTEST confidential evidence").decode())
        saved=frappe.get_doc("File",{"file_url":file["file_url"]})
        self.assertTrue(saved.is_private)
        self.assertTrue(saved.is_downloadable())
        self.assertEqual(len(o.detail(r["name"])["files"]),1)
        for user in [self.other,self.ops,self.admin,"manikandan@bitssecureit.com"]:
            frappe.set_user(user)
            self.assertFalse(saved.is_downloadable())
            self.assertFalse(frappe.has_permission("File","read",doc=saved))
        frappe.set_user(self.sales)
        self.assertFalse(frappe.db.exists("Comment",{"reference_doctype":o.DT,"reference_name":r["name"]}))

    def test_attachment_relink_public_copy_and_shared_owner_refused(self):
        import base64
        r=self.proposal()
        file=o.upload_support(r["name"],"ZZTEST-private-copy.txt",base64.b64encode(b"ZZTEST protected copy").decode())
        saved=frappe.get_doc("File",{"file_url":file["file_url"]})
        alias=frappe.copy_doc(saved);alias.attached_to_doctype="Deal Cost Sheet";alias.attached_to_name=self.sheet.name
        with self.assertRaises(frappe.PermissionError):alias.insert(ignore_permissions=True)
        saved.is_private=0
        with self.assertRaises(frappe.ValidationError):saved.save(ignore_permissions=True)

    def test_quotation_has_only_delivery_prices(self):
        from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation
        self.proposal()
        q=frappe.get_doc("Quotation",make_quotation(self.sheet.name))
        self.assertEqual(q.total,1500)
        self.assertEqual(sum(flt(r.custom_cost_rate)*flt(r.qty) for r in q.items),1000)
        text=json.dumps(q.as_dict(),default=str)
        self.assertNotIn("ZZTEST Synthetic Partner",text)
        self.assertNotIn("ZZTEST-Agreement",text)
        self.assertNotIn("forecast_obligations",text)

    def test_quotation_submit_requires_current_clearance(self):
        from bsgroup.dcs.quotation_control import validate_quotation
        r=self.proposal()
        q=frappe._dict(docstatus=1,custom_deal_cost_sheet=self.sheet.name)
        with self.assertRaises(frappe.ValidationError):validate_quotation(q)

    def test_amendment_cannot_orphan_obligations(self):
        self.proposal()
        with self.assertRaises(frappe.ValidationError):
            o.guard_amendment(frappe._dict(amended_from=self.sheet.name))

    def test_operations_keep_native_delivery_fields(self):
        frappe.set_user("manikandan@bitssecureit.com")
        doc=frappe.get_doc("Deal Cost Sheet",self.sheet.name)
        doc.apply_fieldlevel_read_permissions()
        self.assertEqual(doc.total_cost,1000)
        self.assertEqual(doc.total_selling,1500)
        self.assertEqual(doc.margin_value,500)
        from bsgroup.api.dcs.living import dcs_screen2
        screen=dcs_screen2(dcs=self.sheet.name)
        self.assertEqual(screen["ok"],1)
        self.assertEqual(screen["header"]["money"]["working_gp"],500)
        self.assertNotIn("forecast_obligations",json.dumps(screen,default=str))

    def test_operations_response_does_not_change_with_obligation(self):
        from bsgroup.api.dcs.living import dcs_screen2
        frappe.set_user("manikandan@bitssecureit.com")
        before=dcs_screen2(dcs=self.sheet.name)
        frappe.set_user(self.sales);self.proposal()
        frappe.set_user("manikandan@bitssecureit.com")
        after=dcs_screen2(dcs=self.sheet.name)
        self.assertEqual(before,after)

    def test_settlement_separate_from_forecast_and_commitment(self):
        r=self.approved()
        frappe.set_user(self.finance)
        result=o.record_settlement(r["name"],r["revision"],80,50,"ZZTEST Finance voucher")
        self.assertEqual(result["balance"],50)
        self.assertEqual(o.financials(self.sheet)["approved_commitments"],100)
        self.assertEqual(o.financials(self.sheet)["forecast_obligations"],100)
        o.assert_clearance(self.sheet)

    def test_settlement_overcommitment_and_unauthorized_refused(self):
        r=self.approved()
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.PermissionError):o.record_settlement(r["name"],r["revision"],100,50,"ZZTEST")
        frappe.set_user(self.finance)
        with self.assertRaises(frappe.ValidationError):o.record_settlement(r["name"],r["revision"],101,50,"ZZTEST")
        with self.assertRaises(frappe.ValidationError):o.record_settlement(r["name"],r["revision"],50,51,"ZZTEST")

    def test_only_proposal_maker_can_submit(self):
        r=self.proposal()
        with self.assertRaises(frappe.PermissionError):self.move(r,"Submit",self.finance)

    def test_currency_mismatch_cannot_be_summed(self):
        r=self.proposal()
        self.sheet.currency="OMR"
        with self.assertRaises(frappe.ValidationError):o.financials(self.sheet)

    def test_revised_commitment_cannot_drop_below_settlement(self):
        r=self.approved()
        frappe.set_user(self.finance)
        r=o.record_settlement(r["name"],r["revision"],80,50,"ZZTEST")
        frappe.set_user(self.sales)
        with self.assertRaises(frappe.ValidationError):
            o.save_proposal(self.sheet.name,{**self.values,"fixed_amount":40},r["name"],r["revision"])

    def test_legacy_commercial_charge_hold_prevents_double_count(self):
        self.sheet.append("addtional_charges",{"description":"Consultant charges - project expense","amount":100})
        doc=frappe.get_doc({"doctype":o.DT,**self.values,"currency":"AED"})
        with self.assertRaises(frappe.ValidationError):o.validate_terms(doc,self.sheet)

    def test_assigned_sales_owner_gets_delivery_overview(self):
        from bsgroup.api.dcs.living import dcs_screen2
        screen=dcs_screen2(dcs=self.sheet.name)
        self.assertEqual(screen["projection"],"commercial")
        self.assertEqual(screen["header"]["money"]["working_gp"],500)

    def test_generic_exports_are_denied_even_for_system_manager(self):
        frappe.set_user(self.admin)
        with patch.dict(frappe.local.form_dict,{"doctype":o.DT}):
            with self.assertRaises(frappe.PermissionError):o.export_query()
        with self.assertRaises(frappe.PermissionError):o.export_data(o.EVENT)

    def test_unrelated_report_export_is_delegated_unchanged(self):
        with patch.dict(frappe.local.form_dict,{"doctype":"Deal Cost Sheet"}):
            with patch("frappe.desk.reportview.export_query",return_value="original-export") as core:
                self.assertEqual(o.export_query(),"original-export")
                core.assert_called_once_with()
