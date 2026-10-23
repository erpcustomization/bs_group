"""Read-only PO connections. No document mutations or accounting actions."""
import frappe
from frappe.utils import flt

from bsgroup.procurement import access, load
from bsgroup.procurement_accounts import document_state


def candidates(doctype, filters, field="parent"):
    return set(frappe.get_all(doctype, filters=filters, pluck=field, limit_page_length=0))


def visible(doctype, names, company):
    if not frappe.has_permission(doctype, "read"):
        return [], True
    if not names:
        return [], False
    allowed = frappe.get_list(doctype, filters={"name": ["in", sorted(names)], "company": company},
                              pluck="name", limit_page_length=0, order_by="creation desc")
    docs = []
    for name in allowed:
        try:
            docs.append(access(frappe.get_doc(doctype, name)))
        except frappe.PermissionError:
            pass
    return docs, len(docs) != len(names)


def table(title, columns, rows):
    return dict(title=title, columns=columns, rows=rows)


def attachments(doc):
    result = []
    names = set(frappe.get_all("File", filters=dict(attached_to_doctype=doc.doctype,
            attached_to_name=doc.name, is_folder=0), pluck="name", limit_page_length=0))
    for field in ("custom_bsp_delivery_note_file", "custom_bsp_supplier_invoice_file"):
        reference = doc.get(field)
        if reference:
            names.update(frappe.get_all("File", or_filters={"name": reference, "file_url": reference},
                                        pluck="name", limit_page_length=0))
    for name in sorted(names):
        file = frappe.get_doc("File", name)
        if file.has_permission("read"):
            result.append(dict(name=file.file_name, url=file.file_url))
    return result


def header(doc):
    return dict(id=doc.name, status=document_state(doc), facts=[
        ["Company", doc.company], ["Date", str(doc.get("posting_date") or doc.get("transaction_date") or "")],
        ["Supplier", doc.get("supplier") or doc.get("party") or ""],
        ["Approval", doc.get("workflow_state") or ""]], tables=[], files=[], shared=False)


def ledger(doc):
    if not frappe.has_permission("GL Entry", "read"):
        return None
    rows = frappe.get_list("GL Entry", filters=dict(voucher_type=doc.doctype, voucher_no=doc.name,
        company=doc.company), fields=["account", "debit", "credit", "cost_center", "project", "is_cancelled"],
        limit_page_length=0, order_by="creation asc")
    currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    return table("Posted GL entries · " + currency,
        ["Account", "Debit", "Credit", "Cost centre", "Project", "Cancelled"],
        [[r.account, flt(r.debit), flt(r.credit), r.cost_center, r.project, "Yes" if r.is_cancelled else "No"] for r in rows])


def purchase_record(doc, order):
    value = header(doc)
    lines = [r for r in doc.items if r.purchase_order == order]
    value["shared"] = any(r.purchase_order != order for r in doc.items)
    value["facts"] += [["Currency", doc.currency], ["Document total", flt(doc.grand_total)],
        ["Lines linked to this PO (before document taxes)", sum(flt(r.amount) for r in lines) if lines else "Not directly allocated"],
        ["Return against", doc.get("return_against") or ""]]
    value["tables"].append(table("Items linked to this PO", ["Item", "Quantity", "UOM", "Rate", "Amount"],
        [[r.item_code, flt(r.qty), r.uom, flt(r.rate), flt(r.amount)] for r in lines]))
    if not lines and doc.get("is_return"):
        value["note"] = "Linked through the original document. Return lines have no direct PO allocation; full return items are shown below."
        value["tables"].append(table("Full return items", ["Item", "Quantity", "UOM", "Amount"],
            [[r.item_code, flt(r.qty), r.uom, flt(r.amount)] for r in doc.items]))
    if doc.doctype == "Purchase Invoice":
        value["facts"] += [["Vendor invoice", doc.bill_no], ["Due date", str(doc.due_date or "")],
            ["Outstanding (whole invoice)", flt(doc.outstanding_amount)],
            ["Outstanding currency", doc.get("party_account_currency") or doc.currency],
            ["Journal code", doc.get("custom_bsp_journal_code") or ""],
            ["Approved by", doc.get("custom_bsp_approved_by") or ""],
            ["Supplier payable account", doc.credit_to]]
        value["tables"].append(table("GL coding for this PO", ["Item", "GL account", "Cost centre"],
            [[r.item_code, r.expense_account, r.cost_center] for r in lines]))
    else:
        value["facts"] += [["Delivery note", doc.get("supplier_delivery_note") or ""],
            ["Supplier invoice", doc.get("custom_bsp_supplier_invoice_no") or ""]]
        value["tables"].append(table("Receipt warehouses", ["Item", "Accepted warehouse", "Rejected quantity"],
            [[r.item_code, r.warehouse, flt(r.rejected_qty)] for r in lines]))
    gl = ledger(doc)
    if gl is not None:
        value["tables"].append(gl)
    value["ledgerRestricted"] = gl is None
    value["files"] = attachments(doc)
    return value


