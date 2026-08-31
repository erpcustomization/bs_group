import frappe

def validate_company_on_login(login_manager):
    user = frappe.session.user
    if user in ("Administrator", "Guest"):
        return

    has_company = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Company"},
        limit=1,
    )

    if not has_company:
        frappe.throw(f"No company assigned to {user}. Please contact your administrator.")


@frappe.whitelist()
def user_details():
    user = frappe.session.user

    user_permissions = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Company"},
        fields=["for_value", "is_default"],
        order_by="is_default desc",
        limit=0,
    )

    if not user_permissions:
        return []

    default_company = (
        frappe.defaults.get_user_default("Company")
        or frappe.defaults.get_global_default("company")
    )

    company_names = [perm["for_value"] for perm in user_permissions]

    all_companies = frappe.get_all(
        "Company",
        filters={"name": ["in", company_names]},
        fields=["name", "abbr"],
        limit=0,
    )
    for c in all_companies:
        abbr = (c.get("abbr") or "").strip()
        if not abbr:
            abbr = "".join(w[0] for w in c["name"].split() if w)[:3] or c["name"][:3]
        c["abbr"] = abbr.upper()

    if default_company:
        all_companies = sorted(
            all_companies,
            key=lambda x: (x["name"] == default_company),
            reverse=True,
        )

    return all_companies


@frappe.whitelist()
def set_user_permission(company):
    user = frappe.session.user

    if not company:
        frappe.throw("Company is required")

    existing_permissions = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Company"},
        fields=["name", "for_value", "is_default"],
    )

    allowed_values = [p["for_value"] for p in existing_permissions]
    if company not in allowed_values:
        frappe.throw(f"You do not have permission to switch to company: {company}")

    for perm in existing_permissions:
        is_selected = 1 if perm["for_value"] == company else 0
        frappe.db.set_value(
            "User Permission",
            perm["name"],
            {"is_default": is_selected, "apply_to_all_doctypes": is_selected},
            update_modified=False,
        )

    frappe.defaults.set_user_default("company", company, user)

    try:
        from frappe.core.doctype.session_default_settings.session_default_settings import (
            set_session_default_values,
        )
        set_session_default_values({"company": company})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "set_session_default_values failed")

    frappe.db.commit()
    frappe.cache.hdel("user_permissions", user)

    return {"success": True, "company": company}


def global_company_condition(user, doctype=None):
    """
    Wildcard permission_query_conditions handler ('*' key in hooks).
    Appends `company = <selected>` for every doctype that has a company Link field.
    """
    if not user:
        user = frappe.session.user
    if user in ("Administrator", "Guest"):
        return ""
    if not doctype:
        return ""

    try:
        meta = frappe.get_meta(doctype)
        has_company_field = any(
            f.fieldname == "company" and f.fieldtype == "Link" and f.options == "Company"
            for f in meta.fields
        )
    except Exception:
        return ""

    if not has_company_field:
        return ""
    company = (
        frappe.defaults.get_user_default("Company", user)
        or frappe.defaults.get_global_default("company")
    )
    if not company:
        return ""

    return f"`tab{doctype}`.`company` = {frappe.db.escape(company)}"

