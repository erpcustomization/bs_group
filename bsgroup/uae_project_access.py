"""Explicitly authorized UAE project access, independent of HR restrictions."""
import frappe

USER = "mithun@bitssecureit.com"
COMPANY = "Bits Secure IT Infrastructure LLC - AE"


def enabled():
    from bsgroup.hr_email import site_profile
    profile = site_profile()
    return bool(profile and profile["region"] == "UAE"
                and frappe.db.get_value("User", USER, "enabled"))


def grant(project):
    """Native shares bypass incidental Employee links without widening HR access."""
    from frappe.share import add_docshare
    existing = frappe.db.get_value("DocShare", {
        "user": USER, "share_doctype": "Project", "share_name": project,
    }, ["read", "write"], as_dict=True)
    if existing and existing.read and existing.write:
        return
    add_docshare("Project", project, user=USER, read=1, write=1,
                 flags={"ignore_share_permission": True}, notify=0)


def project_updated(doc, method=None):
    if enabled() and doc.company == COMPANY:
        grant(doc.name)


def install():
    if not enabled():
        return
    for name in frappe.get_all("Project", filters={"company": COMPANY}, pluck="name"):
        grant(name)
    frappe.clear_cache(user=USER)
