"""Opt-in regional HR sender routing. Never changes default or incoming accounts."""
import inspect
import json
from email.parser import Parser
from email.policy import SMTP
from email.utils import formataddr
from urllib.parse import urlparse

import frappe

OMAN_HOSTS = {"erp-om.bitssecureit.com", "erp-om.k.frappe.cloud"}
OMAN_EMAIL = "hr-notifications-om@bitssecureit.com"
UAE_HOSTS = {"erp.bitssecureit.com", "erp-bitssecureit.u.frappe.cloud"}
UAE_EMAIL = "hr-notifications-ae@bitssecureit.com"
CUSTOM_HR_TYPES = {"HR Service Request", "HR Warning"}


def is_oman():
    profile = site_profile()
    return bool(profile and profile["region"] == "Oman")


def site_profile():
    """Use exact trusted site identities; never infer a country from recipients."""
    host = urlparse(frappe.conf.get("host_name") or "").hostname
    site = getattr(frappe.local, "site", None)
    for identity in (host, site):
        if identity in OMAN_HOSTS:
            return dict(region="Oman", email=OMAN_EMAIL, sender_name="HR Oman")
        if identity in UAE_HOSTS:
            return dict(region="UAE", email=UAE_EMAIL, sender_name="HR UAE")
    return None


def hr_document(doctype, name=None, depth=0):
    if not doctype or depth > 3:
        return False
    if doctype in CUSTOM_HR_TYPES:
        return True
    if doctype in ("Communication", "Notification Log") and name:
        fields = (["reference_doctype", "reference_name"] if doctype == "Communication"
                  else ["document_type", "document_name"])
        ref = frappe.db.get_value(doctype, name, fields)
        return bool(ref and hr_document(*ref, depth=depth + 1))
    module = frappe.get_cached_value("DocType", doctype, "module")
    return module in ("HR", "Payroll")


def hr_origin():
    """Legacy HRMS leave/reminder calls omit document references.

    Inspect code-module names only, never message text, recipient identity or
    frame locals. Reference-bearing non-HR mail is excluded before this call.
    Native HR reminder Sender settings also cover separately queued bulk mail.
    """
    frame = inspect.currentframe()
    try:
        for _ in range(60):
            frame = frame.f_back
            if frame is None:
                break
            module = frame.f_globals.get("__name__", "")
            if module.startswith(("hrms.hr.", "hrms.payroll.")) or module in (
                    "hrms.controllers.employee_reminders", "bsgroup.utils.employee", "bsgroup.utils.visa"):
                return True
        return False
    finally:
        del frame


def configured_account():
    if not site_profile():
        return None
    settings = frappe.get_cached_doc("HR Settings")
    if not settings.get("custom_bs_hr_email_enabled"):
        return None
    account = frappe.get_cached_doc("Email Account", settings.custom_bs_hr_email_account)
    validate_account(account)
    return account


def validate_account(account):
    profile = site_profile()
    if (not profile or account.email_id != profile["email"] or not account.enable_outgoing
            or account.default_outgoing or account.enable_incoming):
        frappe.throw("The HR sender must be this site's enabled, non-default, outgoing-only HR mailbox.")


def route_queue(doc, method=None):
    # Only new mail; historical and retry queues retain their original route.
    profile = site_profile()
    if not profile:
        return
    doctype, name = doc.get("reference_doctype"), doc.get("reference_name")
    if not doctype and doc.get("communication"):
        doctype, name = "Communication", doc.communication
    if not (hr_document(doctype, name) if doctype else hr_origin()):
        return
    account = configured_account()
    if not account:
        return
    # Preserve MIME parts, attachments, recipient lists, subject, message ID and
    # Reply-To (daily work summaries rely on their existing reply collection).
    message = Parser(policy=SMTP.clone(refold_source="none")).parsestr(doc.message)
    sender = formataddr((profile["sender_name"], account.email_id))
    if "From" in message:
        message.replace_header("From", sender)
    else:
        message["From"] = sender
    for header in ("Sender", "Return-Path"):
        if header in message:
            message.replace_header(header, sender if header == "Sender" else account.email_id)
    doc.sender = sender
    doc.email_account = account.name
    doc.message = message.as_string()
    if doc.get("communication") and frappe.db.exists("Communication", doc.communication):
        frappe.db.set_value("Communication", doc.communication,
                            {"sender": account.email_id, "sender_full_name": profile["sender_name"]}, update_modified=False)


