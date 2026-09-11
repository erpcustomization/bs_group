# DCS Handover Condition - Accepted Risk Guard (Before Save)
# An accepted risk retains its original blocker identity and can never be marked Clear.
# The acceptance record is immutable once written.

prev = doc.get_doc_before_save()

if prev is not None:
	if prev.get("state") == "Accepted Risk":
		if doc.get("state") != "Accepted Risk":
			frappe.throw("Handover condition " + str(doc.name) + " is a recorded ACCEPTED RISK. An accepted risk retains its original blocker and can never be marked Cleared or reopened. Raise a new condition instead.")
		locked = ["accepted_by", "accepted_on", "acceptance_reason", "acknowledged", "exposure_amount", "exposure_note", "follow_up_date", "original_category", "condition_title", "domain", "dcs", "condition_no"]
		for f in locked:
			if str(prev.get(f)) != str(doc.get(f)):
				frappe.throw("Accepted risk " + str(doc.name) + " is immutable. The field '" + str(f) + "' cannot be changed after the risk was accepted.")
	if prev.get("state") == "Cleared":
		if doc.get("state") == "Accepted Risk":
			frappe.throw("Handover condition " + str(doc.name) + " is already Cleared. A cleared condition cannot be converted into an accepted risk.")
	locked2 = ["dcs", "condition_no", "raised_by", "raised_on"]
	for f2 in locked2:
		if str(prev.get(f2)) != str(doc.get(f2)):
			frappe.throw("Handover condition " + str(doc.name) + " identity is immutable. The field '" + str(f2) + "' cannot be changed.")

if doc.get("state") == "Accepted Risk":
	if not doc.get("acceptance_reason"):
		frappe.throw("An accepted risk requires a written reason.")
	if not doc.get("acknowledged"):
		frappe.throw("An accepted risk requires an explicit acknowledgement.")
	if str(doc.get("original_category")) not in ["Blocker", "Watch Item"]:
		frappe.throw("An accepted risk must retain the original condition category it was raised as.")
