"""Add procurement to the existing BS Group sidebar without replacing its items."""
import json

import frappe


def ensure_sidebar():
    ensure_app_icon()
    if not frappe.db.exists("DocType", "Sidebar") or not frappe.db.exists("Sidebar", "BS Group"):
        return
    sidebar = frappe.get_doc("Sidebar", "BS Group")
    section = next((i for i, row in enumerate(sidebar.items)
                    if row.type == "Section Break" and row.label == "BS Procurement"), None)
    changed = False
    if section is None:
        sidebar.append("items", dict(type="Section Break", label="BS Procurement",
                                     collapsible=1, keep_closed=1, indent=0, show_arrow=0))
        section = len(sidebar.items) - 1
        changed = True
    for field, value in dict(collapsible=1, indent=0, show_arrow=0).items():
        if sidebar.items[section].get(field) != value:
            sidebar.items[section].set(field, value)
            changed = True
    end = next((i for i in range(section + 1, len(sidebar.items))
                if sidebar.items[i].type == "Section Break"), len(sidebar.items))
    for label, view, icon in (
        ("Dashboard", "dashboard", "chart-no-axes-combined"),
        ("Purchase Requisition", "list", "file-text"),
        ("Purchase Order", "orders", "shopping-cart"),
        ("Payment Order", "services", "credit-card"),
    ):
        url = f"/desk/bs-group/bs-procurement?bsp_view={view}"
        options = json.dumps({"bsp_view": view})
        row = next((row for row in sidebar.items[section + 1:end]
                    if (row.link_type == "URL" and row.url == url) or
                    (row.link_type == "Page" and row.link_to == "bs-procurement"
                     and row.route_options == options)), None)
        if row is None:
            row = sidebar.append("items", {})
            sidebar.items.remove(row)
            sidebar.items.insert(section + 1 if view == "dashboard" else end, row)
            end += 1
            changed = True
        # Distinct filters preserve all three destinations in native sidebar deduplication.
        values = dict(type="Link", label=label, link_type="Page", link_to="bs-procurement",
                      route_options=options, filters=json.dumps([["bsp_view", "=", view]]),
                      url="", open_in_new_tab=0, icon=icon, child=1)
        for field, value in values.items():
            if row.get(field) != value:
                row.set(field, value)
                changed = True
    if changed:
        for i, row in enumerate(sidebar.items, 1):
            row.idx = i
        sidebar.save(ignore_permissions=True)
        frappe.clear_cache()


def ensure_app_icon():
    """Register navigation only, using the Procurement page's existing roles."""
    from pathlib import Path
    values = json.loads(Path(frappe.get_app_path("bsgroup", "desktop_icon", "bs_procurement.json")).read_text())
    values["roles"] = [{"role": row.role} for row in frappe.get_doc("Page", "bs-procurement").roles]
    if frappe.db.exists("Desktop Icon", values["name"]):
        doc = frappe.get_doc("Desktop Icon", values["name"])
        doc.update({k: v for k, v in values.items() if k not in ("doctype", "name", "roles")})
        doc.set("roles", values["roles"])
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc(values).insert(ignore_permissions=True)
    frappe.clear_cache()
