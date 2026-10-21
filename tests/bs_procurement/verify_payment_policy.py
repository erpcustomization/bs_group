"""Read-only deployment and regression evidence for the test site."""
import json
import re
from pathlib import Path
import frappe

frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
try:
    from bsgroup.procurement_controls import PROCUREMENT_APPROVER, APPROVER_ROLE
    from bsgroup.procurement_payments import SUPPLIER_EXCEPTIONS
    root = Path(frappe.get_app_path("bsgroup")).parent
    report = dict(site=frappe.local.site, approver=PROCUREMENT_APPROVER)
    assert frappe.db.get_value("User", PROCUREMENT_APPROVER, "enabled")
    assert {APPROVER_ROLE, "Purchase Manager", "Accounts Manager"}.issubset(
        frappe.get_roles(PROCUREMENT_APPROVER))
    report["supplier_count"] = frappe.db.count("Supplier")
    report["supplier_exceptions"] = {
        field: dict(enabled=frappe.db.count("Supplier", {field: 1}),
                    read_only=frappe.get_meta("Supplier").get_field(field).read_only)
        for field in SUPPLIER_EXCEPTIONS
    }
    assert all(v["enabled"] == 0 and v["read_only"] for v in report["supplier_exceptions"].values())
    hooks = frappe.get_hooks("doc_events")
    assert "bsgroup.procurement_payments.prevent_unreconcile" in hooks["Unreconcile Payment"]["before_submit"]
    for doctype in ("Payment Entry", "Journal Entry"):
        assert "bsgroup.procurement_payments.validate_payment" in hooks[doctype]["before_update_after_submit"]
    assert frappe.db.get_single_value("Buying Settings", "po_required") == "Yes"
    assert frappe.db.get_single_value("Buying Settings", "pr_required") == "Yes"
    assert frappe.db.get_single_value("BS Group Settings", "cost_overrun_policy") == "Block"
    report["retained_records"] = {
        doctype: frappe.db.count(doctype, {"custom_bsp_managed": 1})
        for doctype in ("Material Request", "Purchase Order", "Purchase Invoice")
    }
    assert report["retained_records"] == {
        "Material Request": 10, "Purchase Order": 8, "Purchase Invoice": 1}
    invoice = frappe.get_doc("Purchase Invoice", "ACC-PINV-2026-09339")
    assert invoice.docstatus == 0 and not invoice.custom_bsp_approved_by
    from bsgroup.procurement_accounts import get_payment_order
    detail = get_payment_order(invoice.name)
    assert not detail["canPay"] and detail["approver"]["user"] == PROCUREMENT_APPROVER
    report["checks"] = {}
    for suite in ("payment_policy", "standard_documents", "mohan_approval", "pr_supporting",
                  "accounts_continuity", "sales_handover", "qc_gaps", "deployment",
                  "selected_print_format"):
        log = (root/"qa_reports"/f"payment_policy_test_{suite}.log").read_text()
        assert "Traceback (most recent call last)" not in log, suite
        report["checks"][suite] = int(re.findall(r'"passed":\s*(\d+)', log)[-1])
    log = (root/"qa_reports/payment_policy_ui.log").read_text()
    report["checks"]["ui"] = int(re.findall(r'"passed":\s*(\d+)', log)[-1])
    report["total_checks"] = sum(report["checks"].values())
    assert report["total_checks"] == 453
    report["build"] = "20261020-payment-policy"
    assert report["build"] in (root/"qa_reports/payment_policy_deploy_standard.log").read_text()
    print(json.dumps(report, indent=2))
finally:
    frappe.db.rollback()
    frappe.destroy()
