"""Installable BS ERP: a public install page around the existing permission-checked Desk."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import frappe

VERSION = "20261112-1"
API = "/api/method/bsgroup.bs_erp_app."
START = "/desk/my-work-dashboard?bs_erp=1"


def branding():
    site = str(getattr(frappe.local, "site", "") or "").lower()
    request = getattr(frappe.local, "request", None)
    host = urlsplit(getattr(request, "url", "") or "").hostname or ""
    names = {site, host.lower()}
    region = ("Oman" if names & {"erp-om.bitssecureit.com", "erp-om.k.frappe.cloud"}
              else "UAE" if names & {"erp.bitssecureit.com", "erp-bitssecureit.u.frappe.cloud"}
              else "")
    return {"region": region, "name": ("BS ERP " + region).strip(),
            "icon_key": region.lower() or "default", "api": API, "version": VERSION, "start": START}


def manifest_data():
    brand = branding()
    return {"id": "/bs-erp", "name": brand["name"], "short_name": brand["name"],
            "description": "Your BS ERP dashboard and authorised modules in one place.",
            "lang": "en", "start_url": START, "scope": "/", "display": "standalone",
            "background_color": "#f4f7fb", "theme_color": "#123354",
            "prefer_related_applications": False,
            "icons": [{"src": API + f"icon?size={size}&v={VERSION}", "sizes": f"{size}x{size}",
                       "type": "image/png", "purpose": "any maskable"} for size in (192, 512)]}


def send(content, filename, mime):
    frappe.local.response.update(type="download", filename=filename, filecontent=content,
                                 content_type=mime, display_content_as="inline")


@frappe.whitelist(allow_guest=True, methods=["GET"])
def manifest():
    send(json.dumps(manifest_data()), "bs-erp.webmanifest", "application/manifest+json")


@frappe.whitelist(allow_guest=True, methods=["GET"])
def icon(size="192", v=None):
    # Only bundled public artwork can be read; no caller-supplied path is accepted.
    if str(size) not in {"180", "192", "512"}:
        frappe.throw("Unsupported app icon size.")
    name = f"bs-erp-{branding()['icon_key']}-{size}.png"
    send(Path(frappe.get_app_path("bsgroup", "public", "img", "bs_erp", name)).read_bytes(), name, "image/png")


@frappe.whitelist(allow_guest=True, methods=["GET"])
def script(v=None):
    send(Path(frappe.get_app_path("bsgroup", "public", "js", "bs_erp_app.js")).read_text(),
         "bs-erp.js", "application/javascript")


@frappe.whitelist(allow_guest=True, methods=["GET"])
def style(v=None):
    send(Path(frappe.get_app_path("bsgroup", "public", "css", "bs_erp_app.css")).read_text(),
         "bs-erp.css", "text/css")
