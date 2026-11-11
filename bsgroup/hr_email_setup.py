"""Administrator-only, targeted setup of the Oman HR email pilot."""
from html import escape

import frappe

from bsgroup.hr_email import install, is_oman


def guard():
    frappe.only_for("System Manager")
    if not is_oman():
        frappe.throw("This setup is available only on the Oman pilot site.")


@frappe.whitelist(methods=["GET"])
def page():
    guard()
    from frappe.sessions import get_csrf_token
    token = escape(get_csrf_token(), quote=True)
    frappe.respond_as_web_page("Oman HR Email Setup", f'''
        <p>Install the HR sender settings for the Oman pilot. This step leaves
        email routing switched off and does not change existing mail accounts.</p>
        <form method="post" action="/api/method/bsgroup.hr_email_setup.setup">
        <input type="hidden" name="csrf_token" value="{token}">
        <button class="btn btn-primary" type="submit">Install HR sender settings</button>
        </form>''')


@frappe.whitelist(methods=["POST"])
def setup():
    guard()
    install()
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = "/desk/hr-settings"
