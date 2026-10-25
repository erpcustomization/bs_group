"""Simple Lead outcomes, retaining ERPNext's downstream document links."""
from datetime import timedelta
from html import unescape
import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime, strip_html

ACTIVE = ("Lead", "Open", "Replied", "Interested", "Delayed")
CLOSED = ("Opportunity", "Quotation", "Converted", "Lost Quotation")


def overdue(creation, now=None):
    return bool(creation and get_datetime(creation) <= (now or now_datetime()) - timedelta(hours=24))


def linked_outcome(name):
    if not name:
        return None
    if frappe.db.exists("Customer", {"lead_name": name}):
        return "Converted"
    if frappe.db.exists("Opportunity", {"opportunity_from": "Lead", "party_name": name}):
        return "Opportunity"
    if frappe.db.exists("Quotation", {"quotation_to": "Lead", "party_name": name, "docstatus": ["!=", 2]}):
        return "Quotation"
    return None


def before_validate(doc, method=None):
    doc.flags.bsi_requested_lead_status = doc.status


def validate(doc, method=None):
    if "Dropped" not in (doc.meta.get_field("status").options or "").splitlines():
        return
    requested = doc.flags.get("bsi_requested_lead_status", doc.status)
    previous = doc.get_doc_before_save()
    linked = linked_outcome(None if doc.is_new() else doc.name)
    if requested == "Dropped" and (not previous or previous.status != "Dropped"):
        if linked:
            frappe.throw(_("This Lead already has a linked sales document and cannot be dropped."))
        old_notes = {n.name: n.note for n in (previous.notes if previous else [])}
        fresh = [n for n in (doc.notes or []) if n.note != old_notes.get(n.name)]
        if not any(unescape(strip_html(n.note or "")).replace("\xa0", " ").strip() for n in fresh):
            frappe.throw(_("Enter a reason in Notes before dropping this Lead."))
        for note in fresh:
            note.added_by = frappe.session.user
            note.added_on = now_datetime()
    if requested in CLOSED and not linked and (not previous or previous.status != requested):
        frappe.throw(_("Use Convert to Opportunity and save the Opportunity to close this Lead."))
    if linked:
        # Preserve native customer/quotation progression; any saved Opportunity closes intake.
        doc.status = doc.status if doc.status in CLOSED else linked
    elif requested == "Dropped":
        doc.status = "Dropped"
    elif requested in ACTIVE or not requested:
        doc.status = "Delayed" if not doc.is_new() and overdue(doc.creation) else "Open"
    elif previous and requested == previous.status:
        # Retain historical Do Not Contact and other terminal records without inventing notes.
        doc.status = requested
    else:
        frappe.throw(_("Choose Open, Convert to Opportunity, or Dropped."))


def guard_conversion(doc, method=None):
    if doc.opportunity_from == "Lead" and doc.party_name:
        if frappe.db.get_value("Lead", doc.party_name, "status") in ("Dropped", "Do Not Contact"):
            frappe.throw(_("Reopen the Lead before converting it to an Opportunity."))


@frappe.whitelist()
def make_opportunity(source_name):
    lead = frappe.get_doc("Lead", source_name)
    lead.check_permission("write")
    if lead.status in ("Dropped", "Do Not Contact"):
        frappe.throw(_("Reopen the Lead before converting it to an Opportunity."))
    if linked_outcome(lead.name):
        frappe.throw(_("This Lead is already closed. Use its existing Connections."))
    from erpnext.crm.doctype.lead.lead import make_opportunity as native_mapper
    return native_mapper(source_name)


def mark_delayed():
    if "Delayed" not in (frappe.get_meta("Lead").get_field("status").options or "").splitlines():
        return
    cutoff = now_datetime() - timedelta(hours=24)
    rows = frappe.get_all("Lead", filters={"status": ["in", [s for s in ACTIVE if s != "Delayed"]], "creation": ["<=", cutoff]}, fields=["name", "status"])
    for row in rows:
        outcome = linked_outcome(row.name)
        target = outcome or "Delayed"
        if row.status == target:
            continue
        # Conditional write protects a concurrent drop/conversion. Do not reset modified/follow-up time.
        frappe.db.sql("UPDATE `tabLead` SET status=%s WHERE name=%s AND status=%s", (target, row.name, row.status))


def setup():
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    field = frappe.get_meta("Lead").get_field("status")
    options = list(dict.fromkeys((field.options or "").splitlines() + ["Delayed", "Dropped"]))
    make_property_setter("Lead", "status", "options", "\n".join(options), "Text")
    make_property_setter("Lead", "status", "default", "Open", "Text")
    frappe.clear_cache(doctype="Lead")
