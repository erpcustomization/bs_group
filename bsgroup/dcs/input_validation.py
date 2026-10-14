"""Commercial input checks shared by drafts, revisions and decision services."""
import math
import frappe

def non_negative(value, label):
    try:
        number = float(value or 0)
    except (ValueError, TypeError, OverflowError):
        frappe.throw(f"{label} must be a finite, non-negative number.")
    if not math.isfinite(number) or number < 0:
        frappe.throw(f"{label} must be a finite, non-negative number.")
    return number

def validate_inputs(doc):
    for table, label, fields in (
        ("items", "Item", ("qty", "cost_rate", "selling_rate")),
        ("resources", "Resource", ("no_of_persons", "no_of_days", "hours", "cost_rate")),
        ("addtional_charges", "Additional charge", ("amount", "selling_amount")),
    ):
        for index, row in enumerate(doc.get(table) or [], 1):
            for field in fields:
                non_negative(row.get(field), f"{label} row {index}: {field.replace('_', ' ')}")

def validate_position(doc):
    validate_inputs(doc)
    for field in ("total_cost", "total_selling"):
        non_negative(doc.get(field), field.replace("_", " "))
    if doc.get("custom_dcs_revision_no"):
        for field in ("custom_working_total_cost", "custom_working_total_selling"):
            non_negative(doc.get(field), field.replace("custom_working_", "Current ").replace("_", " "))

def position_is_valid(doc):
    # Read projections must remain available to inspect a legacy invalid record.
    values=[]
    for table, fields in (
        ("items", ("qty","cost_rate","selling_rate")),
        ("resources", ("no_of_persons","no_of_days","hours","cost_rate")),
        ("addtional_charges", ("amount","selling_amount")),
    ):
        for row in doc.get(table) or []:
            values.extend(row.get(field) for field in fields)
    values.extend(doc.get(field) for field in ("total_cost","total_selling"))
    if doc.get("custom_dcs_revision_no"):
        values.extend(doc.get(field) for field in ("custom_working_total_cost","custom_working_total_selling"))
    try:
        return all(math.isfinite(float(value or 0)) and float(value or 0)>=0 for value in values)
    except (ValueError,TypeError,OverflowError):
        return False
