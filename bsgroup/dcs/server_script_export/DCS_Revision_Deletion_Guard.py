# Revision history is an audit trail. Entries are never removed.
frappe.throw("DCS Revision " + str(doc.name) + " cannot be deleted. Negotiation history is an immutable audit trail. If the revision was recorded in error, record a corrective revision instead.")
