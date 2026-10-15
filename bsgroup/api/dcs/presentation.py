"""Read-only company identity for the DCS header."""
import frappe


@frappe.whitelist()
def company_context(company=None):
    if not frappe.has_permission("Deal Cost Sheet", "read"):
        frappe.throw("Not permitted to read Deal Cost Sheets.", frappe.PermissionError)
    companies = frappe.get_all("Company", filters={"is_group": 0}, pluck="name", limit_page_length=2)
    selected = company or (companies[0] if len(companies) == 1 else None)
    if not selected:
        return {"company": None, "hide_company": False}
    allowed = frappe.get_list("Company", filters={"name": selected},
        fields=["name", "country", "default_currency"], limit_page_length=1)
    if not allowed:
        frappe.throw("Not permitted to read this company.", frappe.PermissionError)
    info = allowed[0]
    country = info.get("country") or ""
    return {
        "company": info["name"],
        "country": country,
        "country_label": "UAE" if country == "United Arab Emirates" else country,
        "base_currency": info.get("default_currency") or "",
        "hide_company": len(companies) == 1 and companies[0] == info["name"],
    }
