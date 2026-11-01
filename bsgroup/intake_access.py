"""Bridge dedicated intake permissions into older BS Lead Intake releases."""
import frappe

ROLE = "BS Lead Intake Manager"


@frappe.whitelist(methods=["POST"])
def record_review(intake, human_outcome, note=None):
    from bs_lead_intake.intake import review
    # Extend its explicit role allowlist; its native document write check and
    # review/audit/routing behaviour still run unchanged.
    review.REVIEW_ROLES.add(ROLE)
    return review.record_review(intake, human_outcome, note)


@frappe.whitelist()
def pilot_report(from_date, to_date):
    if not {ROLE, "System Manager", "Sales Manager"} & set(frappe.get_roles()):
        frappe.throw("Not permitted", frappe.PermissionError)
    from bs_lead_intake.intake.metrics import compute
    return compute(from_date, to_date)
