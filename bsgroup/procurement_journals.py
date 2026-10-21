"""Cash journal controls; omitting a Supplier must not bypass procurement."""
import frappe
from math import isfinite
from frappe.utils import flt, now_datetime
from bsgroup.procurement_controls import PROCUREMENT_APPROVER, APPROVER_ROLE

CATEGORIES = (
    "Statutory tax settlement",
    "Employee settlement",
    "Financing or capital settlement",
    "Customer refund",
    "Bank charges",
)
PROOF = ("custom_bsp_cash_approved_by", "custom_bsp_cash_approved_on")
MESSAGE = (
    "Direct expense, utility and vendor payments cannot be posted through a Journal Entry. "
    "Create a BS Purchase Requisition with the invoice copy and quotation-exception notes, "
    "then obtain Mohan's PO and Payment Order approvals and pay against that Payment Order."
)


def validate_account_category(doc, method=None):
    old = doc.get_doc_before_save()
    category = doc.get("custom_bsp_cash_category") or ""
    previous = (old.get("custom_bsp_cash_category") or "") if old else ""
    if category != previous and frappe.session.user != PROCUREMENT_APPROVER:
        frappe.throw("Only Mohan can change an account's non-procurement settlement classification.",
                     frappe.PermissionError)
    if not category:
        return
    roots = {
        CATEGORIES[0]: {"Liability"}, CATEGORIES[1]: {"Asset", "Liability"},
        CATEGORIES[2]: {"Liability", "Equity"}, CATEGORIES[3]: {"Asset"},
        CATEGORIES[4]: {"Expense"},
    }
    if category not in roots or doc.is_group or doc.root_type not in roots[category]:
        frappe.throw("The account type does not match its non-procurement settlement classification.")


def seed_cash_accounts():
    """Classify known chart accounts once; never infer exceptions from partial names."""
    names = {
        CATEGORIES[1]: {
            "Payroll Payable", "Salary Payable", "Net Salary Payable", "Hold Salary Payable",
            "Employee Reimbursements", "Employee Reimbursements Payable",
            "Employee Benefits Obligation", "Employee Advances", "Salary Advances",
        },
        CATEGORIES[2]: {
            "Secured Loans", "Unsecured Loans", "Short term loans",
            "Car Loan - Sedan", "Car Loan- Nissan Sunny", "Credit Card Loan/Emi",
        },
        CATEGORIES[4]: {"Bank Charges", "Bank Charges and Fees", "Bank Fees and Charges"},
    }
    for category, account_names in names.items():
        roots = {"Expense"} if category == CATEGORIES[4] else (
            {"Asset", "Liability"} if category == CATEGORIES[1] else {"Liability", "Equity"})
        for row in frappe.get_all("Account", filters={"is_group": 0,
                "account_name": ["in", sorted(account_names)], "root_type": ["in", sorted(roots)]},
                fields=["name", "custom_bsp_cash_category"]):
            if not row.custom_bsp_cash_category:
                frappe.db.set_value("Account", row.name, "custom_bsp_cash_category", category)
                frappe.clear_document_cache("Account", row.name)


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
    # ERPNext accepts signed debit/credit inputs. A negative bank debit is a
    # cash outflow even though there is no positive credit row. Require the
    # ordinary positive debit/credit representation before classifying cash.
    for row in doc.accounts:
        for field in ("debit", "credit", "debit_in_account_currency", "credit_in_account_currency"):
            amount = flt(row.get(field))
            if not isfinite(amount) or amount < 0:
                frappe.throw("Journal amounts cannot be negative or non-finite. "
                             "Enter a positive amount on the opposite debit or credit side.")
    rows = []
    for row in doc.accounts:
        account = frappe.get_cached_doc("Account", row.account)
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
        classified = account.get("custom_bsp_cash_category") == category
        if row.party_type == "Supplier":
            return False
        if category == CATEGORIES[4]:
            return (account.root_type == "Expense" and not row.party
                    and (classified or account.account_type == "Bank Charges"))
        if account.root_type == "Expense":
            return False
        if category == CATEGORIES[0]:
            return account.account_type == "Tax" and account.root_type == "Liability" and not row.party
        if category == CATEGORIES[1]:
            payroll = classified and account.root_type == "Liability" and not row.party
            return payroll or (row.party_type == "Employee" and bool(row.party)
                    and account.root_type in ("Asset", "Liability")
                    and (classified or account.account_type in (
                        "Receivable", "Current Asset", "Payable", "Current Liability", "Liability")))
        if category == CATEGORIES[2]:
            return (account.root_type in ("Liability", "Equity")
                    and (classified or account.account_type in ("Liability", "Current Liability", "Equity"))
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
