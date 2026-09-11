# DCS Handover Condition - Deletion Guard (Before Delete)
frappe.throw("Handover condition " + str(doc.name) + " cannot be deleted. Handover conditions and accepted risks are an immutable governance record. Clear it, or record a corrective condition instead.")
