"""Let the Deal Cost Sheet DocType JSON own its form layout.

Production carries a ``field_order`` Property Setter on Deal Cost Sheet (created through
Customize Form). Frappe applies that stored order over the JSON, so the five-tab layout
shipped in the JSON would never appear and the new Tab Breaks would be appended at the end.
This patch retires that one setter.

Everything else is left in place: the seven label overrides, the permission-level (permlevel 1)
settings on commercial totals, the summary HTML field and the item/resource cost fields, and
any setter on the child DocTypes. Their current values are written into the same backup file
as release evidence, but they are not modified.

Backup and rollback
    Before deleting, the setter is serialised to
    ``sites/<site>/private/files/dcs_property_setter_backup_<timestamp>.json`` together with
    the inventory of every Property Setter on the DCS DocTypes. To roll back:

        bench --site <site> execute \\
            bsgroup.patches.v0_1.dcs_form_layout_property_setters.rollback \\
            --kwargs "{'backup_path': '<that file>'}"

    which re-creates the deleted setter(s) from the file and clears the DocType cache.

Idempotent: a second run finds no ``field_order`` setter and writes nothing.
"""

import json
import os

import frappe
from frappe.utils import now_datetime

DOCTYPES = [
	"Deal Cost Sheet",
	"Deal Cost Item",
	"Additional Charges Item",
	"Deal Cost Resource",
	"Deal Solution Type",
	"Solution Responsibility Detail",
]

RETIRE = [{"doc_type": "Deal Cost Sheet", "doctype_or_field": "DocType", "property": "field_order"}]

FIELDS = [
	"name", "doc_type", "doctype_or_field", "field_name", "row_name", "property", "property_type",
	"value", "module", "is_system_generated", "creation", "modified", "modified_by", "owner",
]


def execute():
	if not frappe.db.table_exists("Property Setter"):
		return

	to_delete = []
	for spec in RETIRE:
		to_delete += frappe.get_all("Property Setter", filters=spec, fields=FIELDS)
	if not to_delete:
		return

	inventory = frappe.get_all("Property Setter", filters={"doc_type": ["in", DOCTYPES]}, fields=FIELDS, order_by="doc_type, field_name, property")

	backup = {
		"taken_on": str(now_datetime()),
		"site": frappe.local.site,
		"deleted": to_delete,
		"retained_inventory": inventory,
		"note": "Only entries under 'deleted' were removed. 'retained_inventory' is evidence of what was left untouched.",
	}
	path = frappe.get_site_path("private", "files", "dcs_property_setter_backup_%s.json" % now_datetime().strftime("%Y%m%d_%H%M%S"))
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		json.dump(backup, f, indent=1, default=str)

	for ps in to_delete:
		frappe.delete_doc("Property Setter", ps["name"], force=True, ignore_permissions=True)

	for dt in DOCTYPES:
		frappe.clear_cache(doctype=dt)

	frappe.logger("bsgroup").info("dcs_form_layout_property_setters: deleted %s; backup at %s" % ([p["name"] for p in to_delete], path))
	print("dcs_form_layout_property_setters: deleted %d Property Setter(s); backup at %s" % (len(to_delete), path))


def rollback(backup_path):
	"""Re-create the Property Setters listed under 'deleted' in the backup file."""
	with open(backup_path) as f:
		backup = json.load(f)
	restored = []
	for ps in backup.get("deleted", []):
		if frappe.db.exists("Property Setter", ps["name"]):
			continue
		doc = frappe.get_doc({
			"doctype": "Property Setter",
			"doctype_or_field": ps["doctype_or_field"],
			"doc_type": ps["doc_type"],
			"field_name": ps.get("field_name"),
			"row_name": ps.get("row_name"),
			"property": ps["property"],
			"property_type": ps.get("property_type"),
			"value": ps.get("value"),
			"module": ps.get("module"),
			"is_system_generated": ps.get("is_system_generated") or 0,
		})
		doc.flags.ignore_permissions = True
		doc.insert()
		restored.append(doc.name)
	for dt in DOCTYPES:
		frappe.clear_cache(doctype=dt)
	frappe.db.commit()
	print("rollback: restored %s" % restored)
	return restored
