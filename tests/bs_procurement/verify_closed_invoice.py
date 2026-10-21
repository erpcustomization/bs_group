"""Read-only installation and test-evidence check for closed-PO invoicing."""
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
    checks = {}
    paths = [("closed_po_invoicing", "closed_po_invoicing.log"), ("ui", "closed_invoice_ui.log")]
    paths += [(s, f"closed_invoice_{s}.log") for s in (
        "cash_and_closed_orders", "payment_policy", "standard_documents", "mohan_approval",
        "pr_supporting", "accounts_continuity", "sales_handover", "qc_gaps", "deployment",
        "selected_print_format")]
    for suite, path in paths:
        log = (root / "qa_reports" / path).read_text()
        assert "Traceback (most recent call last)" not in log, suite
        checks[suite] = int(re.findall(r'"passed":\s*(\d+)', log)[-1])
    assert frappe.db.get_value("User", PROCUREMENT_APPROVER, "enabled")
    assert {APPROVER_ROLE, "Purchase Manager", "Accounts Manager"}.issubset(
        frappe.get_roles(PROCUREMENT_APPROVER))
    for field in SUPPLIER_EXCEPTIONS:
        assert not frappe.db.count("Supplier", {field: 1})
        assert frappe.get_meta("Supplier").get_field(field).read_only
    assert frappe.db.get_single_value("Buying Settings", "po_required") == "Yes"
    assert frappe.db.get_single_value("Buying Settings", "pr_required") == "Yes"
    assert frappe.db.get_single_value("BS Group Settings", "cost_overrun_policy") == "Block"
    for doctype in ("Purchase Receipt", "Purchase Invoice", "Payment Entry", "Item"):
        assert not frappe.db.count(doctype, {"name": ["like", "ZZTEST-CLOSED-BILL-%"]}), doctype
    assert not frappe.db.count("Project", {"project_name": ["like", "ZZTEST-CLOSED-BILL-%"]})
    assert not frappe.db.count("Material Request", {"title": ["like", "ZZTEST-CLOSED-BILL-%"]})
    assert not frappe.db.exists("User", "zztest-closed-invoice-accounts@example.com")
    print(json.dumps(dict(site=frappe.local.site, checks=checks, total=sum(checks.values()),
        retained_bs_records={dt: frappe.db.count(dt, {"custom_bsp_managed": 1})
            for dt in ("Material Request", "Purchase Order", "Purchase Invoice")},
        temporary_closed_invoice_records_removed=True, supplier_exceptions_off=True,
        designated_approver=PROCUREMENT_APPROVER, deployment_scope="rel1-test.local only"), indent=2))
finally:
    frappe.db.rollback()
    frappe.destroy()
