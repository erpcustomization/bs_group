"""Read-only verification of the installed gap fix and complete regression evidence."""
import json
import re
from pathlib import Path
import frappe

frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
try:
    from bsgroup.procurement_controls import PROCUREMENT_APPROVER, APPROVER_ROLE
    from bsgroup.procurement_journals import CATEGORIES, PROOF
    from bsgroup.procurement_payments import SUPPLIER_EXCEPTIONS
    root = Path(frappe.get_app_path("bsgroup")).parent
    meta = frappe.get_meta("Journal Entry")
    assert meta.get_field("custom_bsp_cash_category").options.splitlines()[1:] == list(CATEGORIES)
    assert meta.has_field("custom_bsp_cash_reason")
    assert all(meta.get_field(field).read_only and meta.get_field(field).no_copy for field in PROOF)
    assert frappe.db.get_value("User", PROCUREMENT_APPROVER, "enabled")
    assert {APPROVER_ROLE, "Purchase Manager", "Accounts Manager"}.issubset(
        frappe.get_roles(PROCUREMENT_APPROVER))
    hooks = frappe.get_hooks("doc_events")
    assert "bsgroup.procurement_payments.validate_payment" in hooks["Journal Entry"]["before_submit"]
    for doctype in ("Purchase Receipt", "Purchase Invoice"):
        for event in ("on_submit", "on_cancel"):
            assert "bsgroup.procurement_quantities.sync_closed_orders" in hooks[doctype][event]
    for field in SUPPLIER_EXCEPTIONS:
        assert not frappe.db.count("Supplier", {field: 1})
        assert frappe.get_meta("Supplier").get_field(field).read_only
    assert frappe.db.get_single_value("Buying Settings", "po_required") == "Yes"
    assert frappe.db.get_single_value("Buying Settings", "pr_required") == "Yes"
    assert frappe.db.get_single_value("BS Group Settings", "cost_overrun_policy") == "Block"
    counts = {dt: frappe.db.count(dt, {"custom_bsp_managed": 1})
              for dt in ("Material Request", "Purchase Order", "Purchase Invoice")}
    assert counts == {"Material Request": 10, "Purchase Order": 8, "Purchase Invoice": 1}
    assert not frappe.db.count("Account", {"account_name": ["like", "ZZTEST GAP %"]})
    assert not frappe.db.count("Item", {"name": ["like", "ZZTEST-CLOSED-GAP-%"]})
    assert not frappe.db.exists("User", "zztest-cash-gap-accounts@example.com")
    checks = {}
    for suite, path in [
        ("reported_gaps", "gap_fix_focused.log"),
        ("ui", "cash_close_ui.log"),
        *((s, f"cash_close_{s}.log") for s in (
            "payment_policy", "standard_documents", "mohan_approval", "pr_supporting",
            "accounts_continuity", "sales_handover", "qc_gaps", "deployment", "selected_print_format")),
    ]:
        log = (root / "qa_reports" / path).read_text()
        assert "Traceback (most recent call last)" not in log, suite
        checks[suite] = int(re.findall(r'"passed":\s*(\d+)', log)[-1])
    assert sum(checks.values()) == 541
    print(json.dumps(dict(site=frappe.local.site, checks=checks, total=sum(checks.values()),
                         retained_records=counts, temporary_records_removed=True,
                         supplier_exceptions_off=True, deployment_scope="rel1-test.local only"), indent=2))
finally:
    frappe.db.rollback()
    frappe.destroy()
