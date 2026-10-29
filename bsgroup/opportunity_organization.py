"""Keep the list's organization label consistent with the source Lead."""
import frappe


def sync(doc, method=None):
    if doc.get("opportunity_from") == "Lead" and doc.get("party_name"):
        doc.custom_organization_name = frappe.db.get_value("Lead", doc.party_name, "company_name") or ""


@frappe.whitelist()
def backfill():
    frappe.only_for("System Manager")
    updated = []
    for row in frappe.get_all("Opportunity", filters={"opportunity_from": "Lead"},
                              fields=["name", "party_name", "custom_organization_name"]):
        if (row.custom_organization_name or "").strip() or not row.party_name:
            continue
        organization = frappe.db.get_value("Lead", row.party_name, "company_name")
        if organization and organization.strip():
            frappe.db.set_value("Opportunity", row.name, "custom_organization_name", organization, update_modified=False)
            updated.append(row.name)
    return {"updated": updated}
