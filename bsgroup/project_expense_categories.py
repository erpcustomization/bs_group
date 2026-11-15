"""Project expense labels backed by the existing claim types and account mappings."""
import frappe
from frappe import _

CATEGORIES = {
    "Transportation": "Travel",
    "Petrol / fuel": "Travel",
    "Food": "Food",
    "Food for labourers": "Food",
    "Project material expense": "Others",
}


def install():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Expense Claim Detail": [dict(
        fieldname="custom_project_expense_category", label="Project Expense Category",
        fieldtype="Select", options="\n" + "\n".join(CATEGORIES), insert_after="expense_date",
        in_list_view=1, columns=2, depends_on="eval:parent.project") ]}, update=True)


def validate(doc, method=None):
    if not doc.get("project"):
        return
    old = doc.get_doc_before_save()
    if old and old.docstatus != 0:
        return
    prior = {r.name: r for r in (old.get("expenses") or [])} if old else {}
    for row in doc.get("expenses") or []:
        category = row.get("custom_project_expense_category")
        if not category and row.name in prior and not prior[row.name].get("custom_project_expense_category"):
            continue  # Keep historical rows and their existing accounting unchanged.
        if category not in CATEGORIES:
            frappe.throw(_("Choose a project expense category for row {0}.").format(row.idx))
        expected = CATEGORIES[category]
        if row.expense_type != expected:
            frappe.throw(_("Row {0}: choose the matching expense type {1} for {2}.").format(row.idx, expected, category))
