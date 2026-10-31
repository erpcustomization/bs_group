"""Run only on the restored local bench. Every write rolls back."""
from pathlib import Path
from unittest.mock import patch
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / "bsgroup"))
frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
try:
    from bsgroup import scoped_sales_access as access
    from bsgroup.api.dcs.boq_revision import dcs_apply_boq_revision
    from bsgroup.api.dcs.negotiation import dcs_screen3
    from bsgroup.api.dcs.handover import dcs_screen5
    from bsgroup.api.dcs.test_dcs_boq_revision import payload
    from bsgroup.api.dcs.test_dcs_vendor_revision import quotation_values
    from bsgroup.tests.dcs_fixtures import make_dcs
    from bsgroup.tests import dcs_fixtures
    # This regression exercises existing deals, not the Opportunity intake flow.
    def existing_opportunity(party_type="Customer", suffix="A"):
        party = dcs_fixtures.make_customer(suffix)
        opp = frappe.get_doc({"doctype":"Opportunity", "name":"ZZTEST-OPP-" + suffix,
            "opportunity_from":party_type, "party_name":party,
            "opportunity_owner":"paul@bitssecureit.com", "opportunity_amount":1500,
            "custom_subject":"ZZTEST existing deal", "status":"Open"})
        opp.db_insert()
        return opp
    dcs_fixtures.make_opportunity = existing_opportunity
    with patch.object(frappe, "enqueue"):
        access.configure_dubai()
    print("Configured local roles", flush=True)
    # Production already removed this legacy filter when quote attribution
    # changed to the sales owner. Mirror that verified configuration locally.
    for rule in frappe.get_all("User Permission", filters={"user":"sanisha@bitssecureit.com",
            "allow":"Sales Person", "applicable_for":"Quotation"}, pluck="name"):
        frappe.db.delete("User Permission", {"name":rule})
    # The earlier rollout explicitly enabled Presales submission.
    rule = frappe.db.get_value("Custom DocPerm", {"parent":"Deal Cost Sheet", "role":access.PRESALES, "permlevel":0}, "name")
    frappe.db.set_value("Custom DocPerm", rule, "submit", 1)
    frappe.clear_cache()
    import bsgroup.hooks as hooks
    real_hooks = frappe.get_hooks
    def local_hooks(name=None, *args, **kwargs):
        value = real_hooks(name, *args, **kwargs)
        if name in ("has_permission", "permission_query_conditions"):
            value = dict(value)
            for dt in ("Lead", "Opportunity", "Presales Request", "Deal Cost Sheet", "Quotation", "Site Survey Request"):
                value[dt] = [getattr(hooks, name)[dt]]
        return value
    with patch.object(frappe, "get_hooks", side_effect=local_hooks):
        company = frappe.db.get_single_value("Global Defaults", "default_company")
        doc = make_dcs(suffix="PREACCESS" + frappe.generate_hash(length=6), submit=True, company=company)
        q = frappe.get_doc(quotation_values(doc, 1500)).insert()
        # Sales created the quote, Presales owns the linked request.
        pr = frappe.get_doc({"doctype":"Presales Request", "name":"ZZTEST-PRE-" + frappe.generate_hash(length=6),
            "presales_owner":"sanisha@bitssecureit.com", "opportunity":doc.opportunity})
        pr.db_insert()
        frappe.db.set_value("Deal Cost Sheet", doc.name, "presales_request", pr.name)
        frappe.db.set_value("Quotation", q.name, "owner", "paul@bitssecureit.com")
        foreign = make_dcs(suffix="FOREIGN" + frappe.generate_hash(length=6), submit=True, company=company)
        foreign_q = frappe.get_doc(quotation_values(foreign, 1500)).insert()
        frappe.db.set_value("Quotation", foreign_q.name, "owner", "paul@bitssecureit.com")
        doc.reload()
        frappe.set_user("sanisha@bitssecureit.com")
        assert frappe.get_doc("Quotation", q.name).has_permission("write")
        assert not frappe.get_doc("Quotation", foreign_q.name).has_permission("read")
        assert not frappe.get_doc("Deal Cost Sheet", foreign.name).has_permission("write")
        listed = frappe.get_list("Quotation", filters={"name":["in",[q.name,foreign_q.name]]}, pluck="name")
        assert listed == [q.name], listed
        cap = dcs_screen3(dcs=doc.name)["capability"]
        assert cap["can_prepare_boq"] == 1 and cap["can_customer_side"] == 0
        assert dcs_screen5(dcs=doc.name).get("projection") == "denied"
        p = payload(doc)
        p["items"][0].update(qty=2, cost_rate=900, selling_rate=1600, description="ZZTEST revised scope")
        p["items"].append({"item_code":doc.items[0].item_code,"qty":1,"cost_rate":200,"selling_rate":400,"description":"ZZTEST added scope"})
        result = dcs_apply_boq_revision(dcs=doc.name, expected_modified=str(doc.modified), source="Technical",
            reason="ZZTEST scoped Presales full BOQ revision", update_quotation=1, **p)
        assert result["ok"] == 1, result
        doc.reload(); q.reload()
        assert doc.docstatus == 1 and len(doc.items) == 2
        assert doc.total_cost == 2000 and doc.total_selling == 3600 and q.total == 3600
        assert q.owner == "paul@bitssecureit.com" and q.docstatus == 0
        assert frappe.db.count("DCS Revision", {"dcs":doc.name}) >= 2
        # Submitted quotations may not be overwritten, even by a permitted preparer.
        frappe.set_user("Administrator")
        q.submit()
        frappe.set_user("sanisha@bitssecureit.com")
        doc.reload()
        p = payload(doc); p["items"][0]["qty"] = 3
        before_revision = doc.custom_dcs_revision_no
        try:
            dcs_apply_boq_revision(dcs=doc.name, expected_modified=str(doc.modified), source="Technical",
                reason="ZZTEST submitted quotation guard", update_quotation=1, **p)
            raise AssertionError("Submitted quotation was overwritten")
        except frappe.ValidationError:
            pass
        doc.reload(); q.reload()
        assert doc.total_selling == 3600 and doc.custom_dcs_revision_no == before_revision
        assert q.docstatus == 1 and q.total == 3600
        # Remove an item and change pricing, leaving quotation for separate review.
        p = payload(doc); p["items"] = p["items"][:1]; p["items"][0]["selling_rate"] = 1700
        result = dcs_apply_boq_revision(dcs=doc.name, expected_modified=str(doc.modified), source="Technical",
            reason="ZZTEST remove scope", acknowledge_quote_review=1, **p)
        assert result["ok"] == 1, result
        doc.reload(); assert len(doc.items) == 1 and doc.total_selling == 3400
        q.reload(); assert q.docstatus == 1 and q.total == 3600
        try:
            dcs_apply_boq_revision(dcs=foreign.name, expected_modified=str(foreign.modified),source="Technical",reason="ZZTEST foreign denied",**payload(foreign))
            raise AssertionError("Foreign revision unexpectedly allowed")
        except frappe.PermissionError:
            pass
        # Award/release and customer-side negotiation authority remain unchanged.
        from bsgroup.api.dcs.negotiation import dcs_apply_revision
        denied = dcs_apply_revision(dcs=doc.name,source="Customer",reason="ZZTEST customer negotiation denied",new_total_selling=3000)
        assert denied["ok"] == 0, denied
        print("PASS assigned full BOQ add/update/remove, price and quantity changes, linked sales-owned draft quotation sync, list/direct scope, foreign denial, preserved owner, immutable revisions, no award or customer-negotiation grant", flush=True)
finally:
    frappe.set_user("Administrator")
    frappe.db.rollback()
    frappe.clear_cache()
    frappe.destroy()
