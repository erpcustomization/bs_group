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
        "BS Project": first("Project", "Task", "Timesheet"),
        "BS Helpdesk": first("HD Ticket"),
        "BS AMC": first("AMC Contract"),
        "BS PPM": first("PPM Plan", "PPM Visit"),
        "BS Support": first("Issue"),
        "BS Approvals": first("Labor Preapproval", "Employee Advance", "Expense Claim", "Material Request", "Cheque Request"),
        "BS Procurement": first("Material Request", "Purchase Order"),
        "BS HR": "/desk/bs-group/hr-dashboard" if can_manage() else None,
    }
    return routes
