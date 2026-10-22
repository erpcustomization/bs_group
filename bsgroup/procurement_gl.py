"""Payment Order account selection and journal classification, using native posting."""
import re

import frappe
from frappe.utils import cint, flt

JOURNAL = "custom_bsp_journal_code"


def ensure_schema():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({
        "Purchase Invoice": [dict(fieldname=JOURNAL, label="Journal code", fieldtype="Data",
            insert_after="credit_to", length=40, in_standard_filter=1,
            depends_on="eval:doc.custom_bsp_managed", description=
            "Required manual journal classification for this Payment Order and its ledger entries. "
            "This is not an existing Journal Entry number.")],
        "GL Entry": [dict(fieldname=JOURNAL, label="Journal code", fieldtype="Data",
            insert_after="voucher_no", length=40, read_only=1, in_standard_filter=1,
            search_index=1)],
    }, update=True)


def managed(doc):
    return bool(doc.get("custom_bsp_managed") or any(r.purchase_order and
        frappe.get_cached_value("Purchase Order", r.purchase_order, "custom_bsp_managed")
        for r in doc.items))


def normalized_code(value):
    value = (value or "").strip().upper()
    if value and not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{0,39}", value):
        frappe.throw("Journal code must contain up to 40 letters, numbers, dots, hyphens, slashes or underscores.")
    return value


def editable_line(row):
    stock, asset = frappe.get_cached_value("Item", row.item_code, ["is_stock_item", "is_fixed_asset"]) or (0, 0)
    return not (stock or asset)


def accounting_values(doc):
    return (doc.get(JOURNAL) or "", doc.credit_to,
            bool(doc.get("custom_bsp_accounting_confirmed")),
            {r.name: (r.expense_account, r.cost_center, r.project, r.get("deferred_expense_account"))
             for r in doc.items})


def validate_selected_account(name, company):
    account = frappe.get_cached_doc("Account", name)
    account.check_permission("read")
    if account.company != company or account.is_group or account.disabled or account.root_type != "Expense":
        frappe.throw("Select an enabled expense GL account for this company, not a group account.")
    return account


class PaymentOrderAccountingMixin:
    def before_validate(self):
        parent = getattr(super(), "before_validate", None)
        if parent:
            parent()
        old = self.get_doc_before_save()
        if not (managed(self) or (old and managed(old))):
            return
        self.set(JOURNAL, normalized_code(self.get(JOURNAL)))
        if old and bool(self.get("custom_bsp_accounting_confirmed")) != bool(
                old.get("custom_bsp_accounting_confirmed")) and not getattr(
                    frappe.flags, "bsp_save_accounting", False):
            frappe.throw("Confirm Payment Order accounting through the BS Procurement accounting screen.")
        if old and (old.docstatus == 1 or old.get("workflow_state") == "Pending Approval"):
            if accounting_values(self) != accounting_values(old):
                frappe.throw("Payment Order accounting is locked after sending for approval. "
                             "Return it for correction and approval before changing accounting codes.")

    def before_update_after_submit(self):
        parent = getattr(super(), "before_update_after_submit", None)
        if parent:
            parent()
        old = self.get_doc_before_save()
        if old and managed(old) and accounting_values(self) != accounting_values(old):
            frappe.throw("Approved Payment Order accounting codes cannot be changed. Use cancellation and amendment.")

    def get_gl_dict(self, args, account_currency=None, item=None):
        entry = super().get_gl_dict(args, account_currency, item)
        if managed(self) and self.meta.has_field(JOURNAL):
            entry[JOURNAL] = self.get(JOURNAL) or ""
        return entry


def account_label(name):
    if not name:
        return ""
    code, title = frappe.get_cached_value("Account", name, ["account_number", "account_name"]) or (None, None)
    return " · ".join(str(v) for v in (code, title or name) if v)


