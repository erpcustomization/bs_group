"""Pre-model-sync (rel-1, Step 4): reconcile the Custom-vs-standard collision on
``DCS Handover Condition`` without touching a single data row.

On production the DocType was created from the Desk as a Custom DocType
(``custom = 1``, ``module = Custom``) before the app gained the same DocType
under ``bsgroup/bs_group/doctype/dcs_handover_condition``. While ``custom = 1``
Frappe resolves the controller to the generic ``Document`` class, so the app
guards never run and the Server Script guards are the only control.

This patch runs *before* DocTypes are synced from the app. It:

1. proves the deployed schema is compatible with the committed JSON (every
   committed field exists in the database with the same fieldtype, and every
   committed data field has a real column). Any discrepancy raises and aborts
   the migration - nothing has been changed at that point;
2. records the data snapshot (row count, row names) for the post-sync check;
3. flips ``custom -> 0`` and ``module -> BS Group`` on the DocType record and
   clears ``modified``/``migration_hash`` so the app JSON is imported by the
   sync that follows, replacing DocFields/DocPerms in place. The table itself
   is never dropped or recreated (``import_doc`` deletes ``for_reload``).

Idempotent: a site where the DocType is already standard is left alone.
"""

import json
import os

import frappe

DOCTYPE = "DCS Handover Condition"
LOG_TITLE = "BSG-REL-1"
LAYOUT_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold", "Heading"}


def _committed_json():
	path = os.path.join(
		frappe.get_app_path("bsgroup"), "bs_group", "doctype", "dcs_handover_condition", "dcs_handover_condition.json"
	)
	with open(path) as f:
		return json.load(f)


def _log(message, snapshot=None):
	frappe.log_error(title=LOG_TITLE, message=message + ("\n" + json.dumps(snapshot, default=str) if snapshot else ""))


def execute():
	row = frappe.db.get_value("DocType", DOCTYPE, ["name", "custom", "module", "modified"], as_dict=True)
	if not row:
		_log(f"{DOCTYPE}: DocType absent on this site; the sync will create it from the app JSON.")
		return
	if not frappe.utils.cint(row.custom) and row.module == "BS Group":
		_log(f"{DOCTYPE}: already a standard BS Group DocType; nothing to reconcile.")
		return

	committed = _committed_json()
	db_fields = {
		f.fieldname: f
		for f in frappe.get_all(
			"DocField", filters={"parent": DOCTYPE, "parenttype": "DocType"},
			fields=["fieldname", "fieldtype", "options", "reqd", "permlevel"],
		)
	}
	columns = set(frappe.db.get_table_columns(DOCTYPE))

	problems = []
	for f in committed["fields"]:
		fn, ft = f["fieldname"], f["fieldtype"]
		dbf = db_fields.get(fn)
		if dbf is None:
			problems.append(f"committed field '{fn}' ({ft}) is not on the deployed DocType")
			continue
		if dbf.fieldtype != ft:
			problems.append(f"field '{fn}': deployed fieldtype {dbf.fieldtype} != committed {ft}")
		if ft not in LAYOUT_TYPES and fn not in columns:
			problems.append(f"field '{fn}': no column in `tab{DOCTYPE}`")
	extra = sorted(set(db_fields) - {f["fieldname"] for f in committed["fields"]})
	if extra:
		# A deployed field the app does not know would disappear from the form
		# after sync (its column stays). That is data hidden, not lost, but it
		# is still outside the reconciliation this release was tested for.
		problems.append("deployed fields not in the committed JSON: " + ", ".join(extra))

	snapshot = {
		"doctype_row": row,
		"row_count": frappe.db.count(DOCTYPE),
		"names": [d.name for d in frappe.get_all(DOCTYPE, fields=["name"], order_by="name", limit_page_length=0)],
		"columns": sorted(columns),
		"deployed_fields": sorted(db_fields),
		"problems": problems,
	}
	frappe.flags.bsg_handover_snapshot = snapshot

	if problems:
		_log(f"{DOCTYPE}: reconciliation ABORTED - schema mismatch; no change made.", snapshot)
		frappe.throw(
			f"{DOCTYPE}: the deployed schema does not match the committed JSON; migration aborted "
			"before any change (see Error Log 'BSG-REL-1'): " + "; ".join(problems)
		)

	_log(f"{DOCTYPE}: pre-sync snapshot taken; flipping custom->0, module->BS Group.", snapshot)

	values = {"custom": 0, "module": "BS Group", "modified": "2000-01-01 00:00:00"}
	if "migration_hash" in frappe.db.get_table_columns("DocType"):
		values["migration_hash"] = None
	frappe.db.set_value("DocType", DOCTYPE, values, update_modified=False)
	frappe.clear_cache(doctype=DOCTYPE)
