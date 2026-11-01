"""Planned turnaround chosen by Presales before submission."""
import frappe

OPTIONS = ["1 hour"] + [f"{n} hours" for n in range(2, 9)] + ["1 day"] + [f"{n} days" for n in range(2, 6)] + ["1 week", "2 weeks"]


def validate(doc, method=None):
    value = doc.get("custom_completion_time")
    if value and value not in OPTIONS:
        frappe.throw("Choose a valid Time Required to Complete.")
    if method == "before_submit" and not value:
        frappe.throw("Select Time Required to Complete in Details before submitting Presales.")


@frappe.whitelist(methods=["POST"])
def setup():
    frappe.only_for("System Manager")
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Presales Request": [
        dict(fieldname="custom_completion_time_section", fieldtype="Section Break", label="Completion Time", insert_after="assumptions"),
        dict(fieldname="custom_completion_time", fieldtype="Select", label="Time Required to Complete",
             insert_after="custom_completion_time_section", options="\n" + "\n".join(OPTIONS),
             mandatory_depends_on="eval:doc.docstatus === 1", no_copy=1,
             description="Select the planned time needed to complete this Presales Request.")
    ]}, update=True)
    frappe.clear_cache(doctype="Presales Request")
    return {"options": OPTIONS}
