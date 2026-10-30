"""Record ownership restrictions for the dedicated Sales/Presales workspaces."""
import frappe

SALES = "BS Scoped Sales"
PRESALES = "BS Scoped Presales"
SCREENS = {
    SALES: ("Lead", "Opportunity", "Deal Cost Sheet", "Quotation"),
    PRESALES: ("Presales Request", "Deal Cost Sheet", "Quotation"),
}


def scope(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return None
    roles = frappe.get_roles(user)
    return PRESALES if PRESALES in roles else SALES if SALES in roles else None


def own(alias, field, user):
    who = frappe.db.escape(user)
    return f"COALESCE(NULLIF({alias}.`{field}`, ''), {alias}.owner) = {who}"


def condition(doctype, user):
    mode = scope(user)
    if not mode:
        return None
    if doctype not in SCREENS[mode]:
        return "1=0"
    table = f"`tab{doctype}`"
    who = frappe.db.escape(user)
    if doctype == "Lead":
        return own(table, "lead_owner", user)
    if doctype == "Opportunity":
        return own(table, "opportunity_owner", user)
    if doctype == "Presales Request":
        return own(table, "presales_owner", user)
    if doctype == "Deal Cost Sheet":
        if mode == SALES:
            return (f"(EXISTS (SELECT 1 FROM `tabOpportunity` o WHERE o.name={table}.opportunity "
                    f"AND {own('o', 'opportunity_owner', user)}) OR "
                    f"(COALESCE({table}.opportunity,'')='' AND {own(table, 'deal_owner', user)}))")
        assigned = frappe.db.escape('%"' + user + '"%')
        return (f"({table}._assign LIKE {assigned} OR EXISTS "
                f"(SELECT 1 FROM `tabPresales Request` p WHERE p.name={table}.presales_request "
                f"AND {own('p', 'presales_owner', user)}))")
    if mode == PRESALES:
        return f"{table}.owner={who}"
    return (f"(EXISTS (SELECT 1 FROM `tabOpportunity` o WHERE o.name={table}.opportunity "
            f"AND {own('o', 'opportunity_owner', user)}) OR "
            f"(COALESCE({table}.opportunity,'')='' AND {table}.owner={who}))")


def query(user=None, doctype=None):
    user = user or frappe.session.user
    restricted = condition(doctype, user)
    if restricted is not None:
        return restricted
    from bsgroup.permissions import get_common_conditions, get_deal_cost_sheet_query_conditions
    from bsgroup.site_survey import presales_query, survey_query
    if doctype == "Site Survey Request":
        return survey_query(user)
    if doctype == "Presales Request":
        return presales_query(user)
    if doctype == "Deal Cost Sheet":
        return get_deal_cost_sheet_query_conditions(user)
    return get_common_conditions(user)


def lead_query(user=None):
    return query(user, "Lead")


def opportunity_query(user=None):
    return query(user, "Opportunity")


def presales_query(user=None):
    return query(user, "Presales Request")


def dcs_query(user=None):
    return query(user, "Deal Cost Sheet")


def quotation_query(user=None):
    return query(user, "Quotation")


def survey_query(user=None):
    return query(user, "Site Survey Request")


def permission(doc, user=None, permission_type=None, ptype=None):
    user = user or frappe.session.user
    sql = condition(doc.doctype, user)
    if sql is None:
        if doc.doctype == "Site Survey Request":
            from bsgroup.site_survey import survey_permission
            return survey_permission(doc, user, permission_type, ptype)
        return None
    if sql == "1=0":
        return False
    if doc.is_new():
        return None  # Native create rights and existing intake validations apply.
    allowed = frappe.db.sql(f"SELECT name FROM `tab{doc.doctype}` WHERE name=%s AND ({sql})", doc.name)
    return None if allowed else False


def boot_session(bootinfo):
    mode = scope()
    if not mode:
        return
    allowed = SCREENS[mode]
    bootinfo.bs_scoped_screens = list(allowed)
    # Filter the server-provided sidebar model as well as its rendered navigation.
    for key in ("workspace_sidebar_item", "module_sidebars"):
        for sidebar in (bootinfo.get(key) or {}).values():
            if isinstance(sidebar, dict) and sidebar.get("items"):
                sidebar["items"] = [i for i in sidebar["items"] if i.get("link_type") == "DocType" and i.get("link_to") in allowed]


@frappe.whitelist(methods=["POST"])
def configure_dubai():
    """Explicit, audited rollout to the four accounts requested by the administrator."""
    if frappe.session.user != "Administrator":
        frappe.throw("Only Administrator can apply this access configuration.", frappe.PermissionError)
    targets = {"gopinath@bitssecureit.com": SALES, "priya@bitssecureit.com": SALES,
               "paul@bitssecureit.com": SALES, "sanisha@bitssecureit.com": PRESALES}
    for user in targets:
        if not frappe.db.exists("User", user):
            frappe.throw("Missing user: " + user)
    from frappe.permissions import setup_custom_perms
    def set_rule(dt, role, level, values):
        setup_custom_perms(dt)
        name = frappe.db.get_value("Custom DocPerm", {"parent": dt, "role": role, "permlevel": level, "if_owner": 0})
        rule = frappe.get_doc("Custom DocPerm", name) if name else frappe.get_doc({
            "doctype": "Custom DocPerm", "parent": dt, "parenttype": "DocType", "parentfield": "permissions",
            "role": role, "permlevel": level, "if_owner": 0})
        rule.update(values)
        rule.save()
        frappe.clear_cache(doctype=dt)
    for role, doctypes in SCREENS.items():
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()
        for dt in doctypes:
            source = "Presales" if role == PRESALES and dt != "Quotation" else "Sales User"
            source_rules = [p.as_dict() for p in frappe.get_meta(dt).permissions if p.role == source]
            for rule in source_rules:
                level = rule.get("permlevel") or 0
                values = {}
                for key in ("select", "read", "write", "create", "submit", "cancel", "amend", "delete", "print", "email", "export"):
                    values[key] = int(bool(rule.get(key)))
                # Custom reports and sharing must not bypass ownership restrictions.
                for key in ("report", "share", "import"):
                    values[key] = 0
                set_rule(dt, role, level, values)
        for dt in ("Company", "Customer", "Lead", "Opportunity", "Presales Request", "Item", "Item Group", "UOM", "Currency", "Price List", "Sales Person", "User", "Account", "Cost Center", "Warehouse", "Sales Taxes and Charges Template", "Payment Terms Template", "Terms and Conditions", "Contact", "Address", "Opportunity Type", "Opportunity Lost Reason"):
            if dt in doctypes or not frappe.db.exists("DocType", dt):
                continue
            # Reference masters are needed to populate the permitted forms, but
            # are not exposed as workspace tabs or granted edit/create rights.
            reference_read = dt not in ("Lead", "Opportunity", "Presales Request", "User")
            set_rule(dt, role, 0, {"select": 1, "read": int(reference_read)})
    result = []
    for user, role in targets.items():
        doc = frappe.get_doc("User", user)
        before = [r.role for r in doc.roles]
        doc.role_profile_name = None
        doc.set("roles", [{"role": "Employee"}, {"role": role}])
        doc.save()
        doc.add_comment("Info", "Scoped sales workspace applied. Previous roles: " + ", ".join(before) + ". New role: " + role)
        frappe.clear_cache(user=user)
        result.append({"user": user, "role": role, "screens": SCREENS[role]})
    return result
