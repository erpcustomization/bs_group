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
	frequency: generate_ppm_schedule,
	contract_start_date: generate_ppm_schedule,
});

function generate_ppm_schedule(frm) {
	// PPM Visit Schedule fields: visit_date, assigned_engineer, status
	// (Scheduled\nCompleted\nMissed) - no visit_label/planned_date/"Planned".
	const map = { 'Monthly': 12, 'Quarterly': 4, 'Half-Yearly': 2, 'Yearly': 1 };
	const n = map[frm.doc.frequency];
	if (!n || !frm.doc.contract_start_date) return;
	const step = 12 / n; // months between visits
	frm.clear_table('ppm_schedule');
	for (let i = 0; i < n; i++) {
		const d = frappe.datetime.add_months(frm.doc.contract_start_date, step * (i + 1));
		const row = frm.add_child('ppm_schedule');
		row.visit_date = d;
		row.assigned_engineer = frm.doc.assigned_engineer;
		row.status = 'Scheduled';
	}
	frm.refresh_field('ppm_schedule');
}
