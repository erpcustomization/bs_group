"""H-1: back-fill the party model on existing Presales Requests and Deal Cost
Sheets (A-5 / A-6), idempotently, with a dry-run report by default.

For every record the party is resolved in this order:

1. the linked Opportunity's ``opportunity_from`` / ``party_name`` (Lead or
   Customer) - the authoritative source the document was raised from;
2. otherwise the existing ``customer`` value when it names a real Customer;
3. otherwise the record stays *unresolved*: the historical ``customer`` text
   is preserved in ``organisation_name`` and the party fields are left blank
   for a human to complete. Nothing is invented.

``customer`` ends up equal to the party when the party is a Customer and
NULL otherwise, which is exactly the invariant the controllers enforce from
now on. Writes bypass document hooks (``frappe.db.set_value``,
``update_modified=False``) so no sync, notification or governance side effect
fires for a historical correction.

Modes
-----
* dry run (default): nothing is written; a CSV of every proposed change is
  saved under the site's private files and a summary is logged to Error Log
  ``BSG-REL-1``. This is what runs on an ordinary ``bench migrate``.
* apply: set ``bsg_apply_party_backfill: 1`` in site config, or run
  ``bench --site <site> execute bsgroup.patches.v0_1.backfill_party_fields.execute --kwargs '{"apply": true}'``.
  Re-running after a successful apply changes nothing (idempotent).
"""

import csv
import os
from datetime import datetime

import frappe

from bsgroup.utils.party import organisation_name_for, party_from_opportunity

LOG_TITLE = "BSG-REL-1"
TARGETS = ("Presales Request", "Deal Cost Sheet")


def _proposal(doctype, row):
	old_customer = row.get("customer") or ""
	pt, p = party_from_opportunity(row.get("opportunity"))
	source = "opportunity"
	if not pt:
		if old_customer and frappe.db.exists("Customer", old_customer):
			pt, p, source = "Customer", old_customer, "customer_link"
		else:
			pt, p, source = None, None, "unresolved"

	if pt:
		org = organisation_name_for(pt, p)
		new_customer = p if pt == "Customer" else None
	else:
		org = row.get("organisation_name") or old_customer
		new_customer = old_customer if (old_customer and frappe.db.exists("Customer", old_customer)) else None

	values = {
		"party_type": pt,
		"party": p,
		"organisation_name": org or None,
		"customer": new_customer,
	}
	current = {k: (row.get(k) or None) for k in values}
	changed = {k: v for k, v in values.items() if (v or None) != current[k]}
	return {
		"doctype": doctype,
		"name": row["name"],
		"docstatus": row.get("docstatus"),
		"opportunity": row.get("opportunity") or "",
		"source": source,
		"old_customer": old_customer,
		"party_type": pt or "",
		"party": p or "",
		"organisation_name": org or "",
		"new_customer": new_customer or "",
		"customer_cleared": 1 if (old_customer and not new_customer) else 0,
		"changed_fields": ";".join(sorted(changed)),
		"_changed": changed,
	}


def execute(apply=None):
	if apply is None:
		apply = bool(frappe.utils.cint(frappe.conf.get("bsg_apply_party_backfill")))
	mode = "apply" if apply else "dry-run"

	proposals = []
	for doctype in TARGETS:
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if not meta.has_field("party_type"):
			frappe.log_error(title=LOG_TITLE, message=f"party backfill: {doctype} has no party_type field yet; skipped")
			continue
		rows = frappe.get_all(
			doctype,
			fields=["name", "docstatus", "opportunity", "customer", "party_type", "party", "organisation_name"],
			order_by="name",
			limit_page_length=0,
		)
		for row in rows:
			proposals.append(_proposal(doctype, row))

	applied = 0
	if apply:
		for pr in proposals:
			if pr["_changed"]:
				frappe.db.set_value(pr["doctype"], pr["name"], pr["_changed"], update_modified=False)
				applied += 1

	# ---- report -------------------------------------------------------------
	stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
	folder = frappe.get_site_path("private", "files")
	os.makedirs(folder, exist_ok=True)
	path = os.path.join(folder, f"bsg-rel-1-party-backfill-{mode}-{stamp}.csv")
	cols = [
		"doctype", "name", "docstatus", "opportunity", "source", "old_customer", "party_type", "party",
		"organisation_name", "new_customer", "customer_cleared", "changed_fields",
	]
	with open(path, "w", newline="") as f:
		w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
		w.writeheader()
		for pr in proposals:
			w.writerow(pr)

	summary = {
		"mode": mode,
		"records": len(proposals),
		"would_change": sum(1 for p in proposals if p["_changed"]),
		"applied": applied,
		"by_source": {s: sum(1 for p in proposals if p["source"] == s) for s in ("opportunity", "customer_link", "unresolved")},
		"customer_cleared": sum(p["customer_cleared"] for p in proposals),
		"report": path,
	}
	frappe.log_error(title=LOG_TITLE, message="party backfill summary\n" + frappe.as_json(summary))
	return summary
