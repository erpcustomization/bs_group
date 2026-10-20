"""Non-bypassable supplier settlement policy for standard ERP documents."""
import frappe
from frappe.utils import cint, flt, now_datetime
from bsgroup.procurement_controls import PROCUREMENT_APPROVER, approval_allowed

SUPPLIER_EXCEPTIONS = (
    "allow_purchase_invoice_creation_without_purchase_order",
    "allow_purchase_invoice_creation_without_purchase_receipt",
)
APPROVAL_FIELDS = ("custom_bsp_approved_by", "custom_bsp_approved_on")


def supplier_policy(doc, method=None):
    if any(cint(doc.get(field)) for field in SUPPLIER_EXCEPTIONS):
        frappe.throw("Supplier exceptions for invoices without a Purchase Order or Purchase Receipt "
                     "must remain off.")


def is_approved(invoice):
    return bool(invoice.docstatus == 1 and invoice.get("custom_bsp_managed")
                and invoice.get("workflow_state") == "Approved"
                and invoice.get("custom_bsp_approved_by") == PROCUREMENT_APPROVER
                and invoice.get("custom_bsp_approved_on") and not invoice.get("is_return"))


def protect_approval(doc, old):
    """Only a real Pending -> Approved submission by Mohan produces proof."""
    for field in APPROVAL_FIELDS:
        before = old.get(field) if old else None
        if str(doc.get(field) or "") != str(before or ""):
            frappe.throw("Payment Order approval evidence cannot be entered or changed manually.")
        doc.set(field, before)
    if not doc.get("custom_bsp_managed") or doc.docstatus == 2:
        return
    state = doc.get("workflow_state") or "Draft"
    previous = old.get("workflow_state") if old else None
    if state in ("Approved", "Rejected") and state != previous:
        approval_allowed(doc, throw=True)
        if not old or old.docstatus != 0 or previous != "Pending Approval":
            frappe.throw("Send the Payment Order for approval before Mohan decides.")
        if state == "Approved":
            if doc.docstatus != 1:
                frappe.throw("Approval must submit the standard Purchase Invoice.")
            doc.custom_bsp_approved_by = PROCUREMENT_APPROVER
            doc.custom_bsp_approved_on = now_datetime()
    if doc.docstatus == 1 and (not old or old.docstatus == 0) and not is_approved(doc):
        frappe.throw("Only a Payment Order approved by Mohan can be submitted.")


def approved_invoice(name, supplier, company, account=None):
    # Current locking read serializes concurrent payments and cancellation.
    rows = frappe.db.sql("""select name, docstatus, workflow_state, custom_bsp_managed,
        custom_bsp_approved_by, custom_bsp_approved_on, is_return, supplier, company,
        outstanding_amount, credit_to, party_account_currency
        from `tabPurchase Invoice` where name=%s for update""", (name,), as_dict=True)
    invoice = rows[0] if rows else None
    if not invoice or not is_approved(invoice):
        frappe.throw("Supplier payments require a submitted Payment Order approved by Mohan.")
    if invoice.supplier != supplier or invoice.company != company:
        frappe.throw("The supplier and company must match the approved Payment Order.")
    if account and account != invoice.credit_to:
        frappe.throw("The supplier account must match the approved Payment Order.")
    return invoice


def allocations(doc):
    if doc.doctype == "Payment Entry":
        return [(r.reference_doctype, r.reference_name, flt(r.allocated_amount), doc.party,
                 doc.get("paid_to")) for r in doc.references if flt(r.allocated_amount)]
    return [(r.reference_type, r.reference_name, flt(r.debit_in_account_currency), r.party,
             r.account) for r in doc.accounts
            if r.party_type == "Supplier" and flt(r.debit_in_account_currency) > 0]


