// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Site Visit", {
	refresh(frm) {
		toggle_completion_reqd(frm);
		check_supply_only_project(frm);
	},
	status(frm) {
		toggle_completion_reqd(frm);
	},
	presales_request(frm){
		fetch_presales_customer(frm);
	},
	project(frm) {
		check_supply_only_project(frm);
	}
});

function check_supply_only_project(frm) {
	if (!frm.doc.project) return;

	// Check once per Project value - refresh fires again after every save,
	// and re-fetching/re-setting the same intro each time is pointless noise.
	if (frm.__supply_checked_for === frm.doc.project) return;
	frm.__supply_checked_for = frm.doc.project;

	frappe.db.get_value("Project", frm.doc.project, "project_type").then((r) => {
		if (r.message && r.message.project_type === "Supply") {
			frm.set_intro(
				__("This Project's Type is Supply. A Site Visit is not required for a Supply-only Project."),
				"orange"
			);
		}
	});
}

function toggle_completion_reqd(frm) {
	let is_completed = frm.doc.status === "Completed";
	frm.toggle_reqd("findings", is_completed);
	frm.toggle_reqd("visit_result", is_completed);
}

function fetch_presales_customer(frm) {

    if (!frm.doc.presales_request) {
        frm.set_value("customer", "");
        return;
    }

    frappe.db.get_value(
        "Presales Request",
        frm.doc.presales_request,
        "customer"
    ).then(r => {

        if (r.message && r.message.customer) {
            frm.set_value("customer", r.message.customer);
        } else {
            frm.set_value("customer", "");
        }

    });
}
