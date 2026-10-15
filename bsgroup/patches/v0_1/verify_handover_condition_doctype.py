"""Post-model-sync (rel-1, Step 4): prove the ``DCS Handover Condition``
reconciliation left the DocType standard, the schema complete and the data
untouched. Any failure raises so the migration is reported as failed and the
deployment is rolled back by the platform.
"""

import json
import os

import frappe

DOCTYPE = "DCS Handover Condition"
LOG_TITLE = "BSG-REL-1"
LAYOUT_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"}


def execute():
	row = frappe.db.get_value("DocType", DOCTYPE, ["custom", "module", "autoname"], as_dict=True)
	failures = []
	if not row:
		failures.append("DocType missing after sync")
	else:
		if frappe.utils.cint(row.custom):
			failures.append("DocType is still custom = 1")
		if row.module != "BS Group":
			failures.append(f"module is '{row.module}', expected 'BS Group'")

	path = os.path.join(
		frappe.get_app_path("bsgroup"), "bs_group", "doctype", "dcs_handover_condition", "dcs_handover_condition.json"
	)
	with open(path) as f:
		committed = json.load(f)
	frappe.clear_cache(doctype=DOCTYPE)
	meta = frappe.get_meta(DOCTYPE, cached=False)
	columns = set(frappe.db.get_table_columns(DOCTYPE))
	for fld in committed["fields"]:
		mf = meta.get_field(fld["fieldname"])
		if mf is None:
			failures.append(f"field '{fld['fieldname']}' missing from meta after sync")
		elif mf.fieldtype != fld["fieldtype"]:
			failures.append(f"field '{fld['fieldname']}' fieldtype {mf.fieldtype} != {fld['fieldtype']}")
		if fld["fieldtype"] not in LAYOUT_TYPES and fld["fieldname"] not in columns:
			failures.append(f"field '{fld['fieldname']}' has no column after sync")
	if (row and row.autoname) != committed.get("autoname"):
		failures.append(f"autoname '{row and row.autoname}' != committed '{committed.get('autoname')}'")

	# Controller must now resolve to the app class so the guards are live.
	from frappe.model.base_document import get_controller
	try:
		ctrl = get_controller(DOCTYPE)
		if ctrl.__name__ != "DCSHandoverCondition":
			failures.append(f"controller resolves to {ctrl.__module__}.{ctrl.__name__}, not DCSHandoverCondition")
	except Exception as e:
		failures.append(f"controller import failed: {e}")

	snap = frappe.flags.get("bsg_handover_snapshot")
	count_after = frappe.db.count(DOCTYPE)
	names_after = [d.name for d in frappe.get_all(DOCTYPE, fields=["name"], order_by="name", limit_page_length=0)]
	if snap:
		if snap["row_count"] != count_after:
			failures.append(f"row count moved {snap['row_count']} -> {count_after}")
		if snap["names"] != names_after:
			failures.append("row names differ from the pre-sync snapshot")
		missing_cols = set(snap["columns"]) - columns
		if missing_cols:
			failures.append("columns lost: " + ", ".join(sorted(missing_cols)))

	report = {"row_count_after": count_after, "failures": failures, "had_snapshot": bool(snap)}
	frappe.log_error(title=LOG_TITLE, message=f"{DOCTYPE}: post-sync verification\n" + json.dumps(report, default=str))
	if failures:
		frappe.throw(f"{DOCTYPE}: post-sync verification failed: " + "; ".join(failures))
