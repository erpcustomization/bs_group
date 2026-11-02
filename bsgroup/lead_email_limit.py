"""Allow at most five Lead records per normalized email address."""
import frappe


def validate(doc):
    email = (doc.get('email_id') or '').strip().lower()
    if not email:
        return
    previous = doc.get_doc_before_save()
    if not doc.is_new() and previous and (previous.get('email_id') or '').strip().lower() == email:
        return
    # Serialize creation/email changes, including simultaneous requests. Locking
    # reads use current committed rows rather than an earlier transaction snapshot.
    frappe.db.sql("SELECT name FROM tabDocType WHERE name = 'Lead' FOR UPDATE")
    matches = frappe.db.sql("""SELECT name FROM tabLead
        WHERE LOWER(TRIM(email_id)) = %s AND name != %s LIMIT 5 FOR UPDATE""",
        (email, doc.name or ''))
    if len(matches) >= 5:
        frappe.throw('This email address already has 5 leads. A maximum of 5 leads per email address is allowed.',
                     frappe.DuplicateEntryError)
    doc.email_id = email
