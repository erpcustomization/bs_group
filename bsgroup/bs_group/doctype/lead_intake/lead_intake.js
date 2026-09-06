// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Lead Intake", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.status === "Qualified" && !frm.doc.converted_lead) {
			frm.add_custom_button(__("Convert to Lead"), () => {
				frm.call("convert_to_lead").then((r) => {
					if (r.message) {
						frappe.show_alert({ message: __("Lead {0} created", [r.message]), indicator: "green" });
						frm.reload_doc();
					}
				});
			});
		}

		if (frm.doc.converted_lead) {
			frm.add_custom_button(__("View Lead"), () => {
				frappe.set_route("Form", "Lead", frm.doc.converted_lead);
			});
		}
	},
});
