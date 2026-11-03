"""Mohan's daily team overview, using his existing record permissions."""
from datetime import date, timedelta

import frappe


def quotation_total(rows):
    amounts = {}
    for row in rows:
        currency = row.currency
        amounts[currency] = amounts.get(currency, 0) + float(row.grand_total or 0)
    return {"count": len(rows), "amounts": amounts}


@frappe.whitelist()
def daily(day=None):
    if frappe.session.user not in {"mohan@bitssecureit.com", "Administrator"}:
        frappe.throw("This team overview is available to Mohan only.", frappe.PermissionError)
    try:
        selected = date.fromisoformat(day or frappe.utils.today())
    except (TypeError, ValueError):
        frappe.throw("Choose a valid date (YYYY-MM-DD).")
    if selected > date.fromisoformat(frappe.utils.today()):
        frappe.throw("Choose today or an earlier date.")
    start, end = str(selected), str(selected + timedelta(days=1))

    def records(doctype, filters, fields=None):
        if not frappe.has_permission(doctype, "read"):
            return None
        return frappe.get_list(doctype, fields=fields or ["name"],
                               filters=filters, limit_page_length=0)

    result = {"day": start, "today": frappe.utils.today()}
    people = {}

    def person(user):
        user = user or "Unassigned"
        if user not in people:
            people[user] = dict(user=user, name=frappe.get_cached_value("User", user, "full_name") or user,
                                leads=0, opportunities=0, quoted=[], won=[])
        return people[user]
    for key, doctype in (("leads", "Lead"), ("opportunities", "Opportunity"),
                         ("presales", "Presales Request")):
        owner_field = {"Lead": "lead_owner", "Opportunity": "opportunity_owner"}.get(doctype)
        rows = records(doctype, [["creation", ">=", start], ["creation", "<", end],
                                 ["docstatus", "!=", 2]],
                       ["name", "owner", owner_field] if owner_field else ["name"])
        result[key] = len(rows) if rows is not None else None
        if owner_field:
            for row in rows or []:
                person(row.get(owner_field) or row.owner)[key] += 1
    sheets = records("Deal Cost Sheet", [["docstatus", "=", 0]],
                     ["name", "custom_deal_status", "custom_record_authority"])
    result["dcs"] = sum(
        row.custom_deal_status not in {"Won", "Lost", "Cancelled"}
        and row.custom_record_authority != "Superseded" for row in sheets
    ) if sheets is not None else None
    # Quoted cohort and win-event cohort are deliberately separate. An older
    # quotation won on the selected day belongs in Won for that day.
    fields = ["name", "currency", "grand_total", "owner", "opportunity"]
    for key, filters in (
        ("quoted", [["transaction_date", "=", start]]),
        ("won", [["custom_won_date", "=", start], ["custom_pipeline_stage", "=", "Won"]]),
    ):
        rows = records("Quotation", [["docstatus", "=", 1]] + filters, fields)
        result[key] = quotation_total(rows) if rows is not None else None
        names = list({row.opportunity for row in rows or [] if row.opportunity})
        opportunities = records("Opportunity", [["name", "in", names]],
                                ["name", "opportunity_owner", "owner"]) if names else []
        owners = {row.name: row.opportunity_owner or row.owner for row in opportunities or []}
        for row in rows or []:
            # Do not attribute a presales-created quote to the preparer when
            # the linked Opportunity supplies the actual sales owner.
            person(owners.get(row.opportunity) if row.opportunity else row.owner)[key].append(row)
    result["people"] = []
    for row in sorted(people.values(), key=lambda row: row["name"].lower()):
        row["quoted"] = quotation_total(row["quoted"])
        row["won"] = quotation_total(row["won"])
        result["people"].append(row)
    from bsgroup.management_attendance import overview
    result["attendance"] = overview(selected)
    return result
