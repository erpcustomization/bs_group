"""Personal login landing and app destinations; never grants document access."""
import frappe

DASHBOARD = "/desk/my-work-dashboard"


def on_session_creation(login_manager):
    # LoginManager reads this after session creation, ahead of cached role/workspace
    # home pages. Do not persist a change to any user's roles or preferences.
    if frappe.db.get_value("User", login_manager.user, "user_type") == "System User":
        frappe.local.flags.home_page = DASHBOARD


def destinations():
    from bsgroup.scoped_sales_access import scope, SCREENS
    from bsgroup.hr_management import can_manage

    mode = scope()
    allowed = SCREENS.get(mode) if mode else None

    def first(*doctypes):
        for dt in doctypes:
            if allowed is not None and dt not in allowed:
                continue
            if frappe.db.exists("DocType", dt) and frappe.has_permission(dt, "read"):
                return "/desk/bs-group/" + frappe.scrub(dt).replace("_", "-")
        return None

    routes = {
        "BS Sales": first("Lead", "Opportunity", "Presales Request", "Deal Cost Sheet", "Quotation"),
        "BS Project": first("Project", "Task", "Timesheet", "Site Survey Request", "Delivery Request", "Tech Task Scheduler"),
        "BS Helpdesk": first("HD Ticket"),
        "BS AMC": first("AMC Contract"),
        "BS PPM": first("PPM Plan", "PPM Visit"),
        "BS Support": first("Issue"),
        "BS Approvals": first("Labor Preapproval", "Employee Advance", "Expense Claim", "Material Request", "Cheque Request"),
        "BS Procurement": first("Material Request", "Purchase Order"),
        "BS HR": "/desk/bs-group/hr-dashboard" if can_manage() else None,
        "BS User Management": "/desk/bs-group/bs-user-management"
            if "System Manager" in frappe.get_roles() else None,
    }
    return routes


def project_support_links():
    """Navigation only: use existing DocType and report grants, never write roles."""
    from urllib.parse import quote
    from bsgroup.scoped_sales_access import scope, SCREENS

    mode = scope()
    allowed = SCREENS.get(mode) if mode else None

    def permitted(dt, permission="read"):
        return (allowed is None or dt in allowed) and frappe.db.exists("DocType", dt) and frappe.has_permission(dt, permission)

    links = [dict(label=dt, href="/desk/bs-group/" + frappe.scrub(dt).replace("_", "-") + "?bs_app=BS%20Project")
             for dt in ("Project", "Site Survey Request", "Delivery Request", "Task", "Timesheet", "Tech Task Scheduler")
             if permitted(dt)]
    roles = set(frappe.get_roles())
    for name in ("Task Summary Report", "Task Scheduler Report", "Tech Task Scheduler Report"):
        if not frappe.db.exists("Report", name):
            continue
        report = frappe.get_doc("Report", name)
        if report.disabled or not permitted(report.ref_doctype, "report"):
            continue
        if frappe.session.user != "Administrator" and not roles.intersection(row.role for row in report.roles):
            continue
        links.append(dict(label=name, href="/desk/bs-group/query-report/" + quote(name) + "?bs_app=BS%20Project"))
    return links
