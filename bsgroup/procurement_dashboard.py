"""Read-only procurement overview, respecting document and company permissions."""
from collections import Counter, defaultdict

import frappe
from frappe.utils import flt, nowdate, now_datetime

from bsgroup.procurement_lists import visible_company_names


def visible_rows(doctype, fields, filters):
    if not frappe.has_permission(doctype, "read"):
        return None
    result, start = [], 0
    while True:
        rows = frappe.get_list(doctype, fields=fields, filters=filters, start=start,
                               page_length=500, order_by="modified desc, name desc")
        allowed = set(visible_company_names(doctype, [r.name for r in rows]))
        result.extend(r for r in rows if r.name in allowed)
        if len(rows) < 500:
            return result
        start += 500


@frappe.whitelist()
def get_dashboard(company=""):
    if frappe.session.user == "Guest":
        frappe.throw("Please sign in.", frappe.PermissionError)
    common = ["name", "company", "modified", "docstatus", "status"]
    specifications = (
        ("requests", "Material Request", common + ["workflow_state", "title"],
         {"custom_bsp_managed": 1, "material_request_type": "Purchase"}),
        ("orders", "Purchase Order", common + ["custom_bsp_approval_state", "supplier",
         "currency", "grand_total", "schedule_date", "per_received", "custom_bsp_material_request"],
         {"custom_bsp_managed": 1}),
        ("payments", "Purchase Invoice", common + ["workflow_state", "supplier", "currency",
         "party_account_currency", "outstanding_amount", "due_date", "is_return"],
         {"custom_bsp_managed": 1}),
    )
    data = {key: visible_rows(dt, fields, filters) for key, dt, fields, filters in specifications}
    companies = sorted({r.company for rows in data.values() for r in (rows or [])})
    selected = str(company or "")
    today = nowdate()
    stages, attention, recent = {}, [], []
    po_value, unpaid_value = defaultdict(float), defaultdict(float)
    pending = awaiting_receipt = overdue_payments = unpaid_count = 0
    labels = {"requests": "Purchase Requisition", "orders": "Purchase Order", "payments": "Payment Order"}
    for kind, rows in data.items():
        if rows is None:
            stages[kind] = None
            continue
        rows = [r for r in rows if not selected or r.company == selected]
        states = Counter()
        for row in rows:
            state = "Cancelled" if row.docstatus == 2 else (
                row.get("custom_bsp_approval_state") if kind == "orders" else row.workflow_state) or "Draft"
            states[state] += 1
            record = dict(id=row.name, kind=kind, label=labels[kind], company=row.company,
                          description=row.get("supplier") or row.get("title") or "",
                          state=state, modified=str(row.modified),
                          request=row.get("custom_bsp_material_request") or "")
            recent.append(record)
            if state == "Pending Approval":
                pending += 1
                attention.append(dict(record, reason="Awaiting approval", priority=1))
            if kind == "orders" and row.docstatus == 1 and state == "Approved":
                po_value[row.currency] += flt(row.grand_total)
                if row.status not in ("Closed", "Cancelled") and flt(row.per_received) < 100:
                    awaiting_receipt += 1
                    if row.schedule_date and str(row.schedule_date) < today:
                        attention.append(dict(record, reason="Delivery overdue", priority=2))
            if kind == "payments" and row.docstatus == 1 and state == "Approved" and not row.is_return:
                outstanding = flt(row.outstanding_amount)
                if outstanding > 0:
                    unpaid_count += 1
                    unpaid_value[row.party_account_currency or row.currency] += outstanding
                    if row.due_date and str(row.due_date) < today:
                        overdue_payments += 1
                        attention.append(dict(record, reason="Payment overdue", priority=0))
        stages[kind] = dict(total=len(rows), states=dict(states))
    attention.sort(key=lambda r: (r["priority"], r["modified"], r["id"]))
    recent.sort(key=lambda r: (r["modified"], r["id"]), reverse=True)
    return dict(companies=companies, company=selected, stages=stages,
                pending=pending, awaitingReceipt=awaiting_receipt, overduePayments=overdue_payments,
                unpaidCount=unpaid_count, poValue=dict(po_value), unpaidValue=dict(unpaid_value),
                attention=attention[:12], attentionCount=len(attention), recent=recent[:8],
                updated=str(now_datetime()), user=frappe.session.user,
                restricted=[labels[k] for k, value in stages.items() if value is None])
