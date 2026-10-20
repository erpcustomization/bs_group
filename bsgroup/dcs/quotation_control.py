"""Validate the live DCS position before quoting or ordering."""
from bsgroup.dcs.currency import money_round, money_tolerance
import frappe
from frappe.utils import flt

def validate_quotation(doc, method=None):
    if doc.docstatus == 2 or not doc.get("custom_deal_cost_sheet"):
        return
    sheet = frappe.get_doc("Deal Cost Sheet", doc.custom_deal_cost_sheet, for_update=doc.docstatus == 1)
    if doc.docstatus == 1:
        from bsgroup.dcs.obligation import assert_clearance
        assert_clearance(sheet)
    validate_position(sheet, doc)
    if doc.docstatus == 0:
        doc.custom_dcs_revision_reference = sheet.custom_revision_reference

def validate_position(sheet, quotation):
    from bsgroup.dcs.input_validation import validate_position as validate_commercial_inputs
    validate_commercial_inputs(sheet)
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_deal_identity
    if sheet.docstatus != 1 or sheet.custom_superseded_by:
        frappe.throw("This quotation refers to a cancelled, unsubmitted or superseded Deal Cost Sheet.")
    currency = sheet.currency or frappe.db.get_value("Company", sheet.company, "default_currency")
    if currency and quotation.currency != currency:
        frappe.throw("Quotation currency differs from the Deal Cost Sheet.")
    if quotation_deal_identity(sheet, quotation):
        frappe.throw("Quotation identity does not match its Deal Cost Sheet.")
    if quotation.get("custom_dcs_superseded_revision"):
        frappe.throw("This submitted quotation is superseded. Create and submit a replacement quotation for the current DCS revision.")
    reference = quotation.get("custom_dcs_revision_reference")
    if quotation.docstatus == 1 and reference and reference != sheet.custom_revision_reference:
        frappe.throw("Quotation is stale: its DCS revision has changed. Review a replacement quotation.")
    selling = sheet.custom_working_total_selling if sheet.custom_dcs_revision_no else sheet.total_selling
    if abs(flt(quotation.total) - flt(selling)) > money_tolerance(currency):
        frappe.throw("Quotation selling total differs from the current DCS position.")
    expected = sorted((r.item_code, flt(r.qty), money_round(r.selling_rate, currency)) for r in sheet.items)
    charges = sum(flt(r.get("selling_amount")) for r in sheet.addtional_charges or [])
    if charges:
        item = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
        expected.append((item, 1.0, money_round(charges, currency)))
        expected.sort()
    actual = sorted((r.item_code, flt(r.qty), money_round(r.rate, currency)) for r in quotation.items)
    if expected != actual:
        frappe.throw("Quotation scope or selling rates differ from the current DCS BOQ.")

def validate_sales_order(doc, method=None):
    if doc.docstatus == 2:
        return
    names = {r.get("prevdoc_docname") for r in doc.items if r.get("prevdoc_docname")}
    for name in sorted(names):
        quotation = frappe.get_doc("Quotation", name)
        if not quotation.get("custom_deal_cost_sheet"):
            continue
        sheet = frappe.get_doc("Deal Cost Sheet", quotation.custom_deal_cost_sheet, for_update=True)
        from bsgroup.dcs.obligation import assert_clearance
        assert_clearance(sheet)
        validate_position(sheet, quotation)
        from bsgroup.dcs.commercial_authority import authorised_position
        if not authorised_position(sheet):
            frappe.throw("The current DCS position requires recorded manager approval before a Sales Order can be created or submitted.")

def supersede_submitted(sheet):
    changes = []
    for row in frappe.get_all("Quotation", filters={"custom_deal_cost_sheet": sheet.name, "docstatus": 1},
                              fields=["name", "custom_dcs_superseded_revision"]):
        if row.custom_dcs_superseded_revision == sheet.custom_revision_reference:
            continue
        frappe.db.set_value("Quotation", row.name, "custom_dcs_superseded_revision", sheet.custom_revision_reference)
        changes.append({"dt": "Quotation", "dn": row.name, "field": "custom_dcs_superseded_revision",
                        "old": row.custom_dcs_superseded_revision, "new": sheet.custom_revision_reference})
    return changes

@frappe.whitelist()
def make_sales_order(source_name, target_doc=None, args=None):
    quotation = frappe.get_doc("Quotation", source_name)
    quotation.check_permission("read")
    if quotation.get("custom_deal_cost_sheet"):
        sheet = frappe.get_doc("Deal Cost Sheet", quotation.custom_deal_cost_sheet, for_update=True)
        from bsgroup.dcs.obligation import assert_clearance
        assert_clearance(sheet)
        validate_position(sheet, quotation)
        from bsgroup.dcs.commercial_authority import authorised_position
        if not authorised_position(sheet):
            frappe.throw("The current DCS position requires recorded manager approval before conversion to Sales Order.")
    from erpnext.selling.doctype.quotation.quotation import make_sales_order as core_make_sales_order
    return core_make_sales_order(source_name, target_doc, args)


def guard_lineage(doc, method=None):
    previous = doc.get_doc_before_save()
    if not previous:
        return
    if previous.get("custom_deal_cost_sheet"):
        if doc.get("custom_deal_cost_sheet") != previous.custom_deal_cost_sheet:
            frappe.throw("Submitted quotation DCS linkage cannot be changed.")
        fields = ("item_code", "qty", "rate", "amount", "uom", "conversion_factor", "discount_percentage", "discount_amount")
        before = [tuple(r.get(f) for f in fields) for r in previous.items]
        after = [tuple(r.get(f) for f in fields) for r in doc.items]
        if before != after or any(doc.get(f) != previous.get(f) for f in ("currency", "conversion_rate", "total", "grand_total", "discount_amount", "additional_discount_percentage")):
            frappe.throw("Submitted DCS quotation prices and scope are frozen. Create a replacement quotation.")
    for field in ("custom_dcs_revision_reference", "custom_dcs_superseded_revision"):
        if str(doc.get(field) or "") != str(previous.get(field) or ""):
            frappe.throw("Submitted quotation lineage is governed by the DCS service and cannot be edited.")

@frappe.whitelist()
def update_child_qty_rate(parent_doctype, trans_items, parent_doctype_name, child_docname="items"):
    if parent_doctype == "Purchase Order":
        from bsgroup.procurement import guard_item_update
        guard_item_update(parent_doctype_name)
    # Core updates child rows directly before saving the parent; a document hook
    # alone cannot compare the original prices or protect them atomically.
    if parent_doctype == "Quotation":
        quotation = frappe.get_doc("Quotation", parent_doctype_name, for_update=True)
        quotation.check_permission("write")
        if quotation.docstatus == 1 and quotation.get("custom_deal_cost_sheet"):
            frappe.throw("Submitted DCS quotation prices and scope are frozen. Create a replacement quotation for the current revision.")
    from erpnext.controllers.accounts_controller import update_child_qty_rate as core_update
    return core_update(parent_doctype, trans_items, parent_doctype_name, child_docname)
