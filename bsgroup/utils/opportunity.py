import frappe
from frappe.utils import getdate, nowdate, now


def set_opportunity_owner(doc, method=None):
    if not doc.opportunity_owner:
        doc.opportunity_owner = frappe.session.user


def set_stage_history(doc, method=None):
    update_stage_age(doc)

    if doc.has_value_changed("sales_stage"):
        now_time = now()

        if doc.custom_stage_history:
            last_history = doc.custom_stage_history[-1]
            if not last_history.to_date:
                last_history.to_date = now_time

        doc.append("custom_stage_history", {
            "stage": doc.sales_stage,
            "from_date": now_time,
            "changed_by": frappe.session.user,
            "remarks": doc.custom_last_sales_update or "Stage Updated"
        })

        doc.custom_stage_last_changed_on = now_time


def update_stage_age(doc):
    if doc.custom_stage_last_changed_on:
        today = getdate(nowdate())
        stage_date = getdate(doc.custom_stage_last_changed_on)

        doc.custom_stage_age_days = (today - stage_date).days


def update_overdue_followup_for_all():
    opportunities = frappe.get_all(
        "Opportunity",
        fields=["name", "custom_next_action_date"]
    )

    today = getdate(nowdate())

    for opp in opportunities:
        if opp.custom_next_action_date:
            next_action_date = getdate(opp.custom_next_action_date)

            overdue = 1 if next_action_date < today else 0

            frappe.db.set_value(
                "Opportunity",
                opp.name,
                "custom_overdue_followup",
                overdue
            )


def set_stage_updates(doc, method=None):
    update_changed = doc.has_value_changed("custom_last_sales_update")
    action_changed = (
        doc.has_value_changed("custom_next_action") or
        doc.has_value_changed("custom_next_action_date")
    )
    date_changed = doc.has_value_changed("custom_last_update_date")

    if not (update_changed or action_changed or date_changed):
        return

    if not doc.custom_last_sales_update and not doc.custom_next_action:
        return

    doc.append("custom_sales_updates", {
        "update_note":      doc.custom_last_sales_update or "",
        "update_date":      doc.custom_last_update_date or nowdate(),
        "updated_by":       frappe.session.user,
        "stage_snapshot":   doc.sales_stage,
        "next_action":      doc.custom_next_action or "",
        "next_action_date": doc.custom_next_action_date or None,
    })

def set_last_updates(doc, method=None):
    if doc.is_new():
        return

    if doc.has_value_changed("custom_next_action") or doc.has_value_changed("custom_next_action_date"):
        old_doc = frappe.get_doc(doc.doctype, doc.name)

        doc.custom_last_sales_update = old_doc.custom_next_action
        doc.custom_last_update_date = old_doc.custom_next_action_date