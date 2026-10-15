"""Regression for the October browser audit; staging fixtures only."""
import json
from unittest.mock import patch
import frappe
from frappe.tests import IntegrationTestCase
from bsgroup.tests.dcs_fixtures import make_dcs, make_user, make_reporting_line
from bsgroup.api.dcs.test_dcs_vendor_revision import make_quotation_for

class IntegrationTestDCSBrowserAudit(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        with patch("frappe.tests.classes.integration_test_case.make_test_records", return_value=[]):
            super().setUpClass()
        cls.actor=make_user("zztest-browser-salesmgr@example.com", ["Sales Manager","Managing Director"])
        cls.manager=make_user("zztest-browser-manager@example.com", ["Employee"])

    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        make_reporting_line(self.actor, self.manager)
        self.doc=make_dcs(suffix="Browser"+frappe.generate_hash(length=8))

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_negative_and_nonfinite_rows_cannot_save_or_submit(self):
        for table, fields in (
            ("items", ("qty","cost_rate","selling_rate")),
            ("resources", ("no_of_persons","no_of_days","hours","cost_rate")),
            ("addtional_charges", ("amount","selling_amount")),
        ):
            for field in fields:
                for value in (-1, float("inf"), float("nan")):
                    with self.subTest(table=table,field=field,value=value):
                        doc=frappe.get_doc(self.doc.as_dict())
                        if table != "items":
                            doc.set(table, [])
                            doc.append(table, {field:value})
                        else:
                            doc.items[0].set(field,value)
                        with self.assertRaises(frappe.ValidationError):
                            doc.save(ignore_permissions=True)
                        doc.docstatus=1
                        with self.assertRaises(frappe.ValidationError):
                            doc.validate()

    def test_negative_vendor_revision_changes_no_history(self):
        self.doc.submit()
        count=frappe.db.count("DCS Revision",{"dcs":self.doc.name})
        frappe.set_user(self.actor)
        for value in (-1000,float("inf"),float("nan")):
            result=frappe.call("bsgroup.api.dcs.negotiation.dcs_apply_revision",
                dcs=self.doc.name,source="Vendor",reason="ZZTEST negative",new_total_cost=value)
            self.assertEqual(result["ok"],0,result)
        self.assertEqual(frappe.db.count("DCS Revision",{"dcs":self.doc.name}),count)

    def test_legacy_negative_rows_cannot_be_awarded_or_authorised(self):
        from bsgroup.dcs.commercial_authority import authorised_position
        self.doc.submit()
        frappe.db.set_value("Deal Cost Item",self.doc.items[0].name,"cost_rate",-1000)
        self.doc.reload()
        self.assertFalse(authorised_position(self.doc))
        frappe.set_user(self.actor)
        with self.assertRaises(frappe.ValidationError):
            frappe.call("bsgroup.api.dcs.award.dcs_record_award",dcs=self.doc.name,
                award_reference="ZZTEST blocked poison",evidence_type="Customer PO")
        self.assertEqual(frappe.db.count("DCS Governance Event",
            {"dcs":self.doc.name,"event_code":"DCS_AWARD_RECORDED"}),0)

    def test_duplicate_metadata_and_insert_clear_decisions_and_award(self):
        self.doc.submit()
        values={"custom_approval_state":"Approved","custom_approval_required":"Manager",
            "custom_approved_revision_no":2,"custom_approved_by":self.manager,
            "custom_award_state":"Awarded","custom_baseline_frozen":1,"custom_frozen_total_cost":1000,
            "custom_award_reference":"ZZTEST original award","custom_deal_status":"Won"}
        frappe.db.set_value("Deal Cost Sheet",self.doc.name,dict(values))
        self.doc.reload()
        for field in values:
            self.assertTrue(self.doc.meta.get_field(field).no_copy,field)
        duplicate=frappe.copy_doc(self.doc,ignore_no_copy=False)
        self.assertFalse(duplicate.custom_approved_by)
        self.assertFalse(duplicate.custom_revision_reference)
        # API copies cannot reintroduce authority even if no_copy is bypassed.
        duplicate=frappe.copy_doc(self.doc,ignore_no_copy=True)
        duplicate.docstatus=0
        duplicate.opportunity=None
        duplicate.flags.ignore_links=True
        duplicate.insert(ignore_permissions=True,ignore_mandatory=True)
        self.assertEqual(duplicate.docstatus,0)
        self.assertEqual(duplicate.custom_deal_status,"Draft")
        self.assertFalse(duplicate.custom_baseline_frozen)
        self.assertFalse(duplicate.custom_approved_by)
        self.assertFalse(duplicate.custom_revision_reference)
        self.assertNotEqual(duplicate.custom_award_state,"Awarded")
        self.doc.reload()
        self.assertEqual(self.doc.custom_award_reference,"ZZTEST original award")

    def test_customer_and_lead_derivation_with_no_organisation_value(self):
        from bsgroup.utils.party import organisation_name_for
        for party_type in ("Lead","Customer"):
            d=make_dcs(party_type=party_type,suffix="BrowserParty"+frappe.generate_hash(length=8))
            d.party=None
            d.party_type="Lead" # default select must not defeat the Customer path
            d.organisation_name=None
            d.customer=None
            d.flags.ignore_mandatory=False
            d.save(ignore_permissions=True)
            self.assertEqual(d.party_type,party_type)
            self.assertTrue(d.party)
            self.assertEqual(d.organisation_name,organisation_name_for(party_type,d.party))
            self.assertEqual(d.customer,d.party if party_type=="Customer" else None)
        self.assertFalse(frappe.get_meta("Deal Cost Sheet").get_field("organisation_name").reqd)

    def test_submitted_quotation_update_items_is_blocked_before_core_writes(self):
        from bsgroup.dcs.quotation_control import update_child_qty_rate
        self.doc.submit()
        q=make_quotation_for(self.doc)
        frappe.db.set_value("Quotation",q.name,{"docstatus":1,
            "custom_dcs_revision_reference":self.doc.custom_revision_reference,
            "custom_dcs_superseded_revision":"ZZTEST newer revision"})
        before=frappe.db.get_value("Quotation Item",q.items[0].name,"rate")
        with patch("erpnext.controllers.accounts_controller.update_child_qty_rate") as core:
            with self.assertRaises(frappe.ValidationError):
                update_child_qty_rate("Quotation",json.dumps([{"docname":q.items[0].name,"rate":1400}]),q.name)
            core.assert_not_called()
        self.assertEqual(frappe.db.get_value("Quotation Item",q.items[0].name,"rate"),before)
        self.assertEqual(frappe.get_hooks("override_whitelisted_methods")[
            "erpnext.controllers.accounts_controller.update_child_qty_rate"][-1],
            "bsgroup.dcs.quotation_control.update_child_qty_rate")

    def test_submitted_quotation_form_change_is_blocked(self):
        from bsgroup.dcs.quotation_control import guard_lineage
        self.doc.submit()
        q=make_quotation_for(self.doc)
        previous=frappe.get_doc(q.as_dict())
        q.items[0].rate=1400
        with patch.object(q,"get_doc_before_save",return_value=previous):
            with self.assertRaises(frappe.ValidationError):
                guard_lineage(q)

    def test_other_update_items_paths_delegate_unchanged(self):
        from bsgroup.dcs.quotation_control import update_child_qty_rate
        with patch("erpnext.controllers.accounts_controller.update_child_qty_rate",return_value="OK") as core:
            self.assertEqual(update_child_qty_rate("Sales Order","[]","ZZTEST"),"OK")
            core.assert_called_once_with("Sales Order","[]","ZZTEST","items")

    def test_management_cards_exclude_drafts_and_all_test_prefixes(self):
        from bsgroup.patches.v0_1.dcs_browser_audit import repair_cards
        repair_cards()
        repair_cards()
        for name in ("Open DCS Handover Blockers","DCS Awarded Pending Delivery Release","DCS PO Reconciliation Mismatch"):
            card=frappe.get_doc("Number Card",name)
            filters=json.loads(card.filters_json)
            self.assertTrue(all(len(row)==4 for row in filters))
            self.assertTrue(any(row[2:] == ["not like","%ZZTEST%"] for row in filters))
            self.assertTrue(any(row[2:] == ["not like","%ZZ-TEST%"] for row in filters))
            if card.document_type=="Deal Cost Sheet":
                self.assertIn(["Deal Cost Sheet","docstatus","=",1],filters)

    def test_nonstock_product_group_remains_a_product(self):
        from bsgroup.dcs.item_category import category_for_item, get_item_category
        item=self.doc.items[0].item_code
        frappe.db.set_value("Item",item,{"item_group":"Products","is_stock_item":0})
        self.assertEqual(category_for_item(item),"Products")
        self.assertEqual(get_item_category(item),"Products")
        self.doc.save(ignore_permissions=True)
        self.assertEqual(self.doc.items[0].item_category,"Products")
        self.assertEqual(self.doc.products_cost_total,1000)
        self.assertEqual(self.doc.services_cost_total,0)

    def test_invalid_legacy_rows_can_be_repaired_by_audited_boq_revision(self):
        from bsgroup.api.dcs.test_dcs_boq_revision import payload
        self.doc.submit()
        original=self.doc.custom_revision_reference
        frappe.db.set_value("Deal Cost Item",self.doc.items[0].name,"cost_rate",-1000)
        self.doc.reload()
        values=payload(self.doc)
        values["items"][0]["cost_rate"]=1250
        frappe.set_user(self.actor)
        result=frappe.call("bsgroup.api.dcs.boq_revision.dcs_apply_boq_revision",
            dcs=self.doc.name,expected_modified=str(self.doc.modified),source="Vendor",
            reason="ZZTEST repair invalid old row",**values)
        self.assertEqual(result["ok"],1,result)
        self.doc.reload()
        self.assertEqual(self.doc.custom_approval_required,"Manager")
        self.assertEqual(self.doc.custom_working_total_cost,1250)
        self.assertTrue(frappe.db.exists("DCS Revision",original))
        revision=frappe.get_doc("DCS Revision",result["revision"])
        self.assertTrue(any(json.loads(row.before_values).get("cost_rate")==-1000 for row in revision.boq_lines))
