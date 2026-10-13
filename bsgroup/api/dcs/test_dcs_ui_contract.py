"""Backend contracts consumed by the DCS presentation."""
from unittest.mock import patch
import frappe
from frappe.tests import IntegrationTestCase
from bsgroup.tests.dcs_fixtures import ensure, make_dcs, make_user, make_reporting_line
from bsgroup.dcs.commercial_authority import authorised_position

S4="bsgroup.api.dcs.approval.dcs_screen4"
S5="bsgroup.api.dcs.handover.dcs_screen5"
REVISE="bsgroup.api.dcs.negotiation.dcs_apply_revision"
DECIDE="bsgroup.api.dcs.approval.dcs_approval_decision"

class IntegrationTestDCSUIContract(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records",return_value=[]):
            super().setUpClass()
        for role in ["Managing Director","Commercial Controller","Sales Manager","Technical Engineer"]:
            ensure("Role",role,{"role_name":role},insert=False)
        cls.md=make_user("zztest-ui-md@example.com",["Managing Director","Sales Manager"])
        cls.cc=make_user("zztest-ui-cc@example.com",["Commercial Controller"])
        cls.tech=make_user("zztest-ui-tech@example.com",["Technical Engineer"])
        cls.presales=make_user("zztest-ui-presales@example.com",["Presales"])

        cls.manager = make_user("zztest-ui-manager@example.com", ["Employee"])

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        make_reporting_line(self.md, self.manager)
        make_reporting_line(self.presales, self.manager)
        self.doc=make_dcs(suffix="UI"+frappe.generate_hash(length=6),submit=True)

    def decide(self, **args):
        actor = frappe.session.user
        frappe.set_user(self.manager)
        try:
            return frappe.call("bsgroup.api.dcs.approval.dcs_approval_decision", dcs=self.doc.name, **args)
        finally:
            frappe.set_user(actor)

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def below_floor(self):
        frappe.set_user(self.md)
        result=frappe.call(REVISE,dcs=self.doc.name,source="Vendor",reason="ZZTEST UI margin trigger",new_total_cost=1250)
        self.assertEqual(result["ok"],1,result)

    def test_effective_five_tab_layout_and_field_retention(self):
        meta=frappe.get_meta("Deal Cost Sheet")
        self.assertEqual([f.label for f in meta.fields if f.fieldtype=="Tab Break"],
            ["Deal & Scope","Costing","Revisions","Approval","Award & Handover","Overview"])
        self.assertTrue(meta.has_field("custom_approved_revision_no"))
        self.assertTrue(meta.has_field("custom_superseded_by"))
        self.assertEqual(meta.get_field("addtional_charges").label,"Additional Charges")

    def test_below_floor_approval_signal_is_current_and_delivery_remains_separate(self):
        self.below_floor()
        screen=frappe.call(S5,dcs=self.doc.name)
        self.assertEqual(screen["living"]["authorised_position"],0)
        self.assertEqual(screen["living"]["approval_required"],"Manager")
        self.assertEqual(screen["authority"]["can_set_delivery_owner"],1)
        result=self.decide(action="Approve",reason="ZZTEST UI MD exception")
        self.assertEqual(result["ok"],1,result)
        screen=frappe.call(S5,dcs=self.doc.name)
        self.assertEqual(screen["living"]["authorised_position"],1)
        self.assertEqual(screen["living"]["margin_gate"],"Blocked")
        self.assertEqual(screen["states"]["customer_award"],"Not Awarded")

    def test_cc_receives_return_without_final_manager_actions(self):
        self.below_floor()
        frappe.set_user(self.cc)
        screen=frappe.call(S4,dcs=self.doc.name)
        self.assertEqual(screen["ok"],1,screen)
        self.assertEqual([a["key"] for a in screen["actions"]],["Return for Rework"])

    def test_rejected_revision_has_no_final_decision_buttons_and_recovery_recalculates(self):
        self.below_floor()
        result=self.decide(action="Reject",reason="ZZTEST UI rejection")
        self.assertEqual(result["ok"],1,result)
        self.doc.reload()
        rejected=self.doc.custom_revision_reference
        self.assertEqual(frappe.call(S4,dcs=self.doc.name)["actions"],[])
        result=frappe.call(REVISE,dcs=self.doc.name,source="Vendor",reason="ZZTEST UI recovery",new_total_cost=1200)
        self.assertEqual(result["ok"],1,result)
        screen=frappe.call(S5,dcs=self.doc.name)
        self.assertEqual(screen["living"]["authorised_position"],1)
        self.assertEqual(screen["living"]["approval_required"],"None")
        self.assertEqual(frappe.db.get_value("DCS Revision",rejected,"approval_state"),"Rejected")

    def test_policy_explains_margin_trigger_and_simple_rejection_process(self):
        self.below_floor()
        screen=frappe.call(S4,dcs=self.doc.name)
        self.assertEqual(screen["deal"]["approval_required"],"Manager")
        self.assertIn("below 20%",screen["why"]["policy_basis"])
        self.assertIn("Manager reapproval is not required",screen["why"]["policy_basis"])
        self.assertNotIn("concession from baseline only",screen["why"]["policy_basis"])

    def test_technical_projection_contains_no_commercial_authority_or_position(self):
        frappe.set_user(self.tech)
        screen=frappe.call(S5,dcs=self.doc.name)
        self.assertEqual(screen["ok"],1,screen)
        self.assertEqual(screen["authority"]["can_set_delivery_owner"],0)
        self.assertEqual(screen["authority"]["can_record_award"],0)
        self.assertNotIn("living",screen)

    def test_legacy_evaluation_initialises_without_changing_totals_or_inventing_movement(self):
        frappe.set_user("Administrator")
        with patch("bsgroup.dcs.baseline.ensure_baseline",return_value={"initialised":0}):
            legacy=make_dcs(suffix="UILEG"+frappe.generate_hash(length=6),submit=True)
        self.assertEqual(legacy.custom_dcs_revision_no or 0,0)
        frappe.set_user(self.md)
        result=frappe.call(REVISE,dcs=legacy.name,source="Internal",
            reason="Evaluate the submitted BOQ baseline without changing its totals.")
        self.assertEqual(result["ok"],1,result)
        legacy.reload()
        self.assertEqual(legacy.custom_working_total_cost,1000)
        self.assertEqual(legacy.custom_working_total_selling,1500)
        self.assertEqual(frappe.db.count("DCS Revision",{"dcs":legacy.name}),1)
        self.assertEqual(frappe.db.get_value("DCS Revision",legacy.custom_revision_reference,"gp_movement"),0)

    def test_duplicate_legacy_renderers_are_retired_with_source_preserved(self):
        for name in ["Deal Cost Sheet - Living DCS Experience", "Deal Cost Sheet Summary Dashboard"]:
            if frappe.db.exists("Client Script",name):
                script=frappe.get_doc("Client Script",name)
                self.assertEqual(script.enabled,0,name)
                self.assertTrue(script.script)

    def test_presales_can_read_current_approval_without_award_authority(self):
        self.below_floor()
        frappe.set_user(self.presales)
        read=frappe.call("bsgroup.api.dcs.living.dcs_screen2",dcs=self.doc.name)
        self.assertEqual(read["ok"],1,read)
        self.assertEqual(read["negotiation_guard"]["authorised_position"],0)
        self.assertEqual(read["negotiation_guard"]["approval_required"],"Manager")
        award=frappe.call(S5,dcs=self.doc.name)
        self.assertEqual(award["ok"],0,award)