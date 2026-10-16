"""Trace margin movements to immutable revisions, rather than mutable BOQ totals."""
from frappe.utils import flt
from bsgroup.dcs.currency import money_round

def margin_bridge(sheet, revisions):
    currency = sheet.currency
    def position(cost, selling):
        cost, selling = flt(cost), flt(selling)
        return {"cost": cost, "selling": selling, "gp": money_round(selling-cost,currency),
                "margin_percent": flt((selling-cost)/selling*100,3) if selling else 0}
    first = revisions[0] if revisions else None
    original = position(first.get("prev_total_cost"), first.get("prev_total_selling")) if first else position(sheet.total_cost, sheet.total_selling)
    current = position(sheet.custom_working_total_cost, sheet.custom_working_total_selling) if sheet.custom_dcs_revision_no else position(sheet.total_cost,sheet.total_selling)
    impacts = {"customer": 0, "vendor": 0, "technical": 0, "internal": 0}
    for revision in revisions:
        key = (revision.get("source") or "Internal").lower()
        impacts[key] = money_round(impacts.get(key, 0) + flt(revision.get("gp_movement")),currency)
    movement = money_round(current["gp"]-original["gp"],currency)
    return {"original": original, "current": current, "gp_movement": movement,
            "margin_point_movement": flt(current["margin_percent"]-original["margin_percent"],3),
            "gp_impacts": impacts, "unreconciled_gp": money_round(movement-sum(impacts.values()),currency),
            "basis": "Original position from the first immutable revision; movements include every revision, including rejected positions.",
            "approval_required": sheet.custom_approval_required, "approval_state":sheet.custom_approval_state,
            "awarded": position(sheet.custom_frozen_total_cost,sheet.custom_frozen_total_selling) if sheet.custom_baseline_frozen else None}