def accounting_data(doc):
    ready = doc.meta.has_field(JOURNAL) and frappe.get_meta("GL Entry").has_field(JOURNAL)
    return dict(ready=ready, journalCode=doc.get(JOURNAL) or "",
        confirmed=bool(doc.get("custom_bsp_accounting_confirmed")),
        payable=account_label(doc.credit_to),
        editable=bool(ready and doc.docstatus == 0 and (doc.workflow_state or "Draft") in ("Draft", "Rejected")
                      and frappe.has_permission("Purchase Invoice", "write", doc=doc)),
        canViewLedger=bool(doc.docstatus in (1, 2) and frappe.has_permission("GL Entry", "read")),
        lines=[dict(id=r.name, item=r.item_code, account=r.expense_account or "",
                    label=account_label(r.expense_account), costCenter=r.cost_center or "",
                    editable=editable_line(r)) for r in doc.items])


@frappe.whitelist(methods=["POST"])
def save_accounting(name, modified, journal_code="", lines=None):
    from bsgroup.procurement import load
    from bsgroup.procurement_accounts import bs_order_names, get_payment_order
    doc = load("Purchase Invoice", name, "write", modified)
    if not bs_order_names(doc) or not accounting_data(doc)["editable"]:
        frappe.throw("Accounting codes can only be edited on a draft or rejected BS Payment Order.")
    updates = frappe.parse_json(lines) if isinstance(lines, str) else lines
    if not isinstance(updates, list):
        frappe.throw("Provide the invoice lines and their GL accounts.")
    journal_code = normalized_code(journal_code)
    if not journal_code:
        frappe.throw("Enter the journal code before saving Payment Order accounting.")
    rows = {r.name: r for r in doc.items}
    editable_ids = {r.name for r in doc.items if editable_line(r)}
    seen = set()
    selected = {}
    for value in updates:
        if not isinstance(value, dict) or value.get("id") not in rows or value["id"] in seen:
            frappe.throw("Select each existing Payment Order line only once.")
        row = rows[value["id"]]
        seen.add(row.name)
        account = value.get("account") or ""
        if not editable_line(row):
            if account != row.expense_account:
                frappe.throw("Stock and fixed-asset accounts follow ERPNext receipt and asset accounting.")
        elif account != row.expense_account:
            validate_selected_account(account, doc.company)
            row.expense_account = account
            selected[row.name] = account
        elif editable_line(row) and not account:
            frappe.throw("Select a GL account for every service or expense line.")
    if seen & editable_ids != editable_ids:
        frappe.throw("Select and confirm a GL account for every service or expense line.")
    doc.set(JOURNAL, journal_code)
    doc.custom_bsp_accounting_confirmed = 1
    previous_flag = getattr(frappe.flags, "bsp_save_accounting", False)
    frappe.flags.bsp_save_accounting = True
    try:
        doc.save()
    finally:
        frappe.flags.bsp_save_accounting = previous_flag
    # Never silently report a chosen account if native accounting substituted it.
    if any(r.expense_account != selected[r.name] for r in doc.items if r.name in selected):
        frappe.throw("The selected GL conflicts with this invoice's accounting treatment. Review the supplier invoice.")
    return get_payment_order(doc.name)


@frappe.whitelist()
def get_ledger(name):
    from bsgroup.procurement import load
    from bsgroup.procurement_accounts import bs_order_names
    invoice = load("Purchase Invoice", name)
    if not bs_order_names(invoice):
        frappe.throw("Select a BS Payment Order.")
    frappe.has_permission("GL Entry", "read", throw=True)
    fields = ["name", "account", "posting_date", "debit", "credit", "cost_center", "project", "is_cancelled"]
    if frappe.get_meta("GL Entry").has_field(JOURNAL):
        fields.append(JOURNAL)
    rows = frappe.get_list("GL Entry", filters=dict(voucher_type="Purchase Invoice",
        voucher_no=invoice.name, company=invoice.company), fields=fields,
        order_by="creation asc, name asc", limit_page_length=0)
    return dict(currency=frappe.get_cached_value("Company", invoice.company, "default_currency"),
        records=[dict(id=r.name, account=r.account, label=account_label(r.account),
            date=str(r.posting_date), debit=flt(r.debit), credit=flt(r.credit),
            journalCode=r.get(JOURNAL) or "", costCenter=r.cost_center or "",
            project=r.project or "", cancelled=cint(r.is_cancelled)) for r in rows])
