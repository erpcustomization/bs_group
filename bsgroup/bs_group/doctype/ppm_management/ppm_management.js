// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("PPM Management", {
	refresh(frm) {
		if (frm.is_new()) return;

		const scheduled = (frm.doc.ppm_schedule || []).filter((row) => row.status !== "Completed");

		frm.add_custom_button(__("Service Report"), () => {
			let visit_date = scheduled.length ? scheduled[0].visit_date : frm.doc.next_ppm_date;

			frappe.new_doc("Service Report", {
				source: "PPM Visit",
				ppm_management: frm.doc.name,
				ppm_visit_date: visit_date,
				engineer: frm.doc.assigned_engineer,
			});
		}, __("Create"));
	},
});
