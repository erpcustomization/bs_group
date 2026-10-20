"""Cash journal controls; omitting a Supplier must not bypass procurement."""
import frappe
from frappe.utils import flt, now_datetime
from bsgroup.procurement_controls import PROCUREMENT_APPROVER, APPROVER_ROLE

CATEGORIES = (
    "Statutory tax settlement",
    "Employee settlement",
    "Financing or capital settlement",
    "Customer refund",
)
PROOF = ("custom_bsp_cash_approved_by", "custom_bsp_cash_approved_on")
MESSAGE = (
    "Direct expense, utility and vendor payments cannot be posted through a Journal Entry. "
    "Create a BS Purchase Requisition with the invoice copy and quotation-exception notes, "
    "then obtain Mohan's PO and Payment Order approvals and pay against that Payment Order."
)


def financial_values(doc):
    fields = ("account", "party_type", "party", "debit", "credit",
              "debit_in_account_currency", "credit_in_account_currency",
              "exchange_rate", "reference_type", "reference_name", "cost_center", "project")
    return (doc.company, str(doc.posting_date), [
        tuple(str(row.get(field) or "") for field in fields) for row in doc.accounts
    ])


def validate_cash_journal(doc, method=None):
    if doc.doctype != "Journal Entry" or doc.docstatus == 2:
        return
    old = doc.get_doc_before_save()
    for field in PROOF:
        previous = old.get(field) if old else None
        if str(doc.get(field) or "") != str(previous or ""):
            frappe.throw("Cash journal approval evidence cannot be entered or changed manually.")
        doc.set(field, previous)
    if old and old.docstatus == 1:
        # Do not retrofit approvals onto historical postings. Permit bank
        # reconciliation metadata, never changes to their financial content.
        if (financial_values(doc) != financial_values(old)
                or doc.get("custom_bsp_cash_category") != old.get("custom_bsp_cash_category")
                or doc.get("custom_bsp_cash_reason") != old.get("custom_bsp_cash_reason")):
            frappe.throw("Cancel and replace the submitted cash journal to change its financial "
                         "details or approval classification.")
        return
    rows = []
    for row in doc.accounts:
        account = frappe.get_cached_value("Account", row.account,
            ["account_type", "root_type", "company"], as_dict=True)
        if not account or account.company != doc.company:
            frappe.throw("Journal accounts must belong to the journal's company.")
        rows.append((row, account))
    is_cash = lambda account: account.account_type in ("Bank", "Cash") and account.root_type == "Asset"
    if not any(is_cash(a) and flt(r.credit_in_account_currency) > 0 for r, a in rows):
        return  # Non-cash accruals, depreciation and adjustments remain standard.
    debits = [(r, a) for r, a in rows if flt(r.debit_in_account_currency) > 0 and not is_cash(a)]
    if not debits:
        # Only actual bank/cash transfers; an expense hidden on a credit row
        # must not turn a composite journal into an unchecked transfer.
        if all(is_cash(a) for r, a in rows):
            return
        frappe.throw(MESSAGE)
    suppliers = [(r, a) for r, a in debits if r.party_type == "Supplier"]
    if suppliers:
        if len(suppliers) != len(debits):
            frappe.throw("Keep supplier settlement separate from other journal debits. "
                         "Every supplier payment must reference an approved Payment Order.")
        return  # Existing supplier allocation checks validate every reference.
    category = doc.get("custom_bsp_cash_category")
    reason = (doc.get("custom_bsp_cash_reason") or "").strip()
    def allowed(row, account):
        if account.root_type == "Expense" or row.party_type == "Supplier":
            return False
        if category == CATEGORIES[0]:
            return account.account_type == "Tax" and account.root_type == "Liability" and not row.party
        if category == CATEGORIES[1]:
            return (row.party_type == "Employee" and bool(row.party)
                    and account.root_type in ("Asset", "Liability")
                    and account.account_type in ("Receivable", "Current Asset", "Payable",
                                                 "Current Liability", "Liability"))
        if category == CATEGORIES[2]:
            return (account.root_type in ("Liability", "Equity")
                    and account.account_type in ("Liability", "Current Liability", "Equity")
                    and not row.party)
        if category == CATEGORIES[3]:
            return (account.account_type == "Receivable" and row.party_type == "Customer"
                    and bool(row.party))
        return False
    if category not in CATEGORIES or not all(allowed(r, a) for r, a in debits):
        frappe.throw(MESSAGE + " Genuine non-procurement cash journals require a matching "
                     "non-procurement category; generic clearing, stock and asset purchases are not exceptions.")
    if not reason:
        frappe.throw("Explain the non-procurement cash settlement before saving it for Mohan's approval.")
    if doc.docstatus == 1:
        if (frappe.session.user != PROCUREMENT_APPROVER
                or not frappe.get_cached_value("User", PROCUREMENT_APPROVER, "enabled")
                or not {APPROVER_ROLE, "Accounts Manager"}.issubset(frappe.get_roles())):
            frappe.throw("Only Mohan can submit a non-procurement cash journal.", frappe.PermissionError)
        if method == "before_submit":
            doc.custom_bsp_cash_approved_by = PROCUREMENT_APPROVER
            doc.custom_bsp_cash_approved_on = now_datetime()