@frappe.whitelist()
def get_connections(order):
    po = load("Purchase Order", order)
    if not po.get("custom_bsp_managed"):
        frappe.throw("Select a BS Procurement Purchase Order.")
    sections = []
    invoices = []
    for dt, label in (("Purchase Receipt", "Purchase Receipts"), ("Purchase Invoice", "Payment Orders / Supplier Invoices")):
        names = candidates(dt + " Item", {"purchase_order": order})
        docs, restricted = visible(dt, names, po.company)
        # Include returns even when their item links were not copied from the original.
        originals = [d.name for d in docs]
        if originals:
            names |= candidates(dt, {"return_against": ["in", originals]}, "name")
            docs, extra_restricted = visible(dt, names, po.company)
            restricted = restricted or extra_restricted
        if dt == "Purchase Invoice":
            invoices = docs
        normal = [purchase_record(d, order) for d in docs if not d.get("is_return")]
        returns = [purchase_record(d, order) for d in docs if d.get("is_return")]
        sections.append(dict(title=label, records=normal, restricted=restricted))
        sections.append(dict(title="Receipt returns" if dt == "Purchase Receipt" else "Credit notes / invoice returns",
                             records=returns, restricted=restricted))
    invoice_names = {d.name for d in invoices}
    refs = [("Purchase Order", order)] + [("Purchase Invoice", n) for n in sorted(invoice_names)]
    payment_names, journal_names, request_names = set(), set(), set()
    for dt, name in refs:
        payment_names |= candidates("Payment Entry Reference", {"reference_doctype": dt, "reference_name": name})
        journal_names |= candidates("Journal Entry Account", {"reference_type": dt, "reference_name": name})
        request_names |= candidates("Payment Request", {"reference_doctype": dt, "reference_name": name}, "name")
    for doc in invoices:
        for advance in doc.get("advances") or []:
            if advance.reference_type == "Payment Entry":
                payment_names.add(advance.reference_name)
            elif advance.reference_type == "Journal Entry":
                journal_names.add(advance.reference_name)
    if invoice_names:
        payment_names |= candidates("BS Payment Source", {"purchase_invoice": ["in", sorted(invoice_names)],
                                                           "company": po.company}, "payment_entry")
        for dt, names in (("Payment Entry", payment_names), ("Journal Entry", journal_names)):
            names |= candidates("Payment Ledger Entry", {"voucher_type": dt, "against_voucher_type": "Purchase Invoice",
                "against_voucher_no": ["in", sorted(invoice_names)], "company": po.company}, "voucher_no")
    for dt, names, label in (("Payment Entry", payment_names, "Payments"),
                            ("Journal Entry", journal_names, "Journal Entries"),
                            ("Payment Request", request_names, "Payment Requests")):
        docs, restricted = visible(dt, names, po.company)
        values = []
        for doc in docs:
            value = header(doc)
            if dt == "Payment Entry":
                relevant = [r for r in doc.references if (r.reference_doctype, r.reference_name) in refs]
                value["shared"] = any((r.reference_doctype, r.reference_name) not in refs for r in doc.references)
                value["facts"] += [["Payment type", doc.payment_type], ["Paid from", doc.paid_from],
                    ["Paid to", doc.paid_to], ["Payment amount (whole payment)", flt(doc.paid_amount)],
                    ["Paid from currency", doc.paid_from_account_currency], ["Bank reference", doc.reference_no or ""]]
                value["tables"].append(table("Current allocations to this PO or its invoices",
                    ["Reference type", "Reference", "Allocated amount"],
                    [[r.reference_doctype, r.reference_name, flt(r.allocated_amount)] for r in relevant]))
                value["note"] = "Allocations are to whole invoices, which may cover several POs. Historical or advance links may have no current reference row. Draft and cancelled payments do not count as paid."
            elif dt == "Journal Entry":
                value["facts"] += [["Journal type", doc.voucher_type], ["Reference", doc.cheque_no or ""]]
                value["tables"].append(table("Journal lines · account currencies",
                    ["Account", "Currency", "Debit", "Credit", "Reference type", "Reference"],
                    [[r.account, r.account_currency, flt(r.debit_in_account_currency), flt(r.credit_in_account_currency),
                      r.reference_type, r.reference_name] for r in doc.accounts]))
                value["note"] = "Full journal shown; it may include entries unrelated to this PO. Journal code on an invoice is a reference and does not create a separate Journal Entry."
            else:
                value["facts"] += [["Reference type", doc.reference_doctype], ["Reference", doc.reference_name],
                    ["Amount", flt(doc.grand_total)], ["Currency", doc.currency]]
            gl = ledger(doc) if dt != "Payment Request" else None
            if gl is not None:
                value["tables"].append(gl)
            value["ledgerRestricted"] = dt != "Payment Request" and gl is None
            values.append(value)
        sections.append(dict(title=label, records=values, restricted=restricted))
    return dict(order=order, company=po.company, sections=sections)
