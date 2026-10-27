"""List-only filtering on the same derived status that the user sees."""
import re
from contextlib import contextmanager

import frappe
from frappe.desk import reportview
from bsgroup.opportunity_progress import resolve_many


def matches(label, operator, value):
    def equal(value):
        # Keep saved legacy filters valid; category filters include every delay age.
        if value == "Pending from Site Survey Team":
            value = "Delayed by Site Survey Team"
        return label == value or re.sub(r"^\d+ days - ", "", label) == value
    operator = operator.lower()
    if operator in ("in", "not in"):
        values = value if isinstance(value, list) else [v.strip() for v in str(value).split(",")]
        result = any(equal(v) for v in values)
        return not result if operator == "not in" else result
    if operator in ("like", "not like"):
        pattern = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in str(value))
        result = bool(re.fullmatch(pattern, label, re.IGNORECASE))
        return not result if operator == "not like" else result
    if operator == "=":
        return equal(value)
    if operator == "!=":
        return not equal(value)
    if operator == "is":
        return bool(label) if value == "set" else not label
    frappe.throw("Use Equals, Not Equals, In, Not In, Like, Not Like or Is for Status.")


def split_filters(filters):
    ordinary, progress = [], []
    for item in filters or []:
        item = list(item)
        if len(item) == 3:
            item.insert(0, "Opportunity")
        if len(item) >= 4 and item[0] == "Opportunity" and item[1] == "status":
            progress.append(item)
        else:
            ordinary.append(item)
    return ordinary, progress


@contextmanager
def translated_filters():
    # Let the standard endpoint validate fields/operators and reject unsafe arguments.
    args = reportview.get_form_params()
    if args.doctype != "Opportunity":
        frappe.throw("This list endpoint is only for Opportunity.")
    ordinary, progress = split_filters(args.filters)
    if not progress:
        yield
        return
    matched = []
    start = 0
    while True:
        # Apply normal filters and permissions BEFORE deriving statuses, and scan
        # every candidate before pagination so page 2 and counts remain correct.
        rows = frappe.get_list("Opportunity", filters=ordinary, or_filters=args.get("or_filters"),
            fields=["name", "status"], order_by="name asc", limit_start=start,
            limit_page_length=500, distinct=True)
        resolved = resolve_many(rows)
        matched.extend(row.name for row in rows if all(
            matches(resolved[row.name]["label"], f[2], f[3]) for f in progress))
        if len(rows) < 500:
            break
        start += 500
    original = frappe.local.form_dict.get("filters")
    frappe.local.form_dict.filters = ordinary + [["Opportunity", "name", "in", matched or [""]]]
    try:
        yield
    finally:
        frappe.local.form_dict.filters = original


@frappe.whitelist()
def get():
    with translated_filters():
        return reportview.get()


@frappe.whitelist()
def get_count():
    with translated_filters():
        return reportview.get_count()
