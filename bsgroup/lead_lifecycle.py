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
    doc.flags.bsi_requested_lead_title = doc.title


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


    # Native Lead validation derives Title from organization/name. Preserve an
    # explicitly edited title while allowing the normal initial default.
    incoming_title = doc.flags.get("bsi_requested_lead_title")
    if previous and incoming_title != previous.title:
        if previous.status != "Open" or doc.status != "Open" or linked or overdue(doc.creation):
            frappe.throw(_("Title can only be edited while the Lead is Open."))
        if not (incoming_title or "").strip():
            frappe.throw(_("Enter a Title."))
        doc.title = incoming_title.strip()
    elif previous and previous.title and previous.title != (previous.company_name or previous.lead_name):
        doc.title = previous.title
    elif not previous and (incoming_title or "").strip():
        doc.title = incoming_title.strip()


def guard_conversion(doc, method=None):
    if doc.opportunity_from == "Lead" and doc.party_name:
        frappe.db.sql("SELECT name FROM `tabLead` WHERE name=%s FOR UPDATE", doc.party_name)
        if linked_outcome(doc.party_name):
            frappe.throw(_("This Lead already has an Opportunity. Open the existing Opportunity."))
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
    opportunity = native_mapper(source_name)
    opportunity.custom_subject = lead.title or lead.company_name or lead.lead_name
    opportunity.custom_enquiry = lead.get("custom_requirement") or ""
    opportunity.custom_organization_name = lead.company_name
    opportunity.custom_contact_person_name = lead.lead_name
    opportunity.opportunity_owner = frappe.session.user
    opportunity.company = lead.company
    if not opportunity.currency and lead.company:
        opportunity.currency = frappe.db.get_value("Company", lead.company, "default_currency")
    return opportunity


def mark_delayed():
    if "Delayed" not in (frappe.get_meta("Lead").get_field("status").options or "").splitlines():
        return
    # Repair pre-existing stale conversion states after an Opportunity was deleted.
    for row in frappe.get_all("Lead", filters={"status": "Opportunity"}, fields=["name", "creation"]):
        reopen_without_opportunity(row.name)
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
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Lead": [
        {"fieldname": "custom_requirement", "label": "Requirement", "fieldtype": "Small Text", "insert_after": "company_name"},
        {"fieldname": "custom_next_follow_up_date", "label": "Next Follow Up Date", "fieldtype": "Date", "insert_after": "phone", "placeholder": "Select date"},
        {"fieldname": "custom_bsi_status_tab", "label": "Status", "fieldtype": "Tab Break", "insert_after": "notes"},
        {"fieldname": "custom_bsi_status_controls", "label": "Status", "fieldtype": "HTML", "insert_after": "custom_bsi_status_tab"},
    ]})
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    field = frappe.get_meta("Lead").get_field("status")
    options = list(dict.fromkeys((field.options or "").splitlines() + ["Delayed", "Dropped"]))
    make_property_setter("Lead", "status", "options", "\n".join(options), "Text")
    make_property_setter("Lead", "status", "default", "Open", "Text")
    frappe.clear_cache(doctype="Lead")


def load_responsibility(doc, method=None):
    """Conversion moves open ToDos to Opportunity; show its current assignee on Lead."""
    doc.check_permission("read")
    users = frappe.get_all("ToDo", filters={"reference_type": "Lead", "reference_name": doc.name, "status": "Open"}, pluck="allocated_to")
    source = "Lead"
    if not users:
        opportunities = frappe.get_list("Opportunity", filters={"opportunity_from": "Lead", "party_name": doc.name}, pluck="name", limit_page_length=0)
        if opportunities:
            users = frappe.get_all("ToDo", filters={"reference_type": "Opportunity", "reference_name": ["in", opportunities], "status": "Open"}, pluck="allocated_to")
            source = "Opportunity"
    doc.set_onload("bsi_sales_responsibility", {"source": source, "users": [
        {"user": user, "full_name": frappe.db.get_value("User", user, "full_name") or user}
        for user in dict.fromkeys(users) if user
    ]})


def reopen_without_opportunity(name):
    """Reopen only an orphaned Opportunity state; preserve real downstream links."""
    lead = frappe.db.get_value("Lead", name, ["status", "creation"], as_dict=True)
    if not lead or lead.status != "Opportunity" or linked_outcome(name):
        return
    target = "Delayed" if overdue(lead.creation) else "Open"
    frappe.db.sql("UPDATE `tabLead` SET status=%s WHERE name=%s AND status='Opportunity'", (target, name))
    frappe.clear_document_cache("Lead", name)


def opportunity_deleted(doc, method=None):
    if doc.opportunity_from == "Lead" and doc.party_name:
        reopen_without_opportunity(doc.party_name)


@frappe.whitelist()
def confirm_opportunity(source_name, subject, opportunity_amount=None, intake=None):
    """Create the linked Opportunity; qualification may follow the Lead conversion."""
    lead = frappe.get_doc("Lead", source_name)
    lead.check_permission("write")
    subject = (subject or "").strip()
    if not subject:
        frappe.throw(_("Enter an Opportunity subject."))
    # Serialize confirmations for this Lead so repeat clicks cannot create duplicates.
    frappe.db.sql("SELECT name FROM `tabLead` WHERE name=%s FOR UPDATE", source_name)
    opportunity = make_opportunity(source_name)
    opportunity.opportunity_amount = opportunity_amount
    opportunity.opportunity_owner = frappe.session.user
    from bsgroup.opportunity_intake import FIELDS
    intake = frappe.parse_json(intake) if intake else {}
    opportunity.flags.deferred_lead_intake = not intake
    for field in FIELDS:
        opportunity.set(field, intake.get(field))
    opportunity.company = lead.company
    if not opportunity.currency and lead.company:
        opportunity.currency = frappe.db.get_value("Company", lead.company, "default_currency")
    if opportunity.meta.has_field("custom_subject"):
        opportunity.custom_subject = subject
    if opportunity.meta.has_field("custom_organization_name"):
        opportunity.custom_organization_name = lead.company_name
    if frappe.db.exists("Sales Stage", "Proposal"):
        opportunity.sales_stage = "Proposal"
    opportunity.insert()
    return opportunity.name


@frappe.whitelist()
def list_owner_labels(names, doctype="Lead"):
    """Return profile labels only for owners of Leads the caller can read."""
    if doctype not in ("Lead", "Opportunity"):
        frappe.throw(_("Invalid document type."))
    owner_field = "lead_owner" if doctype == "Lead" else "opportunity_owner"
    names = frappe.parse_json(names)
    if not isinstance(names, list) or len(names) > 2500:
        frappe.throw(_("Invalid Lead list."))
    leads = frappe.get_list(doctype, filters={"name": ["in", names]},
                            fields=[owner_field], limit_page_length=len(names)) if names else []
    owners = list({row.get(owner_field) for row in leads if row.get(owner_field)})
    if not owners:
        return {}
    users = frappe.get_all("User", filters={"name": ["in", owners]},
                           fields=["name", "first_name", "full_name"])
    return {row.name: {"initial": (row.first_name or "").strip()[:1].upper() or "?",
                       "full_name": row.full_name or row.name} for row in users}
