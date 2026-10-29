"""Sales-only qualification, kept on the Opportunity."""
import frappe
from frappe import _

FIELDS = (("decision_maker_known", "Decision Maker Known"),
          ("competition_known", "Competition Known"),
          ("budget_confirmed", "Budget Confirmed"))


def setup():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    from frappe.permissions import add_permission
    fields = [dict(fieldname="custom_sales_qualification", label="Opportunity Qualification",
        fieldtype="Section Break", insert_after="custom_enquiry", permlevel=9)]
    previous = "custom_sales_qualification"
    for name, label in FIELDS:
        fields.append(dict(fieldname="custom_" + name, label=label, fieldtype="Select",
            options="\nYes\nNo", insert_after=previous, permlevel=9))
        previous = "custom_" + name
    create_custom_fields({"Opportunity": fields}, update=True)
    for doctype in ("Opportunity", "Presales Request"):
        for role in ("Sales User", "Sales Manager", "System Manager"):
            if frappe.db.exists("Role", role):
                add_permission(doctype, role, permlevel=9, ptype="read")
                if doctype == "Opportunity":
                    rule = frappe.db.get_value("Custom DocPerm", {"parent":doctype,"role":role,"permlevel":9,"if_owner":0}, "name")
                    frappe.db.set_value("Custom DocPerm", rule, "write", 1)
    for name, label in FIELDS:
        make_property_setter("Presales Request", name, "reqd", 0, "Check")
        make_property_setter("Presales Request", name, "hidden", 1, "Check")
        make_property_setter("Presales Request", name, "permlevel", 9, "Int")
    # Preserve positive historical confirmations without treating unchecked as a confirmed No.
    for row in frappe.get_all("Presales Request", fields=["opportunity", *[name for name, _ in FIELDS]]):
        if not row.opportunity:
            continue
        for name, _ in FIELDS:
            target = "custom_" + name
            if row.get(name) and not frappe.db.get_value("Opportunity", row.opportunity, target):
                frappe.db.set_value("Opportunity", row.opportunity, target, "Yes", update_modified=False)
    frappe.clear_cache()
    return "Sales qualification configured"


def validate(doc):
    if not doc.meta.has_field("custom_decision_maker_known"):
        return
    if doc.flags.get("deferred_lead_intake"):
        return
    if frappe.session.user != "Administrator" and 9 not in doc.get_permlevel_access("write"):
        return
    missing = [label for name, label in FIELDS if doc.get("custom_" + name) not in ("Yes", "No")]
    if missing:
        frappe.throw(_("Complete Opportunity Qualification: {0}").format(", ".join(missing)))
