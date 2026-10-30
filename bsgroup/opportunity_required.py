"""Downstream sales records must belong to an existing Opportunity."""
import frappe
from frappe import _


DOCTYPES = ("Presales Request", "Deal Cost Sheet", "Quotation", "Site Survey Request")


def validate(doc, method=None):
    if doc.doctype not in DOCTYPES:
        return
    previous = doc.get_doc_before_save()
    opportunity = doc.get("opportunity")
    # Preserve editing of historical records; never permit a new orphan or
    # removal/replacement of a link without validating the new source.
    if not doc.is_new() and previous and previous.get("opportunity") == opportunity:
        return
    if not opportunity:
        frappe.throw(_("Create or select an Opportunity before creating {0}.").format(_(doc.doctype)))
    source = frappe.db.get_value("Opportunity", opportunity, ["name", "company"], as_dict=True)
    if not source:
        frappe.throw(_("Select an existing Opportunity before creating {0}.").format(_(doc.doctype)))
    if doc.get("company") and source.company and doc.company != source.company:
        frappe.throw(_("The document and its Opportunity must belong to the same company."))
    if not doc.flags.ignore_permissions:
        from bsgroup.scoped_sales_access import scope, PRESALES
        if doc.doctype == "Quotation" and scope() == PRESALES:
            sheet = frappe.get_doc("Deal Cost Sheet", doc.get("custom_deal_cost_sheet"))
            sheet.check_permission("read")
            if sheet.opportunity != opportunity:
                frappe.throw(_("The quotation must use its Deal Cost Sheet's Opportunity."))
            return
        frappe.get_doc("Opportunity", opportunity).check_permission("read")
