"""Make the app the single owner of the DCS deal status; reversible and hash-checked.

Only the exact known production version of the link-back Server Script is changed
(two status writes removed). A customised version is left as it is and reported;
``sync_quote_status`` then still corrects the status after it on every save.

Revert (staging/production, by an administrator):
    bench --site <site> execute bsgroup.patches.v0_1.dcs_quote_status_owner.revert
"""
import frappe

from bsgroup.dcs import linkback_script


def _current():
    if not frappe.db.exists("Server Script", linkback_script.NAME):
        return None
    return frappe.db.get_value("Server Script", linkback_script.NAME, "script")


def execute():
    decision = linkback_script.plan(_current())
    if decision != "convert":
        print(f"dcs_quote_status_owner: '{linkback_script.NAME}' {decision}; not changed.")
        return decision
    doc = frappe.get_doc("Server Script", linkback_script.NAME)
    doc.script = linkback_script.convert(doc.script)
    doc.save(ignore_permissions=True)
    doc.add_comment("Info", "Deal status writes removed by bsgroup patch dcs_quote_status_owner "
        f"(original sha256 {linkback_script.ORIGINAL_SHA256}). Revert with "
        "bsgroup.patches.v0_1.dcs_quote_status_owner.revert.")
    return decision


def revert():
    current = _current()
    if current is None or linkback_script.sha256(current) != linkback_script.converted_sha256():
        print("dcs_quote_status_owner.revert: script is not the converted version; not changed.")
        return False
    doc = frappe.get_doc("Server Script", linkback_script.NAME)
    doc.script = linkback_script.original()
    doc.save(ignore_permissions=True)
    doc.add_comment("Info", "Deal status writes restored by dcs_quote_status_owner.revert.")
    return True
