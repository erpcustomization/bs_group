// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Checkin Report"] = {
	filters: [
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
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
			fieldname: "checkin_status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nPresent\nHalf Day\nAbsent\nWeekend\nHoliday",
		},
	],

	after_datatable_render() {
		render_summary_cards(frappe.query_report);
	},
};

const CARD_COLORS = {
	blue:  { bg: "#e8f4fd", border: "#2490ef", text: "#2490ef" },
	green: { bg: "#e9f9ef", border: "#28a745", text: "#28a745" },
	red:   { bg: "#fdecea", border: "#e24c4c", text: "#e24c4c" },
};

function render_summary_cards(report) {
	const summary = report.data && report.data.report_summary;
	if (!summary || !summary.length) return;

	const main = $(report.page.main);
	if (!main.find(".ec-summary-cards").length) {
		main.find(".frappe-card, .datatable").first()
			.before('<div class="ec-summary-cards"></div>');
	}

	const container = main.find(".ec-summary-cards");
	container.css({ display: "flex", gap: "16px", padding: "16px 0 12px", flexWrap: "wrap" });

	container.html(
		summary.map((item) => {
			const c = CARD_COLORS[item.indicator] || CARD_COLORS.blue;
			return `
			<div class="ec-card"
				style="
					background:${c.bg};
					border:2px solid ${c.border};
					border-radius:10px;
					padding:18px 32px;
					min-width:180px;
					flex:1;
					text-align:center;
				">
				<div style="font-size:2rem;font-weight:700;color:${c.text}">${item.value}</div>
				<div style="font-size:.875rem;color:#555;margin-top:4px">${__(item.label)}</div>
			</div>`;
		}).join("")
	);
}
