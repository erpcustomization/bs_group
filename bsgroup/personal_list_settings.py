"""Compatibility for older list clients: resizing must not edit shared metadata."""
import math
import frappe


def column_widths(fields, allowed):
    widths = {}
    for field in fields:
        name = field.get("fieldname")
        if name not in allowed or field.get("width") is None:
            continue
        try:
            width = float(field["width"])
        except (ValueError, TypeError):
            continue
        if math.isfinite(width):
            widths[name] = max(50, min(400, width))
    return widths


@frappe.whitelist()
def save_listview_settings(doctype, listview_settings, removed_listview_fields=None):
    from frappe.desk.doctype.list_view_settings.list_view_settings import save_listview_settings as original
    from frappe.model.utils.user_settings import update_user_settings, get_user_settings
    if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
        return original(doctype, listview_settings, removed_listview_fields or [])
    frappe.has_permission(doctype, "read", throw=True)
    meta = frappe.get_meta(doctype)
    settings = frappe.parse_json(listview_settings) or {}
    fields = frappe.parse_json(settings.get("fields")) or []
    widths = column_widths(fields, {f.fieldname for f in meta.fields} | {"name", "status_field"})
    personal = frappe.parse_json(get_user_settings(doctype)) or {}
    personal_widths = personal.get("bs_column_widths") or {}
    personal_widths.update(widths)
    update_user_settings(doctype, {"bs_column_widths": personal_widths})
    # Older resize clients expect this response. Never save their other settings,
    # field visibility, or property setters to the shared List View Settings.
    return {"meta": meta, "listview_settings": settings}
