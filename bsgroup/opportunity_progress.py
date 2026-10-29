"""Read-only progress labels derived from linked work, without changing ERP workflows."""
import frappe
from frappe.utils import get_datetime, now_datetime


def timed(label, delayed, started, now):
    late = bool(started and (now - get_datetime(started)).total_seconds() > 86400)
    return dict(label=delayed if late else label, color="red" if late else "blue", started=started)


def resolve(opportunity, surveys, presales, sheets, now=None):
    now = now or now_datetime()
    native = opportunity.get("status")
    if native in ("Lost", "Closed", "Converted", "Quotation"):
        return dict(label=native, color="red" if native == "Lost" else "green")
    active_surveys = [s for s in surveys if s.status not in ("Completed", "Cancelled")]
    if active_surveys:
        return timed("Open with Site Survey Team", "Pending from Site Survey Team", active_surveys[0].creation, now)
    live_sheets = [s for s in sheets if s.docstatus < 2 and s.get("custom_record_authority") != "Superseded"]
    if live_sheets:
        sheet = live_sheets[0]
        if sheet.docstatus == 0 and sheet.get("custom_deal_status") in (None, "", "Draft", "Costing in Progress"):
            return timed("Deal Cost Sheet in Progress", "Delayed Deal Cost Sheet", sheet.creation, now)
        return dict(label=sheet.get("custom_deal_status") or "Deal Cost Sheet Submitted", color="green")
    live_presales = [p for p in presales if p.docstatus < 2 and p.status not in ("Cancelled", "Completed", "Won", "Lost", "Ready for Quotation", "Submitted to Sales")]
    if live_presales:
        request = live_presales[0]
        survey = next((s for s in surveys if s.name == request.get("custom_site_survey_request")), None)
        if survey and survey.status == "Cancelled":
            return dict(label="Site Survey Cancelled", color="orange")
        started = request.creation
        if survey and survey.status == "Completed" and survey.completed_on:
            started = max(get_datetime(request.creation), get_datetime(survey.completed_on))
        return timed("Open with Presales", "Delayed by Presales", started, now)
    finished = next((p for p in presales if p.docstatus < 2 and p.status not in ("Cancelled", "Awaiting Site Survey Results")), None)
    if finished:
        return dict(label=finished.status, color="green")
    return dict(label="Open" if native in (None, "", "Open", "Presales Request") else native, color="purple")


@frappe.whitelist()
def statuses(names):
    names = frappe.parse_json(names)
    if not isinstance(names, list) or len(names) > 500:
        frappe.throw("Request at most 500 Opportunity statuses.")
    # Permission-filter the requested opportunities before reading any related work.
    opportunities = frappe.get_list("Opportunity", filters={"name": ["in", names]}, fields=["name", "status"], limit_page_length=500)
    allowed = [o.name for o in opportunities]
    if not allowed:
        return {}
    def related(doctype, fields):
        rows = frappe.get_all(doctype, filters={"opportunity": ["in", allowed]}, fields=["name", "opportunity", "creation", *fields], order_by="creation desc")
        grouped = {}
        for row in rows:
            grouped.setdefault(row.opportunity, []).append(row)
        return grouped
    surveys = related("Site Survey Request", ["status", "completed_on"])
    presales = related("Presales Request", ["status", "docstatus", "custom_site_survey_request"])
    sheets = related("Deal Cost Sheet", ["docstatus", "custom_deal_status", "custom_record_authority"])
    now = now_datetime()
    return {o.name: resolve(o, surveys.get(o.name, []), presales.get(o.name, []), sheets.get(o.name, []), now) for o in opportunities}
