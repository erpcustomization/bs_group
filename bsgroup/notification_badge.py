"""Unread notification count for the current user only."""
import frappe


@frappe.whitelist()
def unread_count():
    if frappe.session.user == 'Guest':
        frappe.throw('Sign in to view notifications', frappe.PermissionError)
    return frappe.db.count('Notification Log', {'for_user': frappe.session.user, 'read': 0})