def validate_payment(doc, method=None):
    if doc.docstatus == 2:
        return
    if doc.doctype == "Payment Entry" and not (
            doc.party_type == "Supplier" and doc.payment_type == "Pay"):
        return
    if doc.doctype == "Payment Entry" and method == "before_update_after_submit":
        # Native submitted-document edits do not run validate(). Never trust
        # stale or supplied amount caches when allocation rows change.
        doc.set_amounts_in_company_currency()
        doc.set_total_allocated_amount()
        doc.set_unallocated_amount()
    rows = allocations(doc)
    if doc.doctype == "Payment Entry":
        if not rows or abs(flt(doc.unallocated_amount)) > 0.000001:
            frappe.throw("Allocate the entire supplier payment to approved Payment Orders. "
                         "Unallocated payments and PO advances are not allowed.")
    elif not rows:
        return
    totals, parties, accounts = {}, {}, {}
    for doctype, name, amount, supplier, account in rows:
        if doctype != "Purchase Invoice" or not name or amount <= 0:
            frappe.throw("Supplier payments must reference approved Payment Orders (Purchase Invoices) only.")
        if name in parties and (parties[name] != supplier or accounts[name] != account):
            frappe.throw("All allocations to a Payment Order must use its supplier and payable account.")
        totals[name] = totals.get(name, 0) + amount
        parties[name], accounts[name] = supplier, account
    old = doc.get_doc_before_save()
    previous = {}
    if old and old.docstatus == 1:
        for doctype, name, amount, supplier, account in allocations(old):
            if doctype == "Purchase Invoice":
                previous[name] = previous.get(name, 0) + amount
    for name in sorted(totals):
        invoice = approved_invoice(name, parties[name], doc.company, accounts[name])
        # Existing allocations are already deducted from outstanding on an
        # update/reconciliation. Recheck the new total against the current balance.
        available = flt(invoice.outstanding_amount) + previous.get(name, 0)
        if totals[name] > available + 0.000001:
            frappe.throw("Supplier payment exceeds the approved Payment Order's outstanding amount.")


def validate_inline_payment(doc, method=None):
    if doc.docstatus == 2:
        return
    # Direct cash/bank settlement in Purchase Invoice bypasses Payment Entry.
    # Keep settlement explicit so every payment is made after invoice approval.
    if doc.get("is_paid") or flt(doc.get("paid_amount")):
        frappe.throw("Approve the Payment Order first, then record its supplier payment using Payment Entry. "
                     "Inline invoice payments are not allowed.")
    if any(flt(row.allocated_amount) for row in doc.get("advances", [])):
        frappe.throw("Approve the Payment Order first, then allocate payment against it. "
                     "Supplier advances cannot bypass Payment Order approval.")


def before_invoice_cancel(doc, method=None):
    frappe.db.sql("select name from `tabPurchase Invoice` where name=%s for update", (doc.name,))
    payment = frappe.db.sql("""select p.name from `tabPayment Entry` p
        join `tabPayment Entry Reference` r on r.parent=p.name
        where p.docstatus=1 and r.reference_doctype='Purchase Invoice'
          and r.reference_name=%s and r.allocated_amount!=0 limit 1 for update""", (doc.name,))
    journal = frappe.db.sql("""select p.name from `tabJournal Entry` p
        join `tabJournal Entry Account` r on r.parent=p.name
        where p.docstatus=1 and r.reference_type='Purchase Invoice'
          and r.reference_name=%s and r.party_type='Supplier'
          and r.debit_in_account_currency>0 limit 1 for update""", (doc.name,))
    if payment or journal:
        frappe.throw("Cancel or reverse the linked supplier payments before cancelling the Payment Order.")


def lock_payment_sources(doc, method=None):
    # Cancellation must serialize with invoice cancellation and other settlements.
    for name in sorted({name for dt, name, amount, supplier, account in allocations(doc)
                        if dt == "Purchase Invoice" and name}):
        frappe.db.sql("select name from `tabPurchase Invoice` where name=%s for update", (name,))


def prevent_unreconcile(doc, method=None):
    # Unreconcile Payment removes references using direct SQL, without saving
    # Payment Entry/Journal Entry. Keep supplier payments linked at all times.
    if doc.voucher_type not in ("Payment Entry", "Journal Entry") or not doc.voucher_no:
        return
    payment = frappe.get_doc(doc.voucher_type, doc.voucher_no)
    supplier_payment = (
        payment.party_type == "Supplier" and payment.payment_type == "Pay"
        if payment.doctype == "Payment Entry" else bool(allocations(payment))
    )
    if payment.docstatus == 1 and supplier_payment:
        frappe.throw("Supplier payments must remain linked to approved Payment Orders. "
                     "Cancel the payment and create a correctly allocated payment instead of unreconciling it.")
