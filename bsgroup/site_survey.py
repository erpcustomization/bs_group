"""Transactional Opportunity -> survey intake -> Presales hand-off."""
import frappe
from frappe import _
from frappe.utils import cint, nowdate

WAITING = "Awaiting Site Survey Results"
RECEIVED = "Site Survey Results Received"
DEFERRED_FIELDS = ("presales_owner", "due_date", "priority", "solution_summary", "scope_details")
FLAGS = ("custom_elv_site_survey_required", "custom_technical_site_survey_required")


def survey_selected(doc):
    return cint(doc.get("custom_presales_required")) and any(cint(doc.get(f)) for f in FLAGS)


def validate_opportunity(doc, method=None):
    if any(cint(doc.get(f)) for f in FLAGS) and not cint(doc.get("custom_presales_required")):
        frappe.throw(_("Enable Presales Support Required before selecting a site survey."))
    if doc.is_new() or not frappe.db.exists("DocType", "Site Survey Request"):
        return
    linked = frappe.db.get_value("Site Survey Request", {"opportunity": doc.name}, ["name", "status"], as_dict=True)
    if linked:
        before = doc.get_doc_before_save()
        if before and any(doc.get(f) != before.get(f) for f in (*FLAGS, "custom_presales_required", "party_name", "opportunity_from", "company")):
            frappe.throw(_("A Site Survey Request already exists. Keep its survey options and customer unchanged; manage the request in Projects."))


def create_requests(doc, method=None):
    if not survey_selected(doc):
        return
    # The Opportunity save and both requests share a transaction. A failure rolls
    # back everything; row locking and the unique link prevent repeat-click duplicates.
    doc.check_permission("write")
    frappe.db.get_value("Opportunity", doc.name, "name", for_update=True)
    existing = frappe.db.get_value("Site Survey Request", {"opportunity": doc.name}, "name")
    if existing:
        return
    presales_name = frappe.db.get_value("Presales Request", {
        "opportunity": doc.name, "docstatus": ["<", 2], "status": ["!=", "Cancelled"]})
    if presales_name:
        pre = frappe.get_doc("Presales Request", presales_name)
        if pre.docstatus or pre.status not in ("Draft", "Open", "Assigned", WAITING):
            frappe.throw(_("This Opportunity already has a Presales Request in progress. Arrange its survey from that request before changing the Opportunity."))
    survey = frappe.get_doc({"doctype": "Site Survey Request", "opportunity": doc.name,
                            "status": "Requested", "requested_by": frappe.session.user,
                            "request_date": nowdate()})
    survey.flags.from_opportunity = True
    # Intake creation is a bounded consequence of an authorised Opportunity save;
    # sales users do not gain general write access to project/presales documents.
    survey.insert(ignore_permissions=True)
    if not presales_name:
        pre = frappe.get_doc({"doctype": "Presales Request", "opportunity": doc.name,
            "party_type": doc.opportunity_from, "party": doc.party_name,
            "company": doc.company, "subject": doc.get("custom_subject") or doc.title or doc.name,
            "estimated_value": doc.opportunity_amount, "requested_by": frappe.session.user,
            "request_date": nowdate(), "expected_close_date": doc.expected_closing,
            "is_new_customer": int(doc.opportunity_from == "Lead")})
    pre.custom_site_survey_request = survey.name
    pre.status = WAITING
    pre.save(ignore_permissions=True)
    survey.db_set("presales_request", pre.name, update_modified=False)
    doc.db_set("custom_site_survey_request", survey.name, update_modified=False)
    doc.db_set("status", "Presales Request", update_modified=False)


def validate_presales(doc, method=None):
    link = doc.get("custom_site_survey_request")
    survey = frappe.db.get_value("Site Survey Request", link, ["opportunity", "status"], as_dict=True) if link else None
    if link and (not survey or survey.opportunity != doc.opportunity):
        frappe.throw(_("The Site Survey Request must belong to this Opportunity."))
    if doc.status in (WAITING, RECEIVED) and not survey:
        frappe.throw(_("A linked Site Survey Request is required for this status."))
    if doc.status == RECEIVED and survey.status != "Completed":
        frappe.throw(_("Complete the site survey and record its results first."))
    if survey and survey.status != "Completed" and doc.status not in (WAITING, "Cancelled", "On Hold"):
        frappe.throw(_("This Presales Request is awaiting site survey results."))
    if not (survey and doc.status in (WAITING, RECEIVED, "Cancelled", "On Hold")):
        missing = [doc.meta.get_label(f) for f in DEFERRED_FIELDS if not doc.get(f)]
        if missing:
            frappe.throw(_("Complete the Presales details before proceeding: {0}").format(", ".join(missing)))


def survey_query(user=None):
    user = user or frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & {"System Manager", "Projects Manager", "Presales", "Sales Manager"}:
        return ""
    who = frappe.db.escape(user)
    return f"(`tabSite Survey Request`.salesperson={who} OR `tabSite Survey Request`.requested_by={who} OR `tabSite Survey Request`.assigned_to={who})"


def presales_query(user=None):
    from bsgroup.permissions import get_team_records_condition
    user = user or frappe.session.user
    base = get_team_records_condition(user, "Presales Request")
    if not base or "Presales" not in frappe.get_roles(user) or not frappe.get_meta("Presales Request").has_field("custom_site_survey_request"):
        return base
    # The presales team needs a real intake queue before an owner is assigned.
    # Native Company/User Permissions still apply to the list query.
    return f"({base} OR (`tabPresales Request`.custom_site_survey_request IS NOT NULL AND `tabPresales Request`.custom_site_survey_request != '' AND `tabPresales Request`.status IN ({frappe.db.escape(WAITING)}, {frappe.db.escape(RECEIVED)})))"


def survey_permission(doc, user=None, permission_type=None, ptype=None):
    user = user or frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & {"System Manager", "Projects Manager", "Presales", "Sales Manager"}:
        return None
    if user not in (doc.salesperson, doc.requested_by, doc.assigned_to):
        return False
    return None
