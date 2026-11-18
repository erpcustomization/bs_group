"""Read-only Helpdesk schedule overlay for the Tech Ops dashboard."""
import json


def merge_scheduled_tickets(rows, tickets, assignments, today, only_user=None):
    """Use exact ticket/user/date identities; never create scheduler documents."""
    result, seen = [], set()
    for row in rows:
        row = dict(row)
        ticket = row.get("ticket_id")
        if row.get("category") == "HD Ticket" and ticket:
            key = (str(ticket), row.get("resource"), str(row.get("date"))[:10])
            if key in seen:
                continue
            seen.add(key)
        result.append(row)
    by_ticket = {}
    for assignment in assignments:
        if assignment.get("status") == "Open":
            by_ticket.setdefault(str(assignment.get("reference_name")), []).append(assignment)
    for ticket in tickets:
        if (str(ticket.get("status_category", "")).lower() in {"resolved", "closed"}
                or str(ticket.get("status", "")).lower() in {"resolved", "closed", "cancelled"}
                or ticket.get("is_merged")):
            continue
        ticket_id = str(ticket["name"])
        try:
            users = json.loads(ticket.get("_assign") or "[]")
        except (ValueError, TypeError):
            users = []
        if not isinstance(users, list):
            users = []
        schedule = []
        open_assignments = by_ticket.get(ticket_id, [])
        # Next Action Date is authoritative; assignment dates are a fallback.
        action_date = ticket.get("custom_next_action_date")
        if action_date:
            users = set(users) | {a.get("allocated_to") for a in open_assignments}
            schedule = [(user, action_date) for user in users]
        else:
            schedule = [(a.get("allocated_to"), a.get("date")) for a in open_assignments]
        for user, date in schedule:
            date = str(date or "")[:10]
            if not user or not date or date < str(today)[:10] or (only_user and user != only_user):
                continue
            key = (ticket_id, user, date)
            if key in seen:
                continue
            seen.add(key)
            result.append(dict(date=date, category="HD Ticket", ticket_id=ticket_id,
                category_name=ticket.get("subject") or ticket_id,
                task="Ticket #" + ticket_id + " — " + (ticket.get("subject") or "Helpdesk"),
                resource=user, status=ticket.get("status"), source="Helpdesk",
                activity_details=ticket.get("custom_next_action") or ticket.get("subject") or ""))
    return result


def with_helpdesk_schedule(rows):
    import frappe
    from frappe.utils import today
    from bsgroup.project_support_access import limited_scheduler

    if not frappe.has_permission("HD Ticket", "read"):
        return rows

    def accessible_list(doctype, fields, filters):
        result = []
        while True:
            page = frappe.get_list(doctype, fields=fields, filters=filters,
                start=len(result), page_length=500, order_by="name asc")
            result.extend(page)
            if len(page) < 500:
                return result

    assignments = []
    if frappe.has_permission("ToDo", "read"):
        assignments = accessible_list("ToDo",
            ["reference_name", "allocated_to", "date", "status"],
            {"reference_type": "HD Ticket", "status": "Open"})
    fields = ["name", "subject", "status", "status_category", "_assign", "is_merged",
        "custom_next_action_date", "custom_next_action"]
    tickets = accessible_list("HD Ticket", fields, {"status_category": ["!=", "Resolved"]})
    # Respect controller-level record restrictions as well as list permissions.
    tickets = [t for t in tickets if frappe.has_permission(
        "HD Ticket", "read", doc=frappe.get_doc("HD Ticket", t.name))]
    return merge_scheduled_tickets(rows, tickets, assignments, today(),
        frappe.session.user if limited_scheduler() else None)
