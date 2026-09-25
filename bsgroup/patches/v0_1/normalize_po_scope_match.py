"""Normalise legacy ASCII-hyphen PO scope-match values to the canonical en-dash options.

Before this patch ``dcs_po_reconcile`` wrote ``"Mismatch - Different Scope"`` (and
``"Mismatch - Superseded"``) with an ASCII hyphen, while the ``custom_po_scope_match``
Select field only offers the en-dash spellings. Any sheet carrying the hyphen value
failed validation on its next full save. This patch rewrites those rows in place.

Idempotent: a second run finds nothing to change. It never touches any other field,
never writes a Governance Event (this is a data-format repair, not a commercial action),
and never runs the party backfill.
"""

import frappe

EN_DASH = "–"

# ASCII-hyphen legacy value  ->  canonical Select option
MAP = {
	"Mismatch - Different Scope": "Mismatch " + EN_DASH + " Different Scope",
	"Mismatch - Superseded": "Mismatch " + EN_DASH + " Superseded",
}


def execute():
	if not frappe.db.table_exists("Deal Cost Sheet"):
		return
	if not frappe.db.has_column("Deal Cost Sheet", "custom_po_scope_match"):
		return
	# The patch handler commits after execute(); no explicit commit here, so the
	# function is also safe to call inside a test transaction.
	for legacy, canonical in MAP.items():
		if frappe.db.count("Deal Cost Sheet", {"custom_po_scope_match": legacy}):
			frappe.db.sql(
				"update `tabDeal Cost Sheet` set custom_po_scope_match=%s where custom_po_scope_match=%s",
				(canonical, legacy),
			)
