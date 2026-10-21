"""Won evidence, legacy link recovery and configured approver regression; staging only."""
import json
import uuid
from unittest.mock import patch
from io import BytesIO
from pypdf import PdfWriter
import frappe
from frappe.utils.file_manager import save_file
from bsgroup.dcs import procurement as handover
from bsgroup.dcs import manager_approval as routing
from bsgroup.dcs.commercial_authority import authorised_position
from bsgroup.tests.dcs_fixtures import make_dcs, make_user
from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation
from bsgroup.patches.v0_1.quotation_won_requirements import repair_missing_links

RESULTS = []


def sample_pdf():
    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(stream)
    return stream.getvalue()


def check(label, result):
    assert result, label
    RESULTS.append(label)
    print("PASS", label, flush=True)


def blocked(label, fn):
    point = "won_" + uuid.uuid4().hex
    frappe.db.savepoint(point)
    try:
        fn()
    except (frappe.ValidationError, frappe.PermissionError):
        frappe.db.rollback(save_point=point)
        frappe.clear_messages()
        check(label, True)
    else:
        raise AssertionError("Expected rejection: " + label)


def quotation():
    frappe.set_user("Administrator")
    sheet = make_dcs(suffix="WON-" + uuid.uuid4().hex[:8], submit=True,
        company="Bits Secure IT Infrastructure LLC - AE", currency="AED",
        items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A", qty=1, cost_rate=1000, selling_rate=1500)])
    q = frappe.get_doc("Quotation", make_quotation(sheet.name))
    q.flags.ignore_mandatory = True
    q.flags.ignore_links = True
    q.custom_pipeline_stage = "Sent"
    q.submit()
    frappe.db.set_value("Deal Cost Sheet", sheet.name, "custom_quotation", q.name)
    return sheet, q


def evidence(q):
    f = save_file("ZZTEST-Won-PO.pdf", sample_pdf(), "Quotation", q.name,
                  is_private=1, df="custom_customer_po")
    q.custom_customer_po = f.file_url
    q.custom_customer_po_reference = "ZZTEST-PO-" + q.name


def run():
    assert frappe.local.site == "rel1-test.local"
    # Simulate the Oman defect: a submitted quotation missing its DCS backlink.
    sheet, q = quotation()
    frappe.db.set_value("Quotation", q.name, {"custom_deal_cost_sheet": None,
                        "custom_dcs_revision_reference": None})
    q.reload()
    q.custom_pipeline_stage = "Won"
    def save_won():
        current = frappe.get_doc("Quotation", q.name)
        current.flags.ignore_mandatory = True
        for field in ("custom_pipeline_stage", "custom_customer_po", "custom_customer_po_reference"):
            current.set(field, q.get(field))
        return current.save()
    blocked("Unlinked quotation cannot become Won without either PO field", save_won)
    q.custom_customer_po_reference = "PO-123"
    blocked("Unlinked quotation cannot become Won without the attachment", save_won)
    evidence(q)
    q.custom_customer_po_reference = "   "
    blocked("Whitespace PO reference is rejected", save_won)
    q.custom_customer_po_reference = "PO-123"
    good_file = q.custom_customer_po
    q.custom_customer_po = "https://example.com/po.pdf"
    blocked("External URL cannot replace attached PO evidence", save_won)
    q.custom_customer_po = good_file
    save_won()
    q.reload()
    check("Valid unlinked quotation can record Won with PO evidence", q.custom_pipeline_stage == "Won")
    result = repair_missing_links()
    q.reload()
    check("Exact unique DCS backlink is recovered", q.name in result["repaired"] and q.custom_deal_cost_sheet == sheet.name)
    check("Recovery preserves quotation stage and commercial totals", q.custom_pipeline_stage == "Won" and float(q.total) == 1500)
    check("Recovery does not invent an award or approval", frappe.db.get_value("Deal Cost Sheet", sheet.name, "custom_award_state") != "Awarded")
    check("Recovery is audited", frappe.db.exists("DCS Governance Event", {"dcs": sheet.name, "event_code": "DCS_QUOTATION_LINK_RECOVERED"}))
    check("Recovery is idempotent", q.name not in repair_missing_links()["repaired"])
    sheet2, q2 = quotation()
    frappe.db.set_value("Quotation", q2.name, {"custom_deal_cost_sheet": None, "total": 1400})
    check("Commercial mismatch is never silently linked", q2.name in repair_missing_links()["skipped"] and not frappe.db.get_value("Quotation", q2.name, "custom_deal_cost_sheet"))
    for field in ("custom_customer_po", "custom_customer_po_reference"):
        check(field + " is mandatory for all Won quotations", frappe.get_meta("Quotation").get_field(field).mandatory_depends_on == "eval:doc.custom_pipeline_stage == 'Won'")
    check("DCS field is installed and visible", bool(frappe.get_meta("Quotation").get_field("custom_deal_cost_sheet")) and not frappe.get_meta("Quotation").get_field("custom_deal_cost_sheet").hidden)

    mohan = routing.FIXED_APPROVER
    make_user(mohan, ["Sales Manager", "Managing Director"])
    other = make_user("zztest-won-other@example.com", ["Sales Manager", "Managing Director"])
    # Use a revision initiated by Mohan to prove the explicit single-approver policy.
    sheet3, _ = quotation()
    frappe.set_user(mohan)
    result = frappe.call("bsgroup.api.dcs.negotiation.dcs_apply_revision", dcs=sheet3.name,
        source="Vendor", reason="ZZTEST Won gate commercial exception", new_total_cost=1250)
    check("Below-floor revision is created for approval", result.get("ok") == 1)
    sheet3.reload()
    frappe.set_user("Administrator")
    settings = frappe.get_single("BS Group Settings")
    settings.dcs_approval_policy = "Mohan"
    settings.save()
    route = routing.route_for(sheet3)
    check("Settings reroutes pending revision to Mohan", route.approval_policy == "Mohan" and route.approval_manager == mohan)
    check("Mohan may decide even if he initiated the revision", routing.is_assigned_manager(sheet3, mohan))
    check("Another Managing Director cannot approve", not routing.is_assigned_manager(sheet3, other))
    check("Rerouting does not grant approval", not authorised_position(sheet3))
    frappe.set_user(other)
    result = frappe.call("bsgroup.api.dcs.approval.dcs_approval_decision", dcs=sheet3.name, action="Approve")
    check("Approval endpoint rejects another user", result.get("ok") == 0)
    frappe.set_user(mohan)
    view = frappe.call("bsgroup.api.dcs.approval.dcs_screen4", dcs=sheet3.name)
    check("Mohan sees the approval action", view.get("authority") == "Mohan" and any(a["key"] == "Approve" for a in view.get("actions", [])))
    result = frappe.call("bsgroup.api.dcs.approval.dcs_approval_decision", dcs=sheet3.name, action="Approve")
    check("Mohan approval succeeds", result.get("ok") == 1)
    sheet3.reload()
    check("Recorded Mohan approval authorises this exact revision", authorised_position(sheet3) and sheet3.custom_approved_by == mohan)
    frappe.set_user("Administrator")
    routing.reroute_pending()
    check("Existing final approval remains unchanged", frappe.db.get_value("DCS Revision", sheet3.custom_revision_reference, "decided_by") == mohan)
    frappe.db.set_value("User", mohan, "enabled", 0)
    check("Disabled Mohan cannot approve", not routing.is_assigned_manager(sheet3, mohan))
    print(json.dumps({"passed": len(RESULTS), "tests": RESULTS}, indent=2))


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    try:
        run()
    finally:
        frappe.db.rollback()
        frappe.destroy()