def validate_settings(doc, method=None):
    profile = site_profile()
    old = doc.get_doc_before_save()
    fields = ("custom_bs_hr_email_enabled", "custom_bs_hr_email_account")
    if old and any(old.get(f) != doc.get(f) for f in fields):
        frappe.only_for("System Manager")
    native = ("sender", "sender_email", "hiring_sender", "hiring_sender_email")
    if not doc.get("custom_bs_hr_email_enabled"):
        if old and old.get("custom_bs_hr_email_enabled"):
            saved = json.loads(old.get("custom_bs_hr_email_previous_senders") or "{}")
            for field in native:
                if doc.get(field) in (old.get("custom_bs_hr_email_account"), (profile or {}).get("email")):
                    doc.set(field, saved.get(field))
            doc.custom_bs_hr_email_previous_senders = None
        return
    if not profile:
        frappe.throw("HR email routing is available only on the configured Oman and UAE sites.")
    validate_account(frappe.get_doc("Email Account", doc.custom_bs_hr_email_account))
    if not old or not old.get("custom_bs_hr_email_enabled"):
        doc.custom_bs_hr_email_previous_senders = json.dumps({f: doc.get(f) for f in native})
    # Native sender settings ensure reminders retain the route in bulk jobs.
    doc.sender = doc.hiring_sender = doc.custom_bs_hr_email_account
    doc.sender_email = doc.hiring_sender_email = profile["email"]


def install():
    profile = site_profile()
    if not profile:
        return
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    definitions = [
        dict(fieldname="custom_bs_hr_email_section", label="HR Email Routing", fieldtype="Section Break", insert_after="hiring_sender_email"),
        dict(fieldname="custom_bs_hr_email_account", label="HR Outgoing Email Account", fieldtype="Link", options="Email Account", insert_after="custom_bs_hr_email_section"),
        dict(fieldname="custom_bs_hr_email_enabled", label=f"Use {profile['region']} HR sender for HR emails", fieldtype="Check", default="0", insert_after="custom_bs_hr_email_account",
             description=f"HR emails use {profile['email']}. Default and incoming mail accounts are unchanged. Existing recipients and reply handling are preserved."),
        dict(fieldname="custom_bs_hr_email_previous_senders", label="Previous HR Senders", fieldtype="Small Text", hidden=1, read_only=1, insert_after="custom_bs_hr_email_enabled"),
    ]
    meta = frappe.get_meta("HR Settings")
    missing = [d for d in definitions if not meta.has_field(d["fieldname"])]
    if missing:
        create_custom_fields({"HR Settings": missing}, update=False)


def configure_hooks(hooks):
    def append(mapping, key, value):
        previous = mapping.get(key, [])
        values = [previous] if isinstance(previous, str) else list(previous)
        if value not in values:
            values.append(value)
        mapping[key] = values
    append(hooks.setdefault('scheduler_events', {}).setdefault('cron', {}),
           '2 9 * * 5', 'bsgroup.weekly_attendance_email.send_summaries')
    append(hooks, "after_migrate", "bsgroup.hr_email.install")
    for doctype, event, method in (("Email Queue", "before_insert", "route_queue"),
                                   ("HR Settings", "validate", "validate_settings")):
        mapping = hooks.setdefault("doc_events", {}).setdefault(doctype, {})
        append(mapping, event, "bsgroup.hr_email." + method)
