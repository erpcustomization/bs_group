"""Keep the list's organization label consistent with the linked party."""
import frappe


def organization_name(party_type, party):
    field = {"Lead": "company_name", "Customer": "customer_name"}.get(party_type)
    if field and party:
        return frappe.db.get_value(party_type, party, field) or ""
    return ""


def sync(doc, method=None):
    if doc.get("opportunity_from") in ("Lead", "Customer") and doc.get("party_name"):
        doc.custom_organization_name = organization_name(doc.opportunity_from, doc.party_name)


@frappe.whitelist()
def backfill():
    frappe.only_for("System Manager")
    updated = []
    for row in frappe.get_all("Opportunity", filters={"opportunity_from": ["in", ["Lead", "Customer"]]},
                              fields=["name", "opportunity_from", "party_name", "custom_organization_name"]):
        if (row.custom_organization_name or "").strip() or not row.party_name:
            continue
        organization = organization_name(row.opportunity_from, row.party_name)
        if organization and organization.strip():
            frappe.db.set_value("Opportunity", row.name, "custom_organization_name", organization, update_modified=False)
            updated.append(row.name)
    return {"updated": updated}
