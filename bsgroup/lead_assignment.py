"""Audited sales handover for intake coordinators, limited to writable Leads."""
import frappe
from frappe import _

SALES_ROLES = {"BS Scoped Sales", "Sales User", "Sales Manager"}


def can_transfer():
    return frappe.session.user == "Administrator" or bool(
        {"BS Lead Intake Manager", "Sales Manager", "System Manager"} & set(frappe.get_roles()))


def _check_actor():
    if not can_transfer():
        frappe.throw(_("Lead assignment management permission is required."), frappe.PermissionError)


def _eligible(user, company):
    account = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    if not account or not account.enabled or account.user_type != "System User":
        return False
    if not SALES_ROLES.intersection(frappe.get_roles(user)) or not frappe.has_permission("Lead", "read", user=user):
        return False
    from frappe.permissions import get_user_permissions
    allowed = [p.doc for p in get_user_permissions(user).get("Company", [])
               if not p.get("applicable_for") or p.applicable_for == "Lead"]
    return not company or not allowed or company in allowed


@frappe.whitelist()
def choices(name):
    _check_actor()
    lead = frappe.get_doc("Lead", name)
    lead.check_permission("write")
    return [{"value": u.name, "label": u.full_name or u.name} for u in
            frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"},
                           fields=["name", "full_name"], order_by="full_name asc")
            if _eligible(u.name, lead.company)]


@frappe.whitelist(methods=["POST"])
def transfer(name, to_user, expected_modified):
    _check_actor()
    savepoint = "lead_transfer_" + frappe.generate_hash(length=10)
    frappe.db.savepoint(savepoint)
    try:
        lead = frappe.get_doc("Lead", name, for_update=True)
        lead.check_permission("write")
        if str(lead.modified) != str(expected_modified):
            frappe.throw(_("The Lead changed. Refresh it before assigning a salesperson."))
        if not _eligible(to_user, lead.company):
            frappe.throw(_("Select an active salesperson with access to this Lead's company."), frappe.PermissionError)
        previous = lead.lead_owner
        if previous != to_user:
            lead.lead_owner = to_user
            # Ownership-only handover must work for older intake records whose
            # unrelated form fields predate today's mandatory-field layout.
            lead.flags.ignore_mandatory = True
            lead.save()
            if previous and "BS Scoped Sales" in frappe.get_roles(previous):
                from frappe import share
                share.remove("Lead", name, previous, flags={"ignore_permissions": True, "ignore_share_permission": True})
            lead.add_comment("Info", _("Sales handover by {0}: Lead Owner changed from {1} to {2}. Assignment and access transferred together.").format(
                frappe.session.user, previous or "Unassigned", to_user))
        return {"name": name, "lead_owner": to_user, "can_read": lead.has_permission("read")}
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        raise


@frappe.whitelist(methods=["POST"])
def assign(args=None, **kwargs):
    """The native assignment entry point uses the same checked sales handover."""
    from frappe.desk.form import assign_to
    data = frappe.parse_json(args) if args else (kwargs or frappe.local.form_dict)
    if data.get("doctype") != "Lead" or "BS Lead Intake Manager" not in frappe.get_roles():
        return assign_to.add(data)
    users = frappe.parse_json(data.get("assign_to"))
    if not isinstance(users, list) or len(users) != 1:
        frappe.throw(_("Choose one salesperson to take ownership of this Lead."))
    lead = frappe.get_doc("Lead", data.get("name"))
    transfer(lead.name, users[0], str(lead.modified))
    return assign_to.get({"doctype": "Lead", "name": lead.name})
