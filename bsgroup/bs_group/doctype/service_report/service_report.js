// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Service Report", {
	source(frm) {
		if (frm.doc.source === "HD Ticket") {
			frm.set_value("ppm_management", null);
			frm.set_value("ppm_visit_date", null);
		} else if (frm.doc.source === "PPM Visit") {
			frm.set_value("ticket", null);
		}
	},
	engineer(frm){
		if (frm.doc.engineer) {
			get_engineer_signature(frm);
		}
	},
	ppm_management(frm) {
		if (!frm.doc.ppm_management) return;

		frm.set_query("ppm_visit_date", () => {
			return {};
		});

		frappe.db.get_doc("PPM Management", frm.doc.ppm_management).then((ppm) => {
			let scheduled = (ppm.ppm_schedule || [])
				.filter((row) => row.status !== "Completed")
				.map((row) => row.visit_date);

			if (scheduled.length) {
				frm.set_value("ppm_visit_date", scheduled[0]);
			}
		});
	},
});

function get_engineer_signature(frm) {
	if (!frm.doc.engineer) {
		frm.set_value("engineer_signature", null);
		return;
	}

	frappe.db.get_list("Engineer Signature", {
		filters: {
			engineer: frm.doc.engineer,
		},
		fields: ["name", "engineer_signature"],
		limit: 1
	}).then(records => {
		if (records.length) {
			frm.set_value(
				"engineer_signature",
				records[0].engineer_signature
			);
		} else {
			frm.set_value("engineer_signature", null);
		}
	});
}