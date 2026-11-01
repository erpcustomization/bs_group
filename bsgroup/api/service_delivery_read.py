"""Permission-enforced, read-only evidence for service-delivery reviews."""

import frappe
from frappe.client import get as read_document


def _page_number(value, default=0, maximum=None):
    value = default if value is None else int(value)
    if value < 0 or (maximum is not None and value > maximum):
        frappe.throw("Invalid pagination value")
    return value


def _read(doctype, name):
    # Both list restrictions (including company scopes) and document/field permissions.
    if not frappe.get_list(doctype, filters={"name": name}, pluck="name", limit_page_length=1):
        frappe.throw("Record unavailable", frappe.PermissionError)
    return read_document(doctype, name)


def _section(doctype, filters, start, limit, required_fields=()):
    try:
        meta = frappe.get_meta(doctype)
        if not all(meta.has_field(f) for f in required_fields):
            return {"status": "unavailable", "reason": "Unsupported link schema"}
        names = frappe.get_list(doctype, filters=filters, pluck="name",
                                order_by="creation asc, name asc", limit_start=start,
                                limit_page_length=limit + 1)
        records = []
        denied = 0
        for name in names[:limit]:
            try:
                records.append(_read(doctype, name))
            except frappe.PermissionError:
                denied += 1
        more = len(names) > limit
        return {"status": "partial" if denied else "ok", "records": records,
                "scope": "records visible to the signed-in user", "denied": denied,
                "has_more": more, "next_start": start + limit if more else None}
    except frappe.PermissionError:
        return {"status": "unavailable", "reason": "ERP read permission denied"}
    except frappe.DoesNotExistError:
        return {"status": "unavailable", "reason": "DocType not installed"}


@frappe.whitelist(methods=["POST"])
def ticket_context(ticket, start=0, limit=50):
    """Read a ticket and linked evidence; never writes or overrides permissions.

    Each list uses the same start/limit. Repeat while ANY section has_more.
    An empty visible list is not proof that no off-system response exists.
    """
    if frappe.session.user == "Guest":
        frappe.throw("Sign in required", frappe.PermissionError)
    start = _page_number(start)
    limit = _page_number(limit, default=50, maximum=100)
    if not limit:
        frappe.throw("limit must be at least 1")
    ticket = str(ticket or "").strip()
    if not ticket:
        frappe.throw("ticket is required")
    document = _read("HD Ticket", ticket)
    reference = {"reference_doctype": "HD Ticket", "reference_name": ticket}
    sections = {
        "communications": _section("Communication", reference, start, limit, reference),
        "comments": _section("Comment", reference, start, limit, reference),
        "helpdesk_comments": _section("HD Ticket Comment", {"reference_ticket": ticket},
                                      start, limit, ["reference_ticket"]),
        "attachments": _section("File", {"attached_to_doctype": "HD Ticket", "attached_to_name": ticket},
                                start, limit, ["attached_to_doctype", "attached_to_name"]),
        "history": _section("Version", {"ref_doctype": "HD Ticket", "docname": ticket},
                            start, limit, ["ref_doctype", "docname"]),
    }
    # Communication Link also links messages into timelines. Query the parent
    # Communication through its child table so parent permission filters apply.
    try:
        link_meta = frappe.get_meta("Communication Link")
        parent_meta = frappe.get_meta("Communication")
        if (link_meta.has_field("link_doctype") and link_meta.has_field("link_name")
                and any(f.fieldtype == "Table" and f.options == "Communication Link" for f in parent_meta.fields)):
            sections["linked_communications"] = _section("Communication", [
                ["Communication Link", "link_doctype", "=", "HD Ticket"],
                ["Communication Link", "link_name", "=", ticket],
            ], start, limit)
        else:
            sections["linked_communications"] = {"status": "unavailable", "reason": "Unsupported link schema"}
    except (frappe.DoesNotExistError, frappe.PermissionError):
        sections["linked_communications"] = {"status": "unavailable", "reason": "Link metadata unavailable"}

    sla = {"status": "not_configured"}
    if document.get("sla"):
        try:
            sla = {"status": "ok", "record": _read("HD Service Level Agreement", document["sla"])}
            holiday = sla["record"].get("holiday_list")
            if holiday:
                try:
                    sla["holiday_calendar"] = {"status": "ok", "record": _read("Holiday List", holiday)}
                except (frappe.PermissionError, frappe.DoesNotExistError):
                    sla["holiday_calendar"] = {"status": "unavailable"}
        except (frappe.PermissionError, frappe.DoesNotExistError):
            sla = {"status": "unavailable", "reason": "Linked SLA is not readable"}
    sections["sla"] = sla
    return {"ticket": document, "sections": sections, "start": start, "limit": limit,
            "scope": "Signed-in user's ERP permissions; ticket-linked evidence only",
            "notes": ["Deduplicate communications by name across both communication lists.",
                      "Attachment records are references, not inspected file contents.",
                      "Closed status and silence do not prove customer acceptance.",
                      "SLA is the current configuration; historical rule changes require history review."]}
