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

    result = {"day": start, "today": frappe.utils.today(), "details": {}}
    people = {}

    def person(user):
        user = user or "Unassigned"
        if user not in people:
            people[user] = dict(user=user, name=frappe.get_cached_value("User", user, "full_name") or user,
                                leads=0, opportunities=0, quoted=[], won=[], details={"leads":[],"opportunities":[],"quoted":[],"won":[]})
        return people[user]
    for key, doctype in (("leads", "Lead"), ("opportunities", "Opportunity"),
                         ("presales", "Presales Request")):
        owner_field = {"Lead": "lead_owner", "Opportunity": "opportunity_owner"}.get(doctype)
        rows = records(doctype, [["creation", ">=", start], ["creation", "<", end],
                                 ["docstatus", "!=", 2]],
                       ["name", "owner", owner_field] if owner_field else ["name"])
        result[key] = len(rows) if rows is not None else None
        result["details"][key] = [row.name for row in rows or []]
        if owner_field:
            for row in rows or []:
                person(row.get(owner_field) or row.owner)[key] += 1
                person(row.get(owner_field) or row.owner)["details"][key].append(row.name)
    sheets = records("Deal Cost Sheet", [["docstatus", "=", 0]],
                     ["name", "custom_deal_status", "custom_record_authority"])
    result["dcs"] = sum(
        row.custom_deal_status not in {"Won", "Lost", "Cancelled"}
        and row.custom_record_authority != "Superseded" for row in sheets
    ) if sheets is not None else None
    result["details"]["dcs"] = [row.name for row in sheets or []
        if row.custom_deal_status not in {"Won", "Lost", "Cancelled"}
        and row.custom_record_authority != "Superseded"]
    # Quoted cohort and win-event cohort are deliberately separate. An older
    # quotation won on the selected day belongs in Won for that day.
    fields = ["name", "currency", "grand_total", "owner", "opportunity"]
    for key, filters in (
        ("quoted", [["transaction_date", "=", start]]),
        ("won", [["custom_won_date", "=", start], ["custom_pipeline_stage", "=", "Won"]]),
    ):
        rows = records("Quotation", [["docstatus", "=", 1]] + filters, fields)
        result[key] = quotation_total(rows) if rows is not None else None
        result["details"][key] = [f"{row.name} · {row.currency} {float(row.grand_total or 0):,.2f}" for row in rows or []]
        names = list({row.opportunity for row in rows or [] if row.opportunity})
        opportunities = records("Opportunity", [["name", "in", names]],
                                ["name", "opportunity_owner", "owner"]) if names else []
        owners = {row.name: row.opportunity_owner or row.owner for row in opportunities or []}
        for row in rows or []:
            # Do not attribute a presales-created quote to the preparer when
            # the linked Opportunity supplies the actual sales owner.
            person(owners.get(row.opportunity) if row.opportunity else row.owner)[key].append(row)
            person(owners.get(row.opportunity) if row.opportunity else row.owner)["details"][key].append(
                f"{row.name} · {row.currency} {float(row.grand_total or 0):,.2f}")
    result["people"] = []
    for row in sorted(people.values(), key=lambda row: row["name"].lower()):
        row["quoted"] = quotation_total(row["quoted"])
        row["won"] = quotation_total(row["won"])
        result["people"].append(row)
    from bsgroup.management_attendance import overview
    result["attendance"] = overview(selected)
    return result


@frappe.whitelist()
def executive(day=None):
    """Executive presentation data; no additional access or workflow writes."""
    result = daily(day)  # Enforces the same user and date boundary.
    selected = date.fromisoformat(result['day'])
    first = selected - timedelta(days=6)
    end = selected + timedelta(days=1)
    series = {str(first + timedelta(days=i)):dict(day=str(first + timedelta(days=i)),
        leads=0, opportunities=0, presales=0, quoted={}, won={}) for i in range(7)}
    available = {}
    for key, dt, date_field, extra in (
        ('leads','Lead','creation',[]),
        ('opportunities','Opportunity','creation',[]),
        ('presales','Presales Request','creation',[]),
        ('quoted','Quotation','transaction_date',[['docstatus','=',1]]),
        ('won','Quotation','custom_won_date',[['docstatus','=',1],['custom_pipeline_stage','=','Won']]),
    ):
        available[key] = bool(frappe.has_permission(dt,'read'))
        if not available[key]:
            continue
        money = key in ('quoted','won')
        fields = ['name',date_field] + (['currency','grand_total'] if money else [])
        rows = frappe.get_list(dt, fields=fields, filters=[
            [date_field,'>=',str(first)],[date_field,'<',str(end)],['docstatus','!=',2]]+extra,
            limit_page_length=0)
        for row in rows:
            stamp = str(frappe.utils.getdate(row.get(date_field)))
            if stamp not in series:
                continue
            if money:
                values = series[stamp][key]
                values[row.currency] = values.get(row.currency,0) + float(row.grand_total or 0)
            else:
                series[stamp][key] += 1
    result['series'] = list(series.values())
    result['series_available'] = available
    result['dcs_age'] = []
    if result['dcs'] is not None:
        names = result['details']['dcs']
        rows = frappe.get_list('Deal Cost Sheet',filters={'name':['in',names]},
            fields=['name','creation','deal_owner'],limit_page_length=0) if names else []
        buckets = [('0–7 days',0,7),('8–14 days',8,14),('15–30 days',15,30),('Over 30 days',31,None)]
        today = date.fromisoformat(result['today'])
        for label,low,high in buckets:
            matches = [r.name for r in rows if (age := (today-frappe.utils.getdate(r.creation)).days)>=low
                       and (high is None or age<=high)]
            result['dcs_age'].append(dict(label=label,count=len(matches),details=matches))
    result['currencies'] = sorted({currency for point in result['series']
                                  for key in ('quoted','won') for currency in point[key]})
    if not result['currencies']:
        companies = frappe.get_list('Company',fields=['default_currency'],limit_page_length=0)
        result['currencies'] = sorted({c.default_currency for c in companies if c.default_currency})
    return result
