"""Use the Item Group for commercial category; stock tracking is a fallback."""
import frappe

def category_for_item(item_code):
    item=frappe.db.get_value("Item",item_code,["item_group","is_stock_item"],as_dict=True) if item_code else None
    if not item:
        return "Products"
    group=item.item_group
    visited=set()
    while group and group not in visited:
        visited.add(group)
        if group=="Products":
            return "Products"
        if group in ("Services","Professional Services"):
            return "Professional Services"
        group=frappe.db.get_value("Item Group",group,"parent_item_group")
    return "Products" if item.is_stock_item else "Professional Services"

@frappe.whitelist()
def get_item_category(item_code):
    if not (frappe.has_permission("Item","read",doc=item_code) or frappe.has_permission("Item","select",doc=item_code)):
        frappe.throw("You may not select this Item.",frappe.PermissionError)
    return category_for_item(item_code)
