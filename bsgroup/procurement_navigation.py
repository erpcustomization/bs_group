"""Add procurement to the existing BS Group sidebar without replacing its items."""
import frappe


def ensure_sidebar():
    if not frappe.db.exists("DocType", "Sidebar") or not frappe.db.exists("Sidebar", "BS Group"):
        return
    sidebar = frappe.get_doc("Sidebar", "BS Group")
    section = next((i for i, row in enumerate(sidebar.items)
                    if row.type == "Section Break" and row.label == "BS Procurement"), None)
    changed = False
    if section is None:
        sidebar.append("items", dict(type="Section Break", label="BS Procurement",
                                     collapsible=1, keep_closed=1, indent=1, show_arrow=1))
        section = len(sidebar.items) - 1
        changed = True
    end = next((i for i in range(section + 1, len(sidebar.items))
                if sidebar.items[i].type == "Section Break"), len(sidebar.items))
    for label, view, icon in (
        ("Purchase Requisition", "list", "file-text"),
        ("Purchase Order", "orders", "shopping-cart"),
        ("Payment Order", "services", "credit-card"),
    ):
        url = f"/desk/bs-group/bs-procurement?bsp_view={view}"
        if any(row.link_type == "URL" and row.url == url for row in sidebar.items[section + 1:end]):
            continue
        row = sidebar.append("items", dict(type="Link", label=label, link_type="URL",
                                          url=url, open_in_new_tab=0, icon=icon, child=1))
        sidebar.items.remove(row)
        sidebar.items.insert(end, row)
        end += 1
        changed = True
    if changed:
        for i, row in enumerate(sidebar.items, 1):
            row.idx = i
        sidebar.save(ignore_permissions=True)
        frappe.clear_cache()
