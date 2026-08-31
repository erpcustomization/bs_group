// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Project Cost Baseline", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status === "Approved") {
			frm.dashboard.set_headline(
				__("Approved baseline. Amount, Project and DCS are locked - use Amend to revise.")
			);
		}
	},
});
