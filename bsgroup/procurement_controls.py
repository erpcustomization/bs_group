"""Shared BS purchasing controls. Enforced by document hooks and native forms."""
import hashlib
import json
from pathlib import Path

import frappe
from frappe.utils import flt


PROCUREMENT_APPROVER = "mohan@bitssecureit.com"
APPROVER_ROLE = "BS Procurement Approver"


def approver_details():
    name, enabled = frappe.get_cached_value(
        "User", PROCUREMENT_APPROVER, ["full_name", "enabled"]) or (None, 0)
    return dict(user=PROCUREMENT_APPROVER, name=name or PROCUREMENT_APPROVER, enabled=bool(enabled))


def approval_allowed(doc, throw=False):
    """BS purchasing decisions belong to Mohan, including documents he prepared."""
    if doc.doctype not in ("Material Request", "Purchase Order", "Purchase Invoice") or not doc.get("custom_bsp_managed"):
        return independent(doc, throw=throw)
    required = "Accounts Manager" if doc.doctype == "Purchase Invoice" else "Purchase Manager"
    allowed = (
        frappe.session.user == PROCUREMENT_APPROVER
        and bool(frappe.get_cached_value("User", PROCUREMENT_APPROVER, "enabled"))
        and {APPROVER_ROLE, required}.issubset(frappe.get_roles())
    )
    if not allowed and throw:
        frappe.throw("Only Mohan Babu (mohan@bitssecureit.com) can approve or reject "
                     "BS Purchase Requisitions, Purchase Orders and Payment Orders.", frappe.PermissionError)
    return bool(allowed)


def preparers(doc):
    result = set(json.loads(doc.get("custom_bsp_preparers") or "[]"))
    if doc.owner:
        result.add(doc.owner)
    # Existing submissions predate the preparer field.
    for event in json.loads(doc.get("custom_bsp_history") or "[]"):
        if event.get("action") in ("Draft", "Saved", "Pending Approval"):
            result.add(event.get("actor"))
    return result - {None, ""}


def independent(doc, throw=False):
    allowed = frappe.session.user not in preparers(doc)
    if not allowed and throw:
        frappe.throw("The creator, preparer or sender cannot approve or reject this submission. "
                     "A different authorised approver is required.", frappe.PermissionError)
    return allowed


def track_preparers(doc, old, state, old_state):
    # Never trust a submitted client value, including new documents and amendments.
    people = preparers(old) if old else {doc.owner or frappe.session.user}
    if state in ("Draft", "Rejected") and state == old_state or not old:
        people.add(frappe.session.user)
    if state == "Pending Approval" and old_state != state:
        people.add(frappe.session.user)
    doc.custom_bsp_preparers = json.dumps(sorted(people))
    if state in ("Approved", "Rejected") and state != old_state:
        approval_allowed(doc, throw=True)


def business_values(doc):
    """All schema fields except explicit lifecycle/fulfilment bookkeeping."""
    excluded = {
        "workflow_state", "status", "amended_from",
        "custom_bsp_history", "custom_bsp_reason", "custom_bsp_preparers",
        "custom_bsp_approval_state", "custom_bsp_submission_version",
        "per_received", "per_billed", "per_ordered", "per_returned",
        "advance_paid", "received_qty", "returned_qty", "billed_amt",
        "ordered_qty", "produced_qty", "received_by", "delivered_by_supplier",
        # Regenerated presentation and tax-allocation cache; the underlying
        # tax rows, rates and amounts remain part of the locked document.
        "other_charges_calculation", "item_wise_tax_details",
    }
    result = {}
    for field in doc.meta.fields:
        if field.fieldname in excluded or field.fieldtype in (
            "Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"):
            continue
        value = doc.get(field.fieldname)
        if field.fieldtype in ("Table", "Table MultiSelect"):
            value = [business_values(row) for row in value or []]
        elif field.fieldtype in ("Float", "Currency", "Percent"):
            value = flt(value)
        elif field.fieldtype in ("Int", "Check"):
            value = int(value or 0)
        elif value is None:
            value = ""
        result[field.fieldname] = value
    return result


def evidence(file):
    if file.is_folder or not file.is_private or not file.file_url or not file.file_url.startswith("/private/files/"):
        frappe.throw("Quotation evidence must be a private uploaded file.")
    ext = Path(file.file_name or "").suffix.lower()
    if ext not in {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".doc", ".docx"}:
        frappe.throw("Upload a PDF, image, spreadsheet or Word supplier quotation.")
    content = file.get_content()
    content = content.encode() if isinstance(content, str) else content
    if not content:
        frappe.throw("Quotation evidence must not be empty.")
    return hashlib.sha256(content).hexdigest()


def validate_supplier_details(doc):
    if not doc.supplier_address or not doc.address_display:
        frappe.throw("Select the supplier address before sending the PO for approval.")
    if not doc.contact_person or not doc.contact_display:
        frappe.throw("Select the supplier contact before sending the PO for approval.")
    for doctype, name in (("Address", doc.supplier_address), ("Contact", doc.contact_person)):
        if not frappe.db.exists("Dynamic Link", dict(parenttype=doctype, parent=name,
                                link_doctype="Supplier", link_name=doc.supplier)):
            frappe.throw("The PO address and contact must belong to the selected supplier.")
    if not doc.taxes_and_charges:
        frappe.throw("Select an explicit purchase tax template, including the applicable zero-tax treatment.")
    template = frappe.get_doc("Purchase Taxes and Charges Template", doc.taxes_and_charges)
    if template.disabled or template.company != doc.company:
        frappe.throw("Select an enabled purchase tax template for this company.")
    # No VAT rate is invented: tax treatment is selected from the configured master.


def closed_stock_qty(row):
    # Keep received and already-billed quantities committed when a PO is closed.
    billed_qty = flt(row.stock_qty) * min(1, max(0, flt(row.billed_amt) / flt(row.amount))) if row.amount else 0
    return min(flt(row.stock_qty), max(flt(row.received_qty) * flt(row.conversion_factor or 1), billed_qty))


class ProcurementOrderMixin:
    def _update_children(self, args, update_modified):
        if (args.get("source_dt") == "Purchase Order Item"
                and args.get("target_dt") == "Material Request Item"
                and args.get("target_field") == "ordered_qty"):
            from bsgroup.procurement_quantities import effective_source_field
            args = dict(args, source_field=effective_source_field(args["source_field"]))
        return super()._update_children(args, update_modified)

    def update_status(self, status):
        previous_status = self.status
        if not self.get("custom_bsp_managed") and self.status == "Closed" and status != "Closed":
            frappe.throw("Create a new Purchase Order from an approved BS Purchase Requisition; "
                         "historical orders without a BS PR cannot be reopened.")
        if self.get("custom_bsp_managed"):
            from bsgroup.procurement import allocation, lock_request
            request = lock_request(self.custom_bsp_material_request)
            if self.status == "Closed" and status != "Closed":
                # Native reopen uses db_set and otherwise bypasses validate().
                allocation(self, request)
        result = super().update_status(status)
        if self.get("custom_bsp_managed"):
            self.update_prevdoc_status()
            self.update_requested_qty()
            from bsgroup.utils.project_cost_baseline import (
                recalculate_project_baseline, check_cost_overrun_for_project)
            if previous_status == "Closed" and status != "Closed":
                for project in sorted({self.project, *(row.project for row in self.items)} - {None, ""}):
                    check_cost_overrun_for_project(
                        project, raise_from=f"Purchase Order {self.name}", force_block=True)
            recalculate_project_baseline(self)
        return result
