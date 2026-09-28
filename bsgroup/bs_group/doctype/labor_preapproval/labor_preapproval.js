// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Labor Preapproval", {
	onload(frm) {
		set_reference_label(frm);
	},
	refresh(frm) {
		set_reference_label(frm);
		render_summary_html(frm);
		render_line_items_summary(frm);
		check_supply_only_project(frm);

		if (frm.doc.docstatus === 1 && frm.doc.workflow_state === "Approved") {
			frm.add_custom_button(__("Create Attendance"), () => open_bulk_attendance_dialog(frm));
		}
	},
	labor_line_items_add(frm) {
		render_line_items_summary(frm);
	},
	labor_line_items_remove(frm) {
		render_line_items_summary(frm);
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
	role__skill(frm) {
		render_line_items_summary(frm);
	},
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
	render_line_items_summary(frm);
}

function get_form_currency(frm) {
	if (typeof erpnext !== "undefined" && erpnext.get_currency) {
		try {
			const currency = erpnext.get_currency(frm.doc.company);
			if (currency) return currency;
		} catch (e) {
			// fall through to the system default
		}
	}
	return (frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency) || "";
}

function render_line_items_summary(frm) {
	// Companion to the Labor Line Item grid, rendered into labor_lines_summary_html:
	// a prominent Total Labor Cost / Persons / Person-Days strip at every width, plus a
	// one-card-per-row list that CSS shows only on phones, where the grid truncates.
	// Figures are recomputed from the rows so they track unsaved edits; the server's
	// calculate_totals() remains authoritative on save and uses the same formula.
	const field = frm.fields_dict.labor_lines_summary_html;
	if (!field || !field.$wrapper) return;

	const rows = (frm.doc.labor_line_items || []).filter(
		(r) => r.role__skill || r.no_of_persons || r.days || r.rate
	);
	if (!rows.length) {
		field.$wrapper.html(
			`<div class="lpre-lines-summary"><div class="lpre-empty">${__(
				"Add Labor Line Items to see the labor cost summary."
			)}</div></div>`
		);
		return;
	}

	const currency = get_form_currency(frm);
	const esc = frappe.utils.escape_html;
	const money = (value) => format_currency(flt(value), currency, 2);

	let total_persons = 0;
	let person_days = 0;
	let total_cost = 0;

	const cards = rows.map((r) => {
		const persons = cint(r.no_of_persons);
		const days = cint(r.days);
		const rate = flt(r.rate);
		const total = persons * days * rate;

		total_persons += persons;
		person_days += persons * days;
		total_cost += total;

		return `
			<div class="lpre-line">
				<div class="lpre-line-head">
					<span class="lpre-line-idx">#${cint(r.idx)}</span>
					<span class="lpre-line-role">${esc(r.role__skill || __("Role / Skill not set"))}</span>
					<span class="lpre-line-total">${money(total)}</span>
				</div>
				<div class="lpre-line-meta">
					<div><span class="lpre-line-label">${__("Persons")}</span><span class="lpre-line-value">${persons}</span></div>
					<div><span class="lpre-line-label">${__("Days")}</span><span class="lpre-line-value">${days}</span></div>
					<div><span class="lpre-line-label">${__("Rate / Day")}</span><span class="lpre-line-value">${money(rate)}</span></div>
				</div>
			</div>`;
	});

	field.$wrapper.html(`
		<div class="lpre-lines-summary">
			<div class="lpre-summary-row">
				<div class="lpre-total-card">
					<div class="lpre-total-label">${__("Total Labor Cost")}</div>
					<div class="lpre-total-value">${money(total_cost)}</div>
				</div>
				<div class="lpre-chips">
					<div class="lpre-chip">
						<span class="lpre-chip-value">${total_persons}</span>
						<span class="lpre-chip-label">${__("Persons")}</span>
					</div>
					<div class="lpre-chip">
						<span class="lpre-chip-value">${person_days}</span>
						<span class="lpre-chip-label">${__("Person-Days")}</span>
					</div>
				</div>
			</div>
			<div class="lpre-lines">
				<div class="lpre-lines-title">${__("Labor Line Items")}</div>
				${cards.join("")}
			</div>
		</div>
	`);
}
