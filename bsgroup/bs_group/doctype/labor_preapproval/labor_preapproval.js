// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Labor Preapproval", {
	onload(frm) {
		set_reference_label(frm);
	},
	refresh(frm) {
		set_reference_label(frm);
		render_summary_html(frm);
		check_supply_only_project(frm);

		if (frm.doc.docstatus === 1 && frm.doc.workflow_state === "Approved") {
			frm.add_custom_button(__("Create Attendance"), () => open_bulk_attendance_dialog(frm));
		}
	},
	source(frm) {
		frm.set_value("reference", "");
		frm.set_value("task", "");
		set_reference_label(frm);
	},
	reference(frm) {
		if (frm.doc.source === "Project" && frm.doc.reference) {
			frm.set_value("task", "");
		}
		set_reference_label(frm);
		check_supply_only_project(frm);
	},
});

function check_supply_only_project(frm) {
	if (frm.doc.source !== "Project" || !frm.doc.reference) return;

	// Check once per reference value - refresh fires again after every save,
	// and re-fetching/re-setting the same intro each time is pointless noise.
	if (frm.__supply_checked_for === frm.doc.reference) return;
	frm.__supply_checked_for = frm.doc.reference;

	frappe.db.get_value("Project", frm.doc.reference, "project_type").then((r) => {
		if (r.message && r.message.project_type === "Supply") {
			frm.set_intro(
				__("This Project's Type is Supply. Labor Preapproval is not required for a Supply-only Project."),
				"orange"
			);
		}
	});
}

frappe.ui.form.on("Labor Line Item", {
	no_of_persons(frm, cdt, cdn) {
		recalculate_row(frm, cdt, cdn);
	},
	days(frm, cdt, cdn) {
		recalculate_row(frm, cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		recalculate_row(frm, cdt, cdn);
	},
});

function open_bulk_attendance_dialog(frm) {
	const approved_skills = (frm.doc.labor_line_items || []).map((row) => row.role__skill).filter(Boolean);

	const dialog = new frappe.ui.Dialog({
		title: __("Create Attendance for Multiple Labourers"),
		fields: [
			{
				fieldname: "labourers",
				fieldtype: "MultiSelectList",
				label: __("Labourers"),
				reqd: 1,
				get_data: function (txt) {
					return frappe.db.get_link_options("Labour Name", txt, {
						is_active: 1,
						labour_type: ["in", approved_skills.length ? approved_skills : undefined],
					});
				},
			},
			{ fieldname: "col_br_1", fieldtype: "Column Break" },
			{
				fieldname: "check_in_time",
				fieldtype: "Datetime",
				label: __("Check-In Time"),
				reqd: 1,
				default: frappe.datetime.now_datetime(),
			},
			{ fieldname: "check_out_time", fieldtype: "Datetime", label: __("Check-Out Time") },
			{ fieldname: "sec_br_1", fieldtype: "Section Break" },
			{ fieldname: "site_location", fieldtype: "Data", label: __("Site Location") },
			{
				fieldname: "submit_immediately",
				fieldtype: "Check",
				label: __("Submit Immediately"),
				default: 1,
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			dialog.hide();
			frappe.call({
				method: "bsgroup.bs_group.doctype.labor_attendance.labor_attendance.bulk_create",
				args: {
					labor_preapproval: frm.doc.name,
					labourers: values.labourers,
					check_in_time: values.check_in_time,
					check_out_time: values.check_out_time,
					site_location: values.site_location,
					submit: values.submit_immediately ? 1 : 0,
				},
				freeze: true,
				freeze_message: __("Creating Attendance..."),
				callback(r) {
					const { created = [], errors = [] } = r.message || {};
					if (created.length) {
						frappe.show_alert({
							message: __("Created {0} Attendance record(s)", [created.length]),
							indicator: "green",
						});
					}
					if (errors.length) {
						frappe.msgprint({
							title: __("Some Attendance records could not be created"),
							indicator: "red",
							message: errors.join("<br>"),
						});
					}
					frm.reload_doc();
				},
			});
		},
	});

	dialog.show();
}

function render_summary_html(frm) {
	const wrapper = frm.fields_dict.labor_preapproval_html && frm.fields_dict.labor_preapproval_html.$wrapper;
	if (!wrapper) return;

	if (frm.is_new()) {
		wrapper.html(`<div class="text-muted">${__("Save the Labor Preapproval to see the usage summary.")}</div>`);
		return;
	}

	wrapper.html(`<div class="text-muted">${__("Loading...")}</div>`);

	frappe.call({
		method: "bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval.get_summary_html",
		args: { lpre_name: frm.doc.name },
		callback(r) {
			wrapper.html(r.message || "");
		},
	});
}

function set_reference_label(frm) {
	const label = frm.doc.source === "HD Ticket" ? "HD Ticket" : "Project";
	frm.set_df_property("reference", "label", label);

	frm.set_query("task", () => {
		if (frm.doc.source === "Project" && frm.doc.reference) {
			return { filters: { project: frm.doc.reference } };
		}
		return { filters: { name: ["in", []] } };
	});
}

function recalculate_row(frm, cdt, cdn) {
	// Client-side preview only - the server recalculates authoritative totals on save.
	const row = locals[cdt][cdn];
	const total = (row.no_of_persons || 0) * (row.days || 0) * (row.rate || 0);
	frappe.model.set_value(cdt, cdn, "total_cost", total);
	frm.refresh_field("labor_line_items");
}
