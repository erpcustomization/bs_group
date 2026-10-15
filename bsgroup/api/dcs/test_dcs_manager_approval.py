"""Immediate-manager approval and reporting-line contracts."""
from unittest.mock import patch
import frappe
from frappe.tests import IntegrationTestCase
from bsgroup.tests.dcs_fixtures import ensure, make_dcs, make_user
from bsgroup.dcs.manager_approval import resolve_manager, is_assigned_manager
from bsgroup.dcs.commercial_authority import authorised_position

REVISE="bsgroup.api.dcs.negotiation.dcs_apply_revision"
DECIDE="bsgroup.api.dcs.approval.dcs_approval_decision"
READ="bsgroup.api.dcs.approval.dcs_screen4"

class IntegrationTestDCSManagerApproval(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records",return_value=[]):
            super().setUpClass()
        cls.submitter=make_user("zztest-manager-submitter@example.com",["Sales Manager"])
        cls.manager=make_user("zztest-manager-approver@example.com",["Employee"])
        cls.other=make_user("zztest-manager-other@example.com",["Sales Manager","Managing Director"])

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        for user in [self.submitter,self.manager,self.other]:
            frappe.db.set_value("User",user,"enabled",1)
        self.doc=make_dcs(suffix="MANAGER"+frappe.generate_hash(length=6),submit=True)
        company=frappe.db.get_value("Company",{}, "name")
        ensure("Gender","Male",{"gender":"Male"},insert=False)
        self.manager_emp=self.employee(self.manager,company)
        self.submitter_emp=self.employee(self.submitter,company,self.manager_emp)

    def employee(self,user,company,manager=None):
        found=frappe.db.get_value("Employee",{"user_id":user},"name")
        if found:
            frappe.db.set_value("Employee",found,{"reports_to":manager,"status":"Active"})
            return found
        emp=frappe.get_doc({"doctype":"Employee","first_name":"ZZTEST "+user.split("@")[0],
            "gender":"Male","date_of_birth":"1990-01-01","date_of_joining":"2020-01-01",
            "company":company,"status":"Active","user_id":user,"reports_to":manager})
        emp.insert(ignore_permissions=True)
        return emp.name

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def revise(self,cost=1250):
        frappe.set_user(self.submitter)
        result=frappe.call(REVISE,dcs=self.doc.name,source="Vendor",reason="ZZTEST manager routing",new_total_cost=cost)
        self.assertEqual(result["ok"],1,result)
        self.doc.reload()
        return frappe.get_doc("DCS Revision",self.doc.custom_revision_reference)

    def test_reporting_line_snapshot_and_in_app_task(self):
        rev=self.revise()
        self.assertEqual(rev.approval_requirement,"Manager")
        self.assertEqual(rev.approval_manager,self.manager)
        self.assertEqual(rev.submitter_employee,self.submitter_emp)
        self.assertEqual(rev.manager_employee,self.manager_emp)
        self.assertTrue(frappe.db.exists("ToDo",{"reference_type":"DCS Revision","reference_name":rev.name,"allocated_to":self.manager,"status":"Open"}))
        self.assertTrue(frappe.has_permission("Deal Cost Sheet","read",doc=self.doc.name,user=self.manager))
        self.assertFalse(frappe.has_permission("Deal Cost Sheet","write",doc=self.doc.name,user=self.manager))

    def test_only_the_assigned_manager_can_decide(self):
        self.revise()
        for user in [self.submitter,self.other]:
            frappe.set_user(user)
            result=frappe.call(DECIDE,dcs=self.doc.name,action="Approve")
            self.assertEqual(result["ok"],0,result)
        frappe.set_user(self.manager)
        view=frappe.call(READ,dcs=self.doc.name)
        self.assertEqual(view["authority"],"Immediate Manager")
        self.assertIn("Approve",[a["key"] for a in view["actions"]])
        result=frappe.call(DECIDE,dcs=self.doc.name,action="Approve")
        self.assertEqual(result["ok"],1,result)
        self.doc.reload()
        self.assertTrue(authorised_position(self.doc))
        self.assertEqual(self.doc.custom_approved_by,self.manager)
        self.assertFalse(frappe.db.exists("ToDo",{"reference_type":"DCS Revision","reference_name":self.doc.custom_revision_reference,"status":"Open"}))

    def test_reject_revise_recalculate_preserves_rejection_and_removes_reapproval(self):
        old=self.revise()
        frappe.set_user(self.manager)
        self.assertEqual(frappe.call(DECIDE,dcs=self.doc.name,action="Reject",reason="Recover margin")["ok"],1)
        new=self.revise(1200)
        self.assertEqual(new.approval_requirement,"None")
        self.assertEqual(frappe.db.get_value("DCS Revision",old.name,"approval_state"),"Rejected")
        self.assertTrue(authorised_position(self.doc))
        self.assertFalse(frappe.db.exists("ToDo",{"reference_type":"DCS Revision","reference_name":new.name,"status":"Open"}))

    def test_revised_below_floor_still_requires_manager_approval(self):
        old=self.revise()
        frappe.set_user(self.manager)
        self.assertEqual(frappe.call(DECIDE,dcs=self.doc.name,action="Reject",reason="Revise")["ok"],1)
        new=self.revise(1240)
        self.assertEqual(new.approval_manager,self.manager)
        self.assertEqual(self.doc.custom_approval_state,"Pending Manager")
        self.assertFalse(authorised_position(self.doc))

    def test_snapshot_cannot_be_forged_or_changed_by_reporting_line_edits(self):
        rev=self.revise()
        frappe.set_user("Administrator")
        frappe.db.set_value("Employee",self.submitter_emp,"reports_to","")
        self.assertTrue(is_assigned_manager(self.doc,self.manager))
        rev.approval_manager=self.other
        with self.assertRaises(frappe.ValidationError):
            rev.save(ignore_permissions=True)

    def test_missing_manager_blocks_decision_and_creates_no_task(self):
        frappe.db.set_value("Employee",self.submitter_emp,"reports_to","")
        rev=self.revise()
        self.assertFalse(rev.approval_manager)
        self.assertIn("Reports To",rev.approval_routing_error)
        self.assertFalse(frappe.db.exists("ToDo",{"reference_type":"DCS Revision","reference_name":rev.name}))
        frappe.set_user(self.other)
        self.assertEqual(frappe.call(DECIDE,dcs=self.doc.name,action="Approve")["ok"],0)

    def test_disabled_manager_cannot_decide(self):
        self.revise()
        frappe.set_user("Administrator")
        frappe.db.set_value("User",self.manager,"enabled",0)
        self.assertFalse(is_assigned_manager(self.doc,self.manager))
        result=resolve_manager(self.submitter)
        self.assertIn("disabled",result["approval_routing_error"])


    def test_initial_below_floor_routes_the_submitter_to_manager(self):
        frappe.set_user(self.submitter)
        doc=make_dcs(suffix="MANAGERINITIAL"+frappe.generate_hash(length=6),submit=False)
        doc.items[0].cost_rate=1250
        doc.save(ignore_permissions=True)
        doc.submit()
        doc.reload()
        self.assertEqual(doc.custom_approval_required,"Manager")
        self.assertEqual(frappe.db.get_value("DCS Revision",doc.custom_revision_reference,"approval_manager"),self.manager)

    def test_missing_route_can_be_repaired_only_by_submitter(self):
        frappe.db.set_value("Employee",self.submitter_emp,"reports_to","")
        rev=self.revise()
        frappe.set_user("Administrator")
        frappe.db.set_value("Employee",self.submitter_emp,"reports_to",self.manager_emp)
        frappe.set_user(self.other)
        denied=frappe.call("bsgroup.dcs.manager_approval.dcs_refresh_manager_route",dcs=self.doc.name)
        self.assertEqual(denied["ok"],0,denied)
        frappe.set_user(self.submitter)
        result=frappe.call("bsgroup.dcs.manager_approval.dcs_refresh_manager_route",dcs=self.doc.name)
        self.assertEqual(result["ok"],1,result)
        rev.reload()
        self.assertEqual(rev.approval_manager,self.manager)
        self.assertTrue(frappe.db.exists("ToDo",{"reference_type":"DCS Revision","reference_name":rev.name,"allocated_to":self.manager,"status":"Open"}))

    def test_manager_receives_only_assigned_deal_and_no_email(self):
        before=frappe.db.count("Email Queue")
        self.revise()
        self.assertEqual(frappe.db.count("Email Queue"),before)
        frappe.set_user("Administrator")
        other=make_dcs(suffix="MANAGEROTHER"+frappe.generate_hash(length=6),submit=True)
        self.assertFalse(frappe.has_permission("Deal Cost Sheet","read",doc=other.name,user=self.manager))
        frappe.set_user(self.manager)
        own=frappe.call("bsgroup.api.dcs.living.dcs_screen2",dcs=self.doc.name)
        self.assertEqual(own["ok"],1,own)
        denied=frappe.call("bsgroup.api.dcs.living.dcs_screen2",dcs=other.name)
        self.assertEqual(denied["ok"],0,denied)


    def test_reportee_sees_manager_route_without_gaining_cost_projection(self):
        from bsgroup.tests.dcs_fixtures import make_reporting_line
        frappe.set_user("Administrator")
        reporter=make_user("zztest-manager-reduced@example.com",["Sales User"])
        make_reporting_line(reporter,self.manager)
        frappe.set_user(reporter)
        result=frappe.call(REVISE,dcs=self.doc.name,source="Customer",reason="ZZTEST reduced reportee",new_total_selling=1200)
        self.assertEqual(result["ok"],1,result)
        view=frappe.call(READ,dcs=self.doc.name)
        self.assertEqual(view["projection"],"approval-routing",view)
        self.assertEqual(view["manager_route"]["approval_manager"],self.manager)
        self.assertNotIn("current",view)
        self.assertNotIn("previous_approved",view)
        self.assertEqual(view["actions"],[])

    def test_caller_cannot_choose_a_different_manager(self):
        frappe.set_user(self.submitter)
        result=frappe.call(REVISE,dcs=self.doc.name,source="Vendor",reason="ZZTEST spoofed manager",
                          new_total_cost=1250,approval_manager=self.other)
        self.assertEqual(result["ok"],1,result)
        self.doc.reload()
        self.assertEqual(frappe.db.get_value("DCS Revision",self.doc.custom_revision_reference,"approval_manager"),self.manager)


    def test_approval_rechecks_manager_after_sheet_lock(self):
        self.revise()
        frappe.set_user(self.manager)
        with patch("bsgroup.api.dcs.approval.is_assigned_manager",side_effect=[True,False]):
            result=frappe.call(DECIDE,dcs=self.doc.name,action="Approve")
        self.assertEqual(result["ok"],0,result)
        self.doc.reload()
        self.assertNotEqual(self.doc.custom_approval_state,"Approved")

    def test_pending_migration_is_idempotent_and_preserves_final_history(self):
        from bsgroup.patches.v0_1.dcs_manager_approval import execute
        rev=self.revise()
        frappe.set_user("Administrator")
        frappe.db.set_value("DCS Revision",rev.name,{"approval_policy":"","approval_manager":"",
            "approval_requirement":"Managing Director","approval_state":"Pending Endorsement"})
        frappe.db.set_value("Deal Cost Sheet",self.doc.name,{"custom_approval_required":"Managing Director",
            "custom_approval_state":"Pending Endorsement"})
        execute()
        self.doc.reload()
        self.assertEqual(self.doc.custom_approval_required,"Manager")
        self.assertEqual(frappe.db.get_value("DCS Revision",rev.name,"approval_manager"),self.manager)
        count=frappe.db.count("DCS Governance Event",{"dcs":self.doc.name,"event_code":"DCS_APPROVAL_ROUTED_TO_MANAGER"})
        execute()
        self.assertEqual(frappe.db.count("DCS Governance Event",{"dcs":self.doc.name,"event_code":"DCS_APPROVAL_ROUTED_TO_MANAGER"}),count)
        frappe.set_user(self.manager)
        self.assertEqual(frappe.call(DECIDE,dcs=self.doc.name,action="Approve")["ok"],1)
        frappe.set_user("Administrator")
        history=frappe.db.get_value("DCS Revision",rev.name,["approval_state","decided_by","decided_on","decision_reason"],as_dict=True)
        execute()
        self.assertEqual(frappe.db.get_value("DCS Revision",rev.name,list(history),as_dict=True),history)
    def test_shared_account_exception_routes_only_to_configured_manager(self):
        with patch("bsgroup.dcs.manager_approval.SHARED_ACCOUNT_MANAGERS", {self.submitter: self.manager}):
            frappe.db.set_value("Employee", self.submitter_emp, "reports_to", "")
            rev = self.revise()
            self.assertEqual(rev.approval_manager, self.manager)
            self.assertFalse(rev.submitter_employee)
            self.assertEqual(rev.manager_employee, self.manager_emp)
            frappe.set_user(self.manager)
            self.assertEqual(frappe.call(DECIDE, dcs=self.doc.name, action="Approve")["ok"], 1)

    def test_shared_account_exception_refuses_self_and_disabled_manager(self):
        with patch("bsgroup.dcs.manager_approval.SHARED_ACCOUNT_MANAGERS", {self.submitter: self.submitter}):
            self.assertTrue(resolve_manager(self.submitter)["approval_routing_error"])
        frappe.db.set_value("User", self.manager, "enabled", 0)
        with patch("bsgroup.dcs.manager_approval.SHARED_ACCOUNT_MANAGERS", {self.submitter: self.manager}):
            route = resolve_manager(self.submitter)
            self.assertIn("disabled", route["approval_routing_error"])
            self.assertFalse(route["approval_manager"])

    def test_shared_account_exception_does_not_change_other_reporting_lines(self):
        with patch("bsgroup.dcs.manager_approval.SHARED_ACCOUNT_MANAGERS", {"zztest-shared@example.com": self.other}):
            route = resolve_manager(self.submitter)
            self.assertEqual(route["approval_manager"], self.manager)
            self.assertEqual(route["submitter_employee"], self.submitter_emp)
