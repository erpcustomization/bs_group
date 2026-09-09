// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

// Adds a "Create Service Report" button to the standard Desk HD Ticket form only.
// The Frappe Helpdesk portal (/helpdesk) is a separate Vue frontend that does not
// load Desk client scripts, so this intentionally does not appear there.

frappe.ui.form.on("HD Ticket", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Service Report"), () => {
			frappe.new_doc("Service Report", {
				source: "HD Ticket",
				ticket: frm.doc.name,
			});
		}, __("Create"));
	},

	raised_by(frm) {
		if (frm.doc.customer) return;

		frappe.call({
			method: "bsgroup.utils.hd_ticket.get_customer_by_domain",
			args: { email: frm.doc.raised_by },
			callback(r) {
				if (r.message && !frm.doc.customer) {
					frm.set_value("customer", r.message);
				}
			},
		});
	},
});
