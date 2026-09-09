frappe.listview_settings["PPM Management"] = {
	add_fields: ["status", "next_ppm_date", "assigned_engineer", "project"],
	get_indicator: function(doc) {
		var color_map = {"Scheduled": "blue", "Upcoming": "yellow", "Overdue": "red", "Completed": "green"};
		return [doc.status, color_map[doc.status] || "gray", "status,=," + doc.status];
	},
	onload: function(listview) {
		ppm_render_kpi_bar(listview);
	},
	refresh: function(listview) {
		ppm_render_kpi_bar(listview);
	}
};

frappe.views.calendar["PPM Management"] = {
	field_map: {
		start: "next_ppm_date",
		end: "next_ppm_date",
		id: "name",
		title: "project",
		allDay: "allDay",
		status: "status"
	},
	get_events_method: "bsgroup.bs_group.doctype.ppm_management.ppm_management.ppm_calendar_events",
	get_css_class: function(data) {
		if (data.status === "Overdue") return "danger";
		if (data.status === "Upcoming") return "warning";
		if (data.status === "Completed") return "success";
		return "default";
	},
	order_by: "next_ppm_date"
};

function ppm_render_kpi_bar(listview) {
	if (!listview || listview.doctype !== "PPM Management") return;
	frappe.call({
		method: "frappe.client.get_list",
		args: { doctype: "PPM Management", fields: ["status", "next_ppm_date", "last_completed_on"], limit_page_length: 0 }
	}).then(function(r) {
		listview.__ppm_rows = r.message || [];
		ppm_update_kpi_counts(listview);
		ppm_setup_period_watcher(listview);
	});
}

function ppm_get_period_bounds(listview) {
	try {
		var fc = listview.calendar && listview.calendar.fullCalendar;
		if (fc && fc.view && fc.view.currentStart && fc.view.currentEnd) {
			return { start: fc.view.currentStart, end: fc.view.currentEnd, type: fc.view.type };
		}
	} catch (e) {}
	return null;
}

function ppm_update_kpi_counts(listview) {
	var rows = listview.__ppm_rows || [];
	var bounds = ppm_get_period_bounds(listview);
	var counts = { overdue_period: 0, overdue_carry: 0, upcoming_period: 0, completed_period: 0 };

	rows.forEach(function(d) {
		var due = d.next_ppm_date ? frappe.datetime.str_to_obj(d.next_ppm_date) : null;
		var completedOn = d.last_completed_on ? frappe.datetime.str_to_obj(d.last_completed_on) : null;
		if (d.status === "Overdue") {
			if (bounds && due) {
				if (due >= bounds.start && due < bounds.end) counts.overdue_period++;
				else if (due < bounds.start) counts.overdue_carry++;
			} else {
				counts.overdue_period++;
			}
		} else if (d.status === "Upcoming") {
			if (!bounds || !due || (due >= bounds.start && due < bounds.end)) counts.upcoming_period++;
		} else if (d.status === "Completed") {
			var ref = completedOn || due;
			if (!bounds || !ref || (ref >= bounds.start && ref < bounds.end)) counts.completed_period++;
		}
	});

	var html = ppm_kpi_html(counts, bounds);
	var container = $(listview.page.wrapper).find(".frappe-list").first();
	if (!container.length) return;
	container.find(".ppm-kpi-bar").remove();
	container.prepend(html);
}

function ppm_setup_period_watcher(listview) {
	if (listview.__ppm_observer) return;
	var titleEl = $(listview.page.wrapper).find(".fc-toolbar-title").get(0);
	if (!titleEl) {
		setTimeout(function() { ppm_setup_period_watcher(listview); }, 500);
		return;
	}
	var observer = new MutationObserver(function() {
		setTimeout(function() { ppm_update_kpi_counts(listview); }, 50);
	});
	observer.observe(titleEl, { childList: true, characterData: true, subtree: true });
	listview.__ppm_observer = observer;
}

function ppm_kpi_card(label, value, color) {
	return '<div style="background:#fff;border:1px solid #d1d8dd;border-radius:8px;padding:12px 18px;min-width:130px;">' +
		'<div style="font-size:22px;font-weight:700;color:' + color + ';">' + value + '</div>' +
		'<div style="font-size:11px;color:#8d99a6;text-transform:uppercase;letter-spacing:.5px;margin-top:2px;">' + label + '</div>' +
		'</div>';
}

function ppm_kpi_html(counts, bounds) {
	var period_label = "This Period";
	if (bounds && bounds.type) {
		if (bounds.type.indexOf("Month") > -1) period_label = "This Month";
		else if (bounds.type.indexOf("Week") > -1) period_label = "This Week";
		else if (bounds.type.indexOf("Day") > -1) period_label = "Today";
	}
	return '<div class="ppm-kpi-bar" style="display:flex;gap:12px;flex-wrap:wrap;padding:12px 15px 16px;">' +
		ppm_kpi_card("Overdue (" + period_label + ")", counts.overdue_period, "#e24c4c") +
		ppm_kpi_card("Overdue (Carried Over)", counts.overdue_carry, "#b23c3c") +
		ppm_kpi_card("Upcoming (" + period_label + ")", counts.upcoming_period, "#e8a53d") +
		ppm_kpi_card("Completed (" + period_label + ")", counts.completed_period, "#36a86f") +
		'</div>';
}
