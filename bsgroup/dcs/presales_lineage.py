"""Maintain only a sheet's verified Presales active pointer across cancel/amend.

The cancelled DCS retains its source link. Version and governance rows preserve
the detached active pointer; no link-check bypass or database commit is used.
"""
import json

import frappe

from bsgroup.dcs.governance import make_request_key, record_governance_event

DETACH = "DCS_CANCEL_PRESALES_UNLINK"
RESTORE = "DCS_AMEND_PRESALES_LINKBACK"
IDENTITY = ("presales_request", "opportunity", "party_type", "party", "company")


def atomic_lifecycle(action):
    """Also roll back for in-process callers which catch a failed lifecycle."""
    savepoint = "dcs_lifecycle_" + frappe.generate_hash(length=12)
    frappe.db.savepoint(savepoint)
    try:
        return action()
    except frappe.QueryDeadlockError:
        frappe.db.rollback()
        raise
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


def _same_deal(sheet, request):
    if request.opportunity != sheet.opportunity:
        return False
    if request.party_type != sheet.party_type or request.party != sheet.party:
        return False
    if request.get("company") and sheet.company and request.company != sheet.company:
        return False
    return True


def _move_pointer(sheet, request, old, new, event_code):
    # Caller holds both rows. This projection update deliberately does not save
    # the whole request or run its business workflow.
    frappe.db.set_value("Presales Request", request.name,
                        "custom_deal_cost_sheet", new, update_modified=True)
    frappe.clear_document_cache("Presales Request", request.name)
    frappe.get_doc({
        "doctype": "Version", "ref_doctype": "Presales Request",
        "docname": request.name,
        "data": frappe.as_json({
            "added": [], "removed": [], "row_changed": [], "data_import": None,
            "updater_reference": None,
            "changed": [["custom_deal_cost_sheet", old, new]],
        }),
    }).insert(ignore_permissions=True)
    record_governance_event(
        sheet.name, event_code,
        action_label="Maintain the Presales active DCS pointer across cancel/amend",
        source_endpoint="deal_cost_sheet." + ("before_cancel" if event_code == DETACH else "on_submit"),
        reason=("Cancel the source DCS" if event_code == DETACH else
                "Amend cancelled DCS " + sheet.amended_from),
        revision_no=sheet.custom_dcs_revision_no or 0,
        revision_reference=sheet.custom_revision_reference or "",
        changes=[{"field": "custom_deal_cost_sheet", "old": old, "new": new,
                  "dt": "Presales Request", "dn": request.name}],
        request_key=make_request_key(event_code, {
            "dcs": sheet.name, "presales_request": request.name,
            "old": old, "new": new,
        }),
    )


def before_cancel(sheet):
    from bsgroup.api.dcs._common import CUSTOMER_SIDE, VENDOR_SIDE, get_user_roles, has_any
    if frappe.session.user != "Administrator" and not has_any(get_user_roles(), CUSTOMER_SIDE + VENDOR_SIDE):
        frappe.throw("Only an authorised commercial user may cancel a Deal Cost Sheet.", frappe.PermissionError)
    source = frappe.get_doc("Deal Cost Sheet", sheet.name, for_update=True)
    if source.custom_award_state == "Awarded" or source.custom_delivery_release_state in (
        "Released", "Released with MD Override",
    ):
        frappe.throw("Reverse the award and stop delivery release before cancelling this Deal Cost Sheet.")
    if any(str(source.get(f) or "") != str(sheet.get(f) or "") for f in IDENTITY):
        frappe.throw("Cancellation cannot change deal identity or source links.")
    if not source.presales_request:
        return
    request = frappe.get_doc("Presales Request", source.presales_request, for_update=True)
    if request.custom_deal_cost_sheet != source.name or request.docstatus == 2:
        return
    if not _same_deal(source, request):
        frappe.throw("The linked Presales Request has a different deal identity. Resolve it before cancelling; no link was changed.")
    _move_pointer(source, request, source.name, "", DETACH)


def _detachment_recorded(predecessor, request):
    for event in frappe.get_all("DCS Governance Event",
                               filters={"dcs": predecessor.name, "event_code": DETACH},
                               fields=["changes"]):
        changes = json.loads(event.changes or "[]")
        if any(c.get("target_doctype") == "Presales Request"
               and c.get("target_name") == request.name
               and c.get("fieldname") == "custom_deal_cost_sheet"
               and c.get("old_value") == predecessor.name
               and not c.get("new_value") for c in changes):
            return True
    return False


def amendment_request(sheet):
    """Lock and validate the candidate before any amendment baseline is written."""
    if not sheet.amended_from:
        return None
    predecessor = frappe.get_doc("Deal Cost Sheet", sheet.amended_from, for_update=True)
    if predecessor.presales_request and predecessor.presales_request != sheet.presales_request:
        original = frappe.get_doc("Presales Request", predecessor.presales_request, for_update=True)
        if original.custom_deal_cost_sheet == predecessor.name or _detachment_recorded(predecessor, original):
            frappe.throw("An amendment cannot drop or switch the Presales Request inherited from its predecessor.")
        return None
    if not sheet.presales_request:
        return None
    request = frappe.get_doc("Presales Request", sheet.presales_request, for_update=True)
    # Amendments without an active-pointer transition retain the established
    # behaviour, including records where this active pointer was never populated.
    if request.custom_deal_cost_sheet == sheet.name:
        return None
    recorded = _detachment_recorded(predecessor, request)
    if request.custom_deal_cost_sheet != predecessor.name and not recorded:
        return None
    if predecessor.docstatus != 2 or request.docstatus == 2:
        frappe.throw("Presales link restoration requires a cancelled predecessor and an active Presales Request.")
    if not _same_deal(sheet, request) or not _same_deal(predecessor, request):
        frappe.throw("The amendment and Presales Request must belong to the same deal; no link was changed.")
    if request.custom_deal_cost_sheet not in ("", None, predecessor.name):
        frappe.throw("The Presales Request now points to another DCS. Refresh and resolve it; it was not overwritten.")
    return request


def on_submit(sheet):
    request = amendment_request(sheet)
    if request:
        _move_pointer(sheet, request, request.custom_deal_cost_sheet or "", sheet.name, RESTORE)
