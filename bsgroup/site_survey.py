"""Transactional Opportunity -> survey intake -> Presales hand-off."""
import frappe
from frappe import _
from frappe.utils import cint, nowdate

WAITING = "Awaiting Site Survey Results"
RECEIVED = "Site Survey Results Received"
DEFERRED_FIELDS = ("presales_owner", "due_date", "priority", "solution_summary", "scope_details")
FLAGS = ("custom_elv_site_survey_required", "custom_technical_site_survey_required")


def require_late_survey_manager():
    if frappe.session.user != "mohan@bitssecureit.com":
        frappe.throw(_("Only Mohan can request a late site survey after Opportunity submission."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def request_supplementary_survey(opportunity, team, instructions, location, contact_name, contact_phone):
    """A late survey supplements the current work; it never restarts intake."""
    require_late_survey_manager()
    doc = frappe.get_doc("Opportunity", opportunity, for_update=True)
    doc.check_permission("write")
    if doc.docstatus == 2 or doc.status in ("Lost", "Closed"):
        frappe.throw(_("A site survey cannot be requested for a closed Opportunity."))
    existing = frappe.db.get_value("Site Survey Request", {"opportunity": doc.name}, "name")
    if existing:
        return {"name": existing, "created": False}
    if team not in ("ELV", "Technical Team", "ELV and Technical Team"):
        frappe.throw(_("Choose the site survey team."))
    values = dict(custom_survey_instructions=instructions, custom_survey_location=location,
        custom_survey_contact_name=contact_name, custom_survey_contact_phone=contact_phone)
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        frappe.throw(_("Enter survey instructions, location, contact name and phone."))
    # Build a request snapshot without changing the original qualification or
    # saving the Opportunity through hooks that dispatch presales/costing again.
    doc.update({key: value.strip() for key, value in values.items()})
    doc.custom_elv_site_survey_required = int(team in ("ELV", "ELV and Technical Team"))
    doc.custom_technical_site_survey_required = int(team in ("Technical Team", "ELV and Technical Team"))
    pre = None
    if cint(doc.get("custom_presales_required")):
        pre = frappe.db.get_value("Presales Request", {"opportunity": doc.name,
            "docstatus": ["<", 2], "status": ["!=", "Cancelled"]}, "name")
        if not pre:
            frappe.throw(_("This Opportunity requests presales support, but its active Presales Request is missing. Restore its presales link before requesting the survey."))
    rework_records = late_survey_rework_records(doc, pre)
    survey = frappe.get_doc(dict(doctype="Site Survey Request", opportunity=doc.name,
        supplementary_survey=1, status="Requested", requested_by=frappe.session.user,
        request_date=nowdate(), site_address=location.strip(),
        contact_person=contact_name.strip(), contact_phone=contact_phone.strip(),
        elv_required=doc.custom_elv_site_survey_required,
        technical_required=doc.custom_technical_site_survey_required,
        survey_request_details=request_details(doc), presales_request=pre))
    survey.flags.from_opportunity = True
    survey.insert(ignore_permissions=True)
    frappe.db.set_value("Opportunity", doc.name, "custom_site_survey_request", survey.name)
    if pre:
        # The request remains at its existing stage, including Costing in Progress.
        frappe.db.set_value("Presales Request", pre, "custom_site_survey_request", survey.name)
    mark_survey_rework(rework_records, survey.name)
    return {"name": survey.name, "created": True}


REWORK_REQUIRED = "Rework Required"


def late_survey_rework_records(opportunity, presales):
    sheets = frappe.get_all("Deal Cost Sheet", filters={"opportunity": opportunity.name,
        "docstatus": ["<", 2], "custom_record_authority": ["!=", "Superseded"]}, pluck="name")
    links = {"opportunity": opportunity.name}
    if sheets:
        links["custom_deal_cost_sheet"] = ["in", sheets]
    quotes = frappe.get_all("Quotation", filters={"docstatus": ["<", 2]},
        or_filters=links, pluck="name")
    records = []
    for name in sorted(sheets):
        sheet = frappe.get_doc("Deal Cost Sheet", name, for_update=True)
        if sheet.get("custom_deal_status") in ("Won", "Lost") or sheet.get("custom_award_state") == "Awarded":
            frappe.throw(_("A late site survey cannot be requested: the linked costing sheet is already Won, Lost or awarded."))
        records.append((sheet, "custom_deal_status"))
        if presales and sheet.get("presales_request") == presales:
            records.append((sheet, "custom_presales_status"))
    for name in sorted(quotes):
        quote = frappe.get_doc("Quotation", name, for_update=True)
        if quote.get("custom_pipeline_stage") in ("Won", "Lost") or quote.get("status") in ("Lost", "Ordered"):
            frappe.throw(_("A late site survey cannot be requested: linked quotation {0} is already Won or Lost.").format(name))
        records.append((quote, "custom_pipeline_stage"))
    if presales:
        records.append((frappe.get_doc("Presales Request", presales, for_update=True), "status"))
    return records


def mark_survey_rework(records, survey):
    for record, field in records:
        previous = record.get(field)
        if previous == REWORK_REQUIRED:
            continue
        frappe.db.set_value(record.doctype, record.name, field, REWORK_REQUIRED)
        frappe.clear_document_cache(record.doctype, record.name)
        frappe.get_doc(dict(doctype="Version", ref_doctype=record.doctype, docname=record.name,
            data=frappe.as_json(dict(changed=[[field, previous, REWORK_REQUIRED]],
                added=[], removed=[], row_changed=[])))).insert(ignore_permissions=True)
        record.add_comment("Info", _("Rework Required following late Site Survey Request {0}.").format(survey))


@frappe.whitelist()
def linked_survey_details(doctype, name):
    if doctype not in ("Opportunity", "Deal Cost Sheet", "Presales Request"):
        frappe.throw(_("Unsupported survey source."))
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    opportunity = doc.name if doctype == "Opportunity" else doc.get("opportunity")
    if not opportunity:
        return []
    filters = {"opportunity": opportunity}
    if doctype == "Presales Request":
        if not doc.get("custom_site_survey_request"):
            return []
        filters["name"] = doc.custom_site_survey_request
        filters["presales_request"] = doc.name
    # A reader of the linked business record can see its operational survey,
    # without granting access to other surveys or commercial Opportunity fields.
    return frappe.get_all("Site Survey Request", filters=filters,
        fields=["name", "status", "request_date", "planned_date", "assigned_to",
            "site_address", "contact_person", "contact_phone", "survey_request_details",
            "results", "attachment", "completed_on", "supplementary_survey"],
        order_by="creation desc")


@frappe.whitelist()
def opportunity_survey_results(name):
    opportunity = frappe.get_doc("Opportunity", name)
    opportunity.check_permission("read")
    rows = frappe.get_all("Site Survey Request", filters={"opportunity": name, "status": "Completed"},
        fields=["name", "results", "completed_on"], order_by="completed_on desc")
    return rows


@frappe.whitelist()
def presales_handoff(name):
    """Expose linked survey results to users allowed to read this request."""
    pre = frappe.get_doc("Presales Request", name)
    pre.check_permission("read")
    survey = frappe.db.get_value("Site Survey Request", pre.get("custom_site_survey_request"),
        ["status", "results", "supplementary_survey"], as_dict=True) if pre.get("custom_site_survey_request") else None
    label = pre.status
    if pre.status == "Costing in Progress":
        label = "Deal Cost Sheet in Progress"
    elif pre.status not in ("Cancelled", "Completed", "Won", "Lost", "Submitted to Sales", "Ready for Quotation", "On Hold", "Rework", REWORK_REQUIRED):
        label = "Awaiting Site Survey" if survey and not survey.get("supplementary_survey") and survey.status not in ("Completed", "Cancelled") else "Open with Presales"
    return {"label": label, "results": survey.results if survey and survey.status == "Completed" else None}


def create_costing_after_survey(survey):
    """Complete the no-presales handoff in the survey save transaction."""
    if survey.status != "Completed" or survey.presales_request or survey.get("supplementary_survey"):
        return
    frappe.db.sql("SELECT name FROM `tabOpportunity` WHERE name=%s FOR UPDATE", survey.opportunity)
    opportunity = frappe.get_doc("Opportunity", survey.opportunity)
    if opportunity.status in ("Lost", "Closed", "Converted") or cint(opportunity.get("custom_presales_required")):
        return
    if frappe.db.exists("Presales Request", {"opportunity": opportunity.name,
            "docstatus": ["<", 2], "status": ["!=", "Cancelled"]}):
        return
    if frappe.db.exists("Site Survey Request", {"opportunity": opportunity.name,
            "status": ["not in", ["Completed", "Cancelled"]]}):
        return
    from bsgroup.opportunity_intake import create_cost_sheet
    # Survey save already checks write access. This bounded downstream creation
    # must also work for survey staff who cannot create commercial documents.
    return create_cost_sheet(opportunity, ignore_permissions=True)


def request_details(opportunity):
    """Plain-text intake snapshot for the survey team, independent of Opportunity access."""
    teams = []
    if opportunity.get(FLAGS[0]):
        teams.append("ELV")
    if opportunity.get(FLAGS[1]):
        teams.append("Technical Team")
    rows = [("Opportunity", opportunity.name),
        ("Subject", opportunity.get("custom_subject") or opportunity.get("title")),
        ("Organization", opportunity.get("custom_organization_name")),
        ("Salesperson", opportunity.get("opportunity_owner")),
        ("Supply / Service", opportunity.get("custom_business_type")),
        ("Service Type", opportunity.get("custom_service_type")),
        ("Installation Type", opportunity.get("custom_installation_type")),
        ("Number of Cameras", opportunity.get("custom_camera_count")),
        ("Survey Team", ", ".join(teams)),
        ("Enquiry / Request", opportunity.get("custom_enquiry")),
        ("Service Details", opportunity.get("custom_service_details")),
        ("What exactly should the survey team do?", opportunity.get("custom_survey_instructions")),
        ("Site Survey Location", opportunity.get("custom_survey_location")),
        ("Contact Person", opportunity.get("custom_survey_contact_name") or opportunity.get("custom_contact_person_name")),
        ("Contact Phone", opportunity.get("custom_survey_contact_phone") or opportunity.get("contact_mobile")),
        ("Contact Email", opportunity.get("contact_email"))]
    return "\n\n".join(f"{label}:\n{value}" for label, value in rows if value)


def backfill_request_details():
    for row in frappe.get_all("Site Survey Request", fields=["name", "opportunity", "survey_request_details"]):
        if not row.survey_request_details and frappe.db.exists("Opportunity", row.opportunity):
            frappe.db.set_value("Site Survey Request", row.name, "survey_request_details",
                request_details(frappe.get_doc("Opportunity", row.opportunity)), update_modified=False)


def survey_selected(doc):
    return any(cint(doc.get(f)) for f in FLAGS)


def validate_opportunity(doc, method=None):
    if doc.is_new() or not frappe.db.exists("DocType", "Site Survey Request"):
        return
    linked = frappe.db.get_value("Site Survey Request", {"opportunity": doc.name}, ["name", "status"], as_dict=True)
    if linked:
        before = doc.get_doc_before_save()
        if before and any(doc.get(f) != before.get(f) for f in (*FLAGS, "custom_presales_required", "party_name", "opportunity_from", "company")):
            frappe.throw(_("A Site Survey Request already exists. Keep its survey options and customer unchanged; manage the request in Projects."))


def create_requests(doc, method=None):
    survey_needed = survey_selected(doc)
    presales_needed = cint(doc.get("custom_presales_required"))
    if not survey_needed and not presales_needed:
        return
    doc.check_permission("write")
    frappe.db.get_value("Opportunity", doc.name, "name", for_update=True)
    survey_name = frappe.db.get_value("Site Survey Request", {"opportunity": doc.name}, "name")
    if survey_needed and not survey_name:
        # Cover ordinary Opportunity saves as well as the dedicated button.
        # Initial intake is unaffected; late routing cannot be bypassed by API save.
        if frappe.db.exists("Deal Cost Sheet", {"opportunity": doc.name, "docstatus": ["<", 2]}) or frappe.db.exists(
                "Presales Request", {"opportunity": doc.name, "docstatus": ["<", 2], "status": ["!=", "Cancelled"]}):
            require_late_survey_manager()
            frappe.throw(_("Use Request Site Survey on the Opportunity to preserve the existing costing and presales work."))
        if cint(doc.get("custom_survey_step")) < 3:
            return
        survey = frappe.get_doc({"doctype": "Site Survey Request", "opportunity": doc.name,
            "status": "Requested", "requested_by": frappe.session.user,
            "request_date": nowdate(), "site_address": doc.get("custom_survey_location")})
        survey.flags.from_opportunity = True
        survey.insert(ignore_permissions=True)
        survey_name = survey.name
        doc.db_set("custom_site_survey_request", survey_name, update_modified=False)
    if not presales_needed:
        return
    presales_name = frappe.db.get_value("Presales Request", {
        "opportunity": doc.name, "docstatus": ["<", 2], "status": ["!=", "Cancelled"]})
    if presales_name:
        pre = frappe.get_doc("Presales Request", presales_name)
        if not pre.presales_owner and pre.docstatus == 0:
            recipient = default_presales_owner()
            if recipient:
                pre.db_set("presales_owner", recipient)
        if not survey_name or pre.custom_site_survey_request == survey_name:
            return
        if pre.docstatus or pre.status not in ("Draft", "Open", "Assigned", WAITING):
            frappe.throw(_("This Opportunity already has a Presales Request in progress. Arrange its survey from that request."))
    else:
        pre = frappe.get_doc({"doctype": "Presales Request", "opportunity": doc.name,
            "presales_owner": default_presales_owner(),
            "party_type": doc.opportunity_from, "party": doc.party_name,
            "company": doc.company, "subject": doc.get("custom_subject") or doc.title or doc.name,
            "estimated_value": doc.opportunity_amount, "requested_by": frappe.session.user,
            "request_date": nowdate(), "expected_close_date": doc.expected_closing,
            "is_new_customer": int(doc.opportunity_from == "Lead"), "status": "Draft"})
    if survey_name:
        survey = frappe.get_doc("Site Survey Request", survey_name)
        pre.custom_site_survey_request = survey.name
        pre.status = RECEIVED if survey.status == "Completed" else WAITING
        if survey.status == "Completed":
            pre.custom_survey_results = survey.results
    pre.save(ignore_permissions=True)
    if survey_name:
        frappe.db.set_value("Site Survey Request", survey_name, "presales_request", pre.name, update_modified=False)
    doc.db_set("status", "Presales Request", update_modified=False)


def default_presales_owner():
    """Route intake independently of its creator; retain explicit assignments."""
    user = frappe.conf.get("bsg_default_presales_owner") or "sanisha@bitssecureit.com"
    if frappe.db.get_value("User", user, "enabled") and set(frappe.get_roles(user)) & {"BS Scoped Presales", "Presales"}:
        return user
    return None


def validate_presales(doc, method=None):
    link = doc.get("custom_site_survey_request")
    survey = frappe.db.get_value("Site Survey Request", link, ["opportunity", "status", "supplementary_survey"], as_dict=True) if link else None
    if link and (not survey or survey.opportunity != doc.opportunity):
        frappe.throw(_("The Site Survey Request must belong to this Opportunity."))
    if doc.status in (WAITING, RECEIVED) and not survey:
        frappe.throw(_("A linked Site Survey Request is required for this status."))
    if doc.status == RECEIVED and survey.status != "Completed":
        frappe.throw(_("Complete the site survey and record its results first."))
    if survey and not survey.get("supplementary_survey") and survey.status != "Completed" and doc.status not in (WAITING, "Cancelled", "On Hold"):
        frappe.throw(_("This Presales Request is awaiting site survey results."))
    if doc.status != "Draft" and not (survey and doc.status in (WAITING, RECEIVED, "Cancelled", "On Hold")):
        missing = [doc.meta.get_label(f) for f in DEFERRED_FIELDS if not doc.get(f)]
        if missing:
            frappe.throw(_("Complete the Presales details before proceeding: {0}").format(", ".join(missing)))


def survey_query(user=None):
    if "BS Projects Manager" in frappe.get_roles(user or frappe.session.user):
        return ""
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
    if "BS Projects Manager" in frappe.get_roles(user or frappe.session.user):
        return None
    user = user or frappe.session.user
    if user == "Administrator" or set(frappe.get_roles(user)) & {"System Manager", "Projects Manager", "Presales", "Sales Manager"}:
        return None
    if user not in (doc.salesperson, doc.requested_by, doc.assigned_to):
        return False
    return None


def complete_survey_rework(sheet):
    records = [(sheet, "custom_deal_status", "Submitted to Sales")]
    if sheet.get("presales_request"):
        pre = frappe.get_doc("Presales Request", sheet.presales_request)
        if pre.opportunity == sheet.opportunity:
            records.append((pre, "status", "Submitted to Sales"))
            records.append((sheet, "custom_presales_status", "Submitted to Sales"))
    if sheet.get("custom_quotation"):
        quote = frappe.get_doc("Quotation", sheet.custom_quotation)
        if quote.get("custom_deal_cost_sheet") == sheet.name:
            records.append((quote, "custom_pipeline_stage", "Draft"))
    for doc, field, target in records:
        if doc.get(field) == REWORK_REQUIRED:
            frappe.db.set_value(doc.doctype, doc.name, field, target)
            frappe.clear_document_cache(doc.doctype, doc.name)
            frappe.get_doc(dict(doctype="Version", ref_doctype=doc.doctype, docname=doc.name,
                data=frappe.as_json(dict(changed=[[field, REWORK_REQUIRED, target]], added=[], removed=[], row_changed=[])))).insert(ignore_permissions=True)
            doc.add_comment("Info", _("Site survey rework completed through costing revision {0}.").format(sheet.name))
