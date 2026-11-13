"""Request presales rework without cancelling or duplicating commercial records."""
import frappe

from bsgroup.dcs.presales_lineage import atomic_lifecycle, _same_deal
from bsgroup.dcs.governance import make_request_key, record_governance_event

REVISION = "To be revised"
REWORK = "Rework"


def install():
    # Existing site-survey Property Setters override the standard JSON options.
    # Preserve every local option and append only the new business states.
    from bsgroup.oman_quotation_flow import enabled
    if not enabled():
        return
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    for doctype, field, status in (("Presales Request", "status", REWORK),
                                  ("Deal Cost Sheet", "custom_deal_status", REVISION)):
        options = (frappe.get_meta(doctype).get_field(field).options or "").splitlines()
        if status not in options:
            make_property_setter(doctype, field, "options", "\n".join(options + [status]), "Text")


def linked_presales(sheet):
    if not sheet.presales_request:
        frappe.throw("This costing sheet has no linked Presales Request. Choose No to revise it in Sales, or have the source presales link reviewed.")
    request = frappe.get_doc("Presales Request", sheet.presales_request, for_update=True)
    if (request.docstatus == 2 or request.status in ("Won", "Lost", "Cancelled")
            or request.custom_deal_cost_sheet != sheet.name or not _same_deal(sheet, request)):
        frappe.throw("The linked Presales Request is closed or does not link back to this costing sheet and deal. No records were changed.")
    return request


def record(sheet, request, event, values):
    changes = []
    for doc, updates in values:
        changed = {key: value for key, value in updates.items() if doc.get(key) != value}
        if not changed:
            continue
        changes.extend(dict(dt=doc.doctype, dn=doc.name, field=key, old=doc.get(key), new=value)
                       for key, value in changed.items())
        frappe.db.set_value(doc.doctype, doc.name, changed, update_modified=True)
        frappe.clear_document_cache(doc.doctype, doc.name)
        frappe.get_doc(dict(doctype="Version", ref_doctype=doc.doctype, docname=doc.name,
            data=frappe.as_json(dict(changed=[[k, doc.get(k), v] for k, v in changed.items()],
                                    added=[], removed=[], row_changed=[])))).insert(ignore_permissions=True)
    if changes:
        record_governance_event(sheet.name, event,
            action_label="Quotation revision presales handoff",
            source_endpoint="quotation_revision", reason="Linked quotation " + sheet.custom_quotation,
            changes=changes, request_key=make_request_key(event, dict(
                dcs=sheet.name, request=request.name, modified=str(sheet.modified), changes=changes)))


@frappe.whitelist(methods=["POST"])
def begin(quotation, presales, expected_modified):
    return atomic_lifecycle(lambda: _begin(quotation, presales, expected_modified))


def _begin(quotation, presales, expected_modified):
    from bsgroup import oman_quotation_flow as flow
    from bsgroup.api.dcs._common import CUSTOMER_SIDE
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_deal_identity
    if presales not in ("Yes", "No"):
        frappe.throw("Choose Yes or No for presales support.")
    if frappe.session.user != "Administrator" and not set(frappe.get_roles()).intersection(CUSTOMER_SIDE):
        frappe.throw("Sales access is required to request a quotation revision.", frappe.PermissionError)
    # Follow the BOQ writer's lock order: DCS, then quotation.
    initial = flow._quotation(quotation, write=True)
    sheet = frappe.get_doc("Deal Cost Sheet", initial.custom_deal_cost_sheet, for_update=True)
    sheet.check_permission("write")
    q = flow._quotation(quotation, write=True, lock=True)
    flow.check_editable(q)
    if str(q.modified) != str(expected_modified):
        frappe.throw("The quotation changed. Reload it before requesting a revision.")
    if (sheet.docstatus != 1 or sheet.custom_record_authority == "Superseded"
            or q.custom_deal_cost_sheet != sheet.name or sheet.custom_quotation != q.name
            or quotation_deal_identity(sheet, q)):
        frappe.throw("Revision requires this quotation's own active submitted costing sheet. Review the links; nothing was changed.")
    if sheet.custom_award_state == "Awarded" or sheet.custom_delivery_release_state in ("Released", "Released with MD Override"):
        frappe.throw("An awarded or released costing sheet cannot be revised.")
    flow.guard_dcs_revision(sheet)
    result = dict(dcs=sheet.name, quotation=q.name, presales=presales)
    if presales == "No":
        if sheet.custom_deal_status == REVISION:
            frappe.throw("This revision is already with Presales. Complete the existing rework before starting another revision.")
        return result
    request = linked_presales(sheet)
    request.check_permission("read")
    record(sheet, request, "QUOTATION_PRESALES_REWORK_REQUESTED", [
        (sheet, dict(custom_deal_status=REVISION, custom_presales_status=REWORK)),
        (request, dict(status=REWORK)),
    ])
    return dict(result, presales_request=request.name)


def finish(sheet):
    """Called only after the governed BOQ and same quotation save succeeds."""
    if sheet.custom_deal_status != REVISION:
        return
    request = linked_presales(sheet)
    record(sheet, request, "QUOTATION_PRESALES_REWORK_COMPLETED", [
        (sheet, dict(custom_deal_status="Submitted to Sales", custom_presales_status="Submitted to Sales")),
        (request, dict(status="Submitted to Sales")),
    ])
