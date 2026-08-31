// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.query_reports["Weekly Project Governance Report"] = {
	onload(report) {
		const $colorful = $('<div class="wpg-colorful-wrapper"></div>')
			.hide()
			.insertBefore(report.$report);

		let showing_colorful = false;

		const fetch_and_render = () => {
			const values = report.get_values();
			if (!values.from_date || !values.to_date) {
				frappe.msgprint(__("Set From Date and To Date first"));
				return;
			}

			$colorful.html(`<div class="text-muted" style="padding: 20px;">${__("Loading...")}</div>`);

			frappe.call({
				method:
					"bsgroup.bs_group.report.weekly_project_governance_report.weekly_project_governance_report.get_colorful_html",
				args: {
					from_date: values.from_date,
					to_date: values.to_date,
					project: values.project,
					category: values.category,
				},
				callback(r) {
					$colorful.html(r.message || "");
				},
			});
		};

		const $btn = report.page.add_inner_button(__("Colorful View"), () => {
			showing_colorful = !showing_colorful;

			if (showing_colorful) {
				report.$report.hide();
				$colorful.show();
				fetch_and_render();
				$btn.text(__("Table View"));
			} else {
				$colorful.hide();
				report.$report.show();
				$btn.text(__("Colorful View"));
			}
		});

		// Filters changed while the colourful view is open - keep it in sync.
		report.page.wrapper.on("change", ".report-filters input, .report-filters select", () => {
			if (showing_colorful) fetch_and_render();
		});
	},
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "category",
			label: __("Category"),
			fieldtype: "Select",
			options: [
				"",
				"Created",
				"Completed",
				"Untouched",
				"Overdue",
				"Blocked",
				"Missing Timesheet",
				"Requires Action",
			].join("\n"),
		},
	],
};
