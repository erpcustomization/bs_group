import frappe


def get_common_conditions(user):
    if not user:
        user = frappe.session.user
    doctype = frappe.local.form_dict.get("doctype")

    return get_team_records_condition(user, doctype)


def get_reporting_team_users(user):
    """
    Returns a list of user emails who directly report to the given user
    (via Employee.reports_to). Includes the user themselves.
    """
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return [user]

    team_users = frappe.get_all(
        "Employee",
        filters={"reports_to": employee},
        pluck="user_id"
    )
    team_users = [u for u in team_users if u]  # remove blanks
    team_users.append(user)
    return team_users


def get_team_records_condition(user, doctype):
    if not doctype:
        return ""

    roles = frappe.get_roles(user)

    if "System Manager" in roles:
        return ""

    # Deal Cost Sheet has its own logic
    if doctype == "Deal Cost Sheet":
        return get_deal_cost_sheet_query_conditions(user)

    escaped_user = frappe.db.escape(user)[1:-1]  # strip surrounding quotes added by escape
    assigned_condition = f"`tab{doctype}`.`_assign` LIKE '%%\"{escaped_user}\"%%'"

    if "Sales Manager" in roles:
        # Sales Manager sees their own records + all records from direct reports
        # For Opportunity, match on opportunity_owner; for others, match on owner
        field = "opportunity_owner" if doctype == "Opportunity" else "owner"
        team_users = get_reporting_team_users(user)
        users_list = "', '".join(team_users)
        return f"(`tab{doctype}`.`{field}` IN ('{users_list}') OR {assigned_condition})"

    # Sales User / Presales User: records they created OR are assigned to
    return f"(`tab{doctype}`.`owner` = '{user}' OR {assigned_condition})"


def get_user_sales_person(user):
    """
    Map a User to their Sales Person record via Employee.user_id -> Sales Person.employee.
    Returns the Sales Person name, or None if the user isn't linked to one.
    """
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return None

    return frappe.db.get_value("Sales Person", {"employee": employee}, "name")


def customer_has_sales_team_access(customer, user=None):
    """
    A customer is accessible to a user if:
    - the customer has no Sales Team rows at all (open to any Sales User), or
    - the user's Sales Person is listed in the customer's Sales Team.
    """
    if not user:
        user = frappe.session.user

    sales_team = frappe.get_all(
        "Sales Team",
        filters={"parenttype": "Customer", "parent": customer},
        pluck="sales_person",
    )

    if not sales_team:
        return True

    sales_person = get_user_sales_person(user)
    return bool(sales_person and sales_person in sales_team)


def get_customer_query_conditions(user):
    """permission_query_conditions for Customer: restrict list/report visibility
    to customers where the user's Sales Person is on the Sales Team, or customers
    with no Sales Team assigned at all."""
    if not user:
        user = frappe.session.user

    roles = frappe.get_roles(user)
    if "System Manager" in roles or "Sales Manager" in roles:
        return ""

    sales_person = get_user_sales_person(user)
    escaped_sales_person = frappe.db.escape(sales_person) if sales_person else "''"

    return f"""
        (
            not exists (
                select 1 from `tabSales Team`
                where `tabSales Team`.parenttype = 'Customer'
                and `tabSales Team`.parent = `tabCustomer`.name
            )
            or exists (
                select 1 from `tabSales Team`
                where `tabSales Team`.parenttype = 'Customer'
                and `tabSales Team`.parent = `tabCustomer`.name
                and `tabSales Team`.sales_person = {escaped_sales_person}
            )
        )
    """


def has_customer_permission(doc, ptype=None, user=None):
    """has_permission hook for Customer: enforces the same Sales Team based
    access at the single-document level (list filtering alone doesn't stop
    direct access by name/route, e.g. opening a Customer Statement print view)."""
    if not user:
        user = frappe.session.user

    roles = frappe.get_roles(user)
    if "System Manager" in roles or "Sales Manager" in roles:
        return True

    if "Sales User" not in roles:
        # Non-sales roles are governed by the standard role permission stack.
        return None

    return customer_has_sales_team_access(doc.name, user)


def get_sales_target_gp_entry_allowed_sales_persons(user=None):
    """Sales Person names visible to `user` for Sales Target GP Entry, derived
    ONLY from the Employee reporting hierarchy: user -> Employee (via user_id)
    -> subordinates (Employee.reports_to, recursive) -> Sales Person (via
    Sales Person.employee). A manager sees their own + all reportees (any
    depth); a plain salesperson sees only their own. Returns None for
    System Manager / Administrator, meaning "no restriction"."""
    if not user:
        user = frappe.session.user

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return None

    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return []

    emp_ids = set()
    frontier = [employee]
    while frontier:
        emp_ids.update(frontier)
        children = frappe.get_all(
            "Employee",
            filters=[["reports_to", "in", frontier]],
            pluck="name",
        )
        frontier = [c for c in children if c not in emp_ids]

    return frappe.get_all(
        "Sales Person",
        filters=[["employee", "in", list(emp_ids)]],
        pluck="name",
    )


def get_sales_target_gp_entry_query_conditions(user):
    """permission_query_conditions for Sales Target GP Entry: access is
    derived ONLY from the Employee reporting hierarchy (see
    get_sales_target_gp_entry_allowed_sales_persons). System Manager /
    Administrator see all; an Employee with no linked Sales Person, or no
    Employee mapping at all, sees only records they created."""
    if not user:
        user = frappe.session.user

    allowed = get_sales_target_gp_entry_allowed_sales_persons(user)
    if allowed is None:
        return ""

    if not allowed:
        return f"`tabSales Target GP Entry`.owner = {frappe.db.escape(user)}"

    escaped = ", ".join(frappe.db.escape(a) for a in allowed)
    return f"`tabSales Target GP Entry`.salesperson in ({escaped})"


def get_deal_cost_sheet_query_conditions(user):
    if not user:
        user = frappe.session.user

    roles = frappe.get_roles(user)

    if "System Manager" in roles:
        return ""

    if "Projects Manager" in roles:
        return "`tabDeal Cost Sheet`.`docstatus` = 1"

    if "Sales Manager" in roles:
        team_users = get_reporting_team_users(user)
        users_list = "', '".join(team_users)
        return (
            f"(`tabDeal Cost Sheet`.`docstatus` = 1"
            f" AND (`tabDeal Cost Sheet`.`owner` IN ('{users_list}')"
            f" OR `tabDeal Cost Sheet`.`deal_owner` = '{user}'))"
            f" OR `tabDeal Cost Sheet`.`owner` = '{user}'"
        )

    return (
        f"(`tabDeal Cost Sheet`.`owner` = '{user}'"
        f" OR (`tabDeal Cost Sheet`.`deal_owner` = '{user}'"
        f" AND `tabDeal Cost Sheet`.`docstatus` = 1))"
    )
