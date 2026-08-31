// ── Dashboard state ────────────────────────────────────────────────────────
const _state = { selected_user: null, user_label: "All Users", from_date: null, to_date: null };

frappe.pages["sales-management-das"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Sales Management Dashboard",
		single_column: true,
	});

	// ── Inject CSS ─────────────────────────────────────────────────────────
	if (!document.getElementById("smd-styles")) {
		const style = document.createElement("style");
		style.id = "smd-styles";
		style.textContent = `
			.smd-wrap {
				padding: 20px 24px;
				background: #f5f7fb;
				min-height: 100vh;
			}
			.smd-header {
				background: linear-gradient(135deg,#1d4ed8,#2563eb 45%,#3b82f6);
				color: #fff;
				border-radius: 20px;
				padding: 24px 28px;
				margin-bottom: 18px;
				display: flex;
				justify-content: space-between;
				align-items: flex-start;
				flex-wrap: wrap;
				gap: 14px;
				box-shadow: 0 10px 25px rgba(15,23,42,0.12);
			}
			.smd-header h1 { margin: 10 0 25px; font-size: 28px; font-weight: 800; color: #fff }
			.smd-header .sub { font-size: 14px; opacity: 0.9; }
			.smd-header-actions {
				display: flex;
				align-items: center;
				gap: 8px;
				flex-wrap: wrap;
			}
			.smd-header .refresh-btn,
			.smd-header .filter-btn {
				background: rgba(255,255,255,0.18);
				border: 1px solid rgba(255,255,255,0.25);
				color: #fff;
				padding: 8px 16px;
				border-radius: 999px;
				cursor: pointer;
				font-size: 13px;
				font-weight: 600;
				transition: background 0.2s;
				white-space: nowrap;
			}
			.smd-header .refresh-btn:hover,
			.smd-header .filter-btn:hover { background: rgba(255,255,255,0.28); }
			.smd-header .filter-btn.active {
				background: rgba(255,255,255,0.35);
				border-color: rgba(255,255,255,0.6);
			}
			.smd-dropdown {
				position: absolute;
				top: calc(100% + 6px);
				right: 0;
				background: #fff;
				border: 1px solid #e5e7eb;
				border-radius: 12px;
				box-shadow: 0 8px 24px rgba(15,23,42,0.12);
				min-width: 220px;
				z-index: 9999;
				overflow: hidden;
			}
			.smd-dropdown-item {
				padding: 10px 16px;
				font-size: 13px;
				color: #374151;
				cursor: pointer;
				transition: background 0.15s;
			}
			.smd-dropdown-item:hover { background: #f0f9ff; color: #1d4ed8; }
			.smd-dropdown-item.selected { background: #dbeafe; color: #1d4ed8; font-weight: 600; }
			.smd-dropdown-divider { border-top: 1px solid #f3f4f6; margin: 4px 0; }
			.smd-dropdown-header {
				padding: 8px 16px 4px;
				font-size: 11px;
				font-weight: 700;
				color: #9ca3af;
				text-transform: uppercase;
				letter-spacing: .05em;
			}
			.smd-grid4 {
				display: grid;
				grid-template-columns: repeat(4,1fr);
				gap: 16px;
				margin-bottom: 16px;
			}
			.smd-grid2 {
				display: grid;
				grid-template-columns: 1.7fr 1.3fr;
				gap: 16px;
				margin-bottom: 16px;
			}
			.smd-card {
				background: #fff;
				border: 1px solid #e5e7eb;
				border-radius: 16px;
				padding: 20px;
				box-shadow: 0 4px 16px rgba(15,23,42,0.06);
			}
			.smd-metric-label { font-size: 13px; color: #6b7280; margin-bottom: 8px; }
			.smd-metric-value {
				font-size: 28px;
				font-weight: 800;
				margin-bottom: 6px;
				color: #1f2937;
			}
			.smd-metric-note { font-size: 12px; color: #9ca3af; }
			.smd-danger { color: #dc2626; }
			.smd-warn   { color: #d97706; }
			.smd-good   { color: #16a34a; }
			.smd-sec-title {
				display: flex;
				justify-content: space-between;
				align-items: center;
				margin-bottom: 16px;
			}
			.smd-sec-title h2 { margin: 0; font-size: 17px; font-weight: 700; }
			.smd-link { color: #2563eb; font-size: 13px; font-weight: 600; text-decoration: none; cursor: pointer; }
			.smd-bar-group { display: grid; gap: 12px; }
			.smd-bar-row {
				display: grid;
				grid-template-columns: 130px 1fr 100px;
				align-items: center;
				gap: 10px;
				font-size: 13px;
			}
			.smd-bar-label { color: #374151; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.smd-bar-track {
				width: 100%;
				height: 12px;
				background: #dbeafe;
				border-radius: 999px;
				overflow: hidden;
			}
			.smd-bar-fill {
				height: 100%;
				background: linear-gradient(90deg,#60a5fa,#2563eb);
				border-radius: 999px;
				transition: width 0.6s ease;
			}
			.smd-bar-val { font-weight: 700; font-size: 12px; text-align: right; color: #1f2937; }
			.smd-table { width: 100%; border-collapse: collapse; font-size: 13px; }
			.smd-table th, .smd-table td {
				padding: 10px 8px;
				border-bottom: 1px solid #f3f4f6;
				text-align: left;
				vertical-align: middle;
			}
			.smd-table th {
				color: #9ca3af;
				font-weight: 700;
				font-size: 11px;
				text-transform: uppercase;
				letter-spacing: 0.05em;
			}
			.smd-table tr:hover td { background: #f9fafb; }
			.smd-badge {
				display: inline-block;
				border-radius: 999px;
				padding: 3px 10px;
				font-size: 11px;
				font-weight: 700;
			}
			.smd-b-red    { background: #fee2e2; color: #b91c1c; }
			.smd-b-yellow { background: #fef3c7; color: #b45309; }
			.smd-b-green  { background: #dcfce7; color: #15803d; }
			.smd-b-blue   { background: #dbeafe; color: #1d4ed8; }
			.smd-b-purple { background: #ede9fe; color: #6d28d9; }
			.smd-b-gray   { background: #f3f4f6; color: #374151; }
			.smd-updates  { display: grid; gap: 10px; }
			.smd-update-item {
				border: 1px solid #e5e7eb;
				border-radius: 12px;
				padding: 12px 14px;
				background: #fbfdff;
			}
			.smd-update-item strong { display: block; margin-bottom: 4px; font-size: 13px; }
			.smd-update-item p { margin: 0 0 4px; font-size: 13px; color: #374151; line-height: 1.4; }
			.smd-update-meta { font-size: 12px; color: #9ca3af; }
			.smd-loading { text-align: center; padding: 60px; color: #9ca3af; font-size: 14px; }
			.smd-opp-link { color: #2563eb; text-decoration: none; font-weight: 600; }
			.smd-opp-link:hover { text-decoration: underline; }
			@media (max-width: 1100px) {
				.smd-grid4 { grid-template-columns: repeat(2,1fr); }
				.smd-grid2 { grid-template-columns: 1fr; }
			}
			@media (max-width: 650px) {
				.smd-grid4 { grid-template-columns: 1fr; }
				.smd-bar-row { grid-template-columns: 100px 1fr 80px; }
			}
		`;
		document.head.appendChild(style);
	}

	// ── Shell HTML ─────────────────────────────────────────────────────────
	$(page.body).html(`
		<div class="smd-wrap">
			<div class="smd-header">
				<div>
					<h1>Sales Management Dashboard</h1>
					<div class="sub" id="smd-subtitle">Loading…</div>
				</div>
				<div class="smd-header-actions">
					<div style="position:relative">
						<button class="filter-btn" id="smd-user-btn">&#128100; All Users</button>
						<div class="smd-dropdown" id="smd-user-dropdown" style="display:none"></div>
					</div>
					<button class="filter-btn" id="smd-date-btn">&#128197; This Month</button>
					<button class="refresh-btn" id="smd-refresh">&#8635; Refresh</button>
				</div>
			</div>
			<div id="smd-body">
				<div class="smd-loading">Loading dashboard data…</div>
			</div>
		</div>
	`);

	// ── User filter button ─────────────────────────────────────────────────
	$("#smd-user-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#smd-user-dropdown");
		if ($dd.is(":visible")) { $dd.hide(); return; }

		$dd.html('<div class="smd-dropdown-item" style="color:#9ca3af">Loading…</div>').show();

		frappe.call({
			method: "bsgroup.bs_group.page.sales_management_das.sales_management_das.get_sales_users",
			callback: function (r) {
				const users = (r.message || []);
				if (!users.length) {
					$dd.html('<div class="smd-dropdown-item" style="color:#9ca3af">No other users found</div>');
					return;
				}
				let html = '<div class="smd-dropdown-header">Filter by Owner</div>';
				html += `<div class="smd-dropdown-item${!_state.selected_user ? ' selected' : ''}" data-user="">All Users</div>`;
				html += '<div class="smd-dropdown-divider"></div>';
				users.forEach(u => {
					const name  = u.user || "";
					const label = name.split("@")[0].replace(/\./g, " ").replace(/\b\w/g, c => c.toUpperCase());
					const sel   = _state.selected_user === name ? " selected" : "";
					html += `<div class="smd-dropdown-item${sel}" data-user="${name}" title="${name}">${label}</div>`;
				});
				$dd.html(html);
			},
		});
	});

	$(document).on("click", "#smd-user-dropdown .smd-dropdown-item", function () {
		const user  = $(this).data("user") || null;
		const label = $(this).text().trim();
		_state.selected_user = user;
		_state.user_label    = label;
		$("#smd-user-btn").text("👤 " + label).toggleClass("active", !!user);
		$("#smd-user-dropdown").hide();
		load_dashboard();
	});

	// ── Date filter button ─────────────────────────────────────────────────
	$("#smd-date-btn").on("click", function () {
		frappe.prompt(
			[
				{ fieldname: "from_date", label: "From Date", fieldtype: "Date", reqd: 1,
				  default: _state.from_date || frappe.datetime.month_start() },
				{ fieldname: "to_date",   label: "To Date",   fieldtype: "Date", reqd: 1,
				  default: _state.to_date   || frappe.datetime.month_end() },
			],
			function (vals) {
				_state.from_date = vals.from_date;
				_state.to_date   = vals.to_date;
				const label = frappe.datetime.str_to_user(vals.from_date) + " → " + frappe.datetime.str_to_user(vals.to_date);
				$("#smd-date-btn").text("📅 " + label).addClass("active");
				load_dashboard();
			},
			"Select Date Range",
			"Apply"
		);
	});

	// Close user dropdown when clicking outside
	$(document).on("click", function (e) {
		if (!$(e.target).closest("#smd-user-btn, #smd-user-dropdown").length) {
			$("#smd-user-dropdown").hide();
		}
	});

	$("#smd-refresh").on("click", () => load_dashboard());
	load_dashboard();

	// ── TV mode (?tv=1) ────────────────────────────────────────────────────
	if (new URLSearchParams(window.location.search).get("tv") === "1") {
		// Hide Frappe chrome for full-screen display
		document.querySelector(".navbar-expand")?.style.setProperty("display", "none", "important");
		document.querySelector(".layout-side-section")?.style.setProperty("display", "none", "important");
		document.querySelector(".page-head")?.style.setProperty("display", "none", "important");
		document.querySelector(".layout-main-section-wrapper")
			?.style.setProperty("padding", "0", "important");

		if (!document.getElementById("smd-tv-styles")) {
			const tvStyle = document.createElement("style");
			tvStyle.id = "smd-tv-styles";
			tvStyle.textContent = `
				.smd-wrap          { padding: 28px 36px !important; }
				.smd-header        { padding: 28px 36px !important; }
				.smd-header h1     { font-size: clamp(32px, 3vw, 52px) !important; }
				.smd-header .sub   { font-size: 18px !important; }
				.smd-metric-label  { font-size: 16px !important; margin-bottom: 12px !important; }
				.smd-metric-value  { font-size: clamp(64px, 5.5vw, 100px) !important; }
				.smd-metric-note   { font-size: 15px !important; }
				.smd-sec-title h2  { font-size: clamp(22px, 2vw, 30px) !important; }
				.smd-table         { font-size: 17px !important; }
				.smd-table th      { font-size: 13px !important; padding: 10px 12px !important; }
				.smd-table td      { padding: 14px 12px !important; }
				.smd-bar-label     { font-size: 16px !important; }
				.smd-bar-val       { font-size: 16px !important; font-weight: 700 !important; }
				.smd-bar-row       { margin-bottom: 14px !important; }
			`;
			document.head.appendChild(tvStyle);
		}

		// Auto-refresh every 60 seconds
		setInterval(() => load_dashboard(), 60000);
	}
};

// ── Helpers ────────────────────────────────────────────────────────────────
function fmt_aed(val) {
	val = parseFloat(val) || 0;
	if (val >= 1e6) return "AED " + (val / 1e6).toFixed(1) + "M";
	if (val >= 1e3) return "AED " + Math.round(val / 1000) + "K";
	return "AED " + val.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function stage_badge(stage) {
	if (!stage) return "";
	const map = {
		"Prospecting":  "smd-b-gray",
		"Qualification":"smd-b-blue",
		"Needs Analysis":"smd-b-blue",
		"Value Proposition":"smd-b-blue",
		"BOQ":          "smd-b-yellow",
		"Proposal":     "smd-b-yellow",
		"Negotiation":  "smd-b-red",
		"Review":       "smd-b-blue",
		"Approval":     "smd-b-blue",
		"PO":           "smd-b-green",
		"Committed":    "smd-b-green",
	};
	const cls = map[stage] || "smd-b-gray";
	return `<span class="smd-badge ${cls}">${stage}</span>`;
}

function opp_link(name, label) {
	return `<a class="smd-opp-link" href="/app/opportunity/${encodeURIComponent(name)}" target="_blank">${label}</a>`;
}

function bar_rows(items, label_key, val_key, max_val) {
	if (!items || !items.length) return `<div style="color:#9ca3af;font-size:13px">No data</div>`;
	let html = '<div class="smd-bar-group">';
	items.forEach(row => {
		const val   = parseFloat(row[val_key]) || 0;
		const label = row[label_key] || "—";
		const pct   = max_val > 0 ? Math.min(100, (val / max_val) * 100).toFixed(1) : 0;
		html += `
			<div class="smd-bar-row">
				<span class="smd-bar-label" title="${label}">${label}</span>
				<div class="smd-bar-track"><div class="smd-bar-fill" style="width:${pct}%"></div></div>
				<span class="smd-bar-val">${fmt_aed(val)}</span>
			</div>`;
	});
	html += "</div>";
	return html;
}

// ── Main loader ────────────────────────────────────────────────────────────
function load_dashboard() {
	$("#smd-refresh").prop("disabled", true).text("Loading…");
	$("#smd-body").html('<div class="smd-loading">Fetching live data…</div>');

	frappe.call({
		method: "bsgroup.bs_group.page.sales_management_das.sales_management_das.get_dashboard_data",
		args: {
			selected_user: _state.selected_user || null,
			from_date:     _state.from_date     || null,
			to_date:       _state.to_date        || null,
		},
		callback: function (r) {
			$("#smd-refresh").prop("disabled", false).text("⟳ Refresh");
			if (r.exc || !r.message) {
				$("#smd-body").html(
					`<div class="smd-loading" style="color:#dc2626">Failed to load data. Check console for errors.</div>`
				);
				return;
			}
			render_dashboard(r.message);
		},
	});
}

// ── Renderer ───────────────────────────────────────────────────────────────
function render_dashboard(d) {
	const kpis    = d.kpis    || {};
	const now     = d.generated_at || "";
	const filters = d.active_filters || {};

	// Sync user button visibility — hide for non-managers
	if (!d.is_manager) {
		$("#smd-user-btn").hide();
	}

	// Update closing section title based on active date range
	const closing_label = filters.is_custom_date
		? `Deals Closing ${frappe.datetime.str_to_user(filters.from_date)} – ${frappe.datetime.str_to_user(filters.to_date)}`
		: "Deals Closing This Month";

	$("#smd-subtitle").text("BS Group · ERPNext CRM · " + now);

	// ── KPI Cards ──────────────────────────────────────────────────────────
	const kpi_html = `
	<div class="smd-grid4">
		<div class="smd-card">
			<div class="smd-metric-label">Total Pipeline</div>
			<div class="smd-metric-value">${fmt_aed(kpis.total_pipeline)}</div>
			<div class="smd-metric-note">Open opportunities across all active stages</div>
		</div>
		<div class="smd-card">
			<div class="smd-metric-label">Closing This Month</div>
			<div class="smd-metric-value smd-good">${fmt_aed(kpis.closing_month)}</div>
			<div class="smd-metric-note">Expected closures based on closing date</div>
		</div>
		<div class="smd-card">
			<div class="smd-metric-label">Overdue Follow-ups</div>
			<div class="smd-metric-value smd-danger">${kpis.overdue_count} Deals</div>
			<div class="smd-metric-note">Next action date has already passed</div>
		</div>
		<div class="smd-card">
			<div class="smd-metric-label">No Updates in 7 Days</div>
			<div class="smd-metric-value smd-warn">${kpis.no_update_count} Deals</div>
			<div class="smd-metric-note">Needs review from owner or manager</div>
		</div>
	</div>`;

	// ── Pipeline by Stage + Owner ──────────────────────────────────────────
	const stage_items = d.pipeline_by_stage || [];
	const owner_items = d.owner_pipeline   || [];
	const stage_max   = stage_items.length ? Math.max(...stage_items.map(x => x.amount)) : 1;
	const owner_max   = owner_items.length ? Math.max(...owner_items.map(x => x.amount)) : 1;

	const charts_html = `
	<div class="smd-grid2">
		<div class="smd-card">
			<div class="smd-sec-title">
				<h2>Pipeline by Stage</h2>
				<a class="smd-link" href="/app/opportunity?sales_stage=&status=Open" target="_blank">Open report</a>
			</div>
			${bar_rows(stage_items, "sales_stage", "amount", stage_max)}
		</div>
		<div class="smd-card">
			<div class="smd-sec-title">
				<h2>Owner-wise Pipeline</h2>
				<a class="smd-link" href="/app/opportunity" target="_blank">View all</a>
			</div>
			${bar_rows(owner_items.map(r => ({ ...r, label: r.owner_short })), "label", "amount", owner_max)}
		</div>
	</div>`;

	// ── Overdue Table ──────────────────────────────────────────────────────
	let overdue_rows = "";
	(d.overdue_list || []).forEach(row => {
		overdue_rows += `<tr>
			<td>${opp_link(row.name, row.display_name)}</td>
			<td>${stage_badge(row.sales_stage)}</td>
			<td style="color:#374151;max-width:160px">${row.custom_next_action || "—"}</td>
			<td><span style="color:#dc2626;font-weight:600">${row.due_display || "—"}</span></td>
		</tr>`;
	});
	if (!overdue_rows) overdue_rows = `<tr><td colspan="4" style="color:#9ca3af;text-align:center;padding:20px">No overdue follow-ups</td></tr>`;

	// ── Closing This Month Table ───────────────────────────────────────────
	let closing_rows = "";
	(d.closing_list || []).forEach(row => {
		const prob = row.probability ? `${row.probability}%` : "—";
		closing_rows += `<tr>
			<td>${opp_link(row.name, row.display_name)}</td>
			<td style="font-weight:700">${fmt_aed(row.opportunity_amount)}</td>
			<td>${stage_badge(row.sales_stage)}</td>
			<td><span style="font-weight:600;color:#16a34a">${prob}</span></td>
		</tr>`;
	});
	if (!closing_rows) closing_rows = `<tr><td colspan="4" style="color:#9ca3af;text-align:center;padding:20px">No deals closing this month</td></tr>`;

	const tables_html = `
	<div class="smd-grid2">
		<div class="smd-card">
			<div class="smd-sec-title">
				<h2>Overdue Follow-ups</h2>
				<a class="smd-link" href="/app/opportunity?custom_next_action_date=Today" target="_blank">See all</a>
			</div>
			<table class="smd-table">
				<thead><tr><th>Customer</th><th>Stage</th><th>Next Action</th><th>Due</th></tr></thead>
				<tbody>${overdue_rows}</tbody>
			</table>
		</div>
		<div class="smd-card">
			<div class="smd-sec-title">
				<h2>${closing_label}</h2>
				<a class="smd-link" href="/app/opportunity" target="_blank">View all</a>
			</div>
			<table class="smd-table">
				<thead><tr><th>Customer</th><th>Value</th><th>Stage</th><th>Prob.</th></tr></thead>
				<tbody>${closing_rows}</tbody>
			</table>
		</div>
	</div>`;

	// ── Updates ────────────────────────────────────────────────────────────
	let updates_html = "";
	(d.updates_list || []).forEach(row => {

		let owner_short = row.owner ? row.owner.split("@")[0] : "Unknown";

		let when = row.custom_last_update_date
			? frappe.datetime.prettyDate(row.custom_last_update_date)
			: "";

		updates_html += `
		<div class="smd-update-item">
			<strong>${opp_link(row.name, row.title)}</strong>
			<p>${row.custom_last_sales_update || ""}</p>
			<div class="smd-update-meta">
				Owner: ${owner_short} · Updated ${when}
			</div>
		</div>`;
	});
	if (!updates_html) updates_html = `<div style="color:#9ca3af;font-size:13px">No recent updates found.</div>`;

	// ── Stuck Deals ────────────────────────────────────────────────────────
	let stuck_rows = "";
	(d.stuck_list || []).forEach(row => {
		const days = row.custom_stage_age_days || "—";
		const color = days > 30 ? "#dc2626" : days > 20 ? "#d97706" : "#374151";
		stuck_rows += `<tr>
			<td>${opp_link(row.name, row.display_name)}</td>
			<td>${stage_badge(row.sales_stage)}</td>
			<td style="font-weight:700;color:${color}">${days}</td>
			<td style="color:#6b7280">${row.owner_short}</td>
		</tr>`;
	});
	if (!stuck_rows) stuck_rows = `<tr><td colspan="4" style="color:#9ca3af;text-align:center;padding:20px">No stuck deals</td></tr>`;

	const bottom_html = `
	<div class="smd-grid2">
		<div class="smd-card">
			<div class="smd-sec-title">
				<h2>Latest Sales Updates</h2>
				<a class="smd-link" href="/app/opportunity" target="_blank">Sales log</a>
			</div>
			<div class="smd-updates">${updates_html}</div>
		</div>
		<div class="smd-card">
			<div class="smd-sec-title">
				<h2>Stuck Deals <span style="font-size:12px;color:#9ca3af;font-weight:400">&gt; 14 days in stage</span></h2>
				<a class="smd-link" href="/app/opportunity" target="_blank">Stage aging</a>
			</div>
			<table class="smd-table">
				<thead><tr><th>Customer</th><th>Stage</th><th>Days</th><th>Owner</th></tr></thead>
				<tbody>${stuck_rows}</tbody>
			</table>
		</div>
	</div>`;

	$("#smd-body").html(kpi_html + charts_html + tables_html + bottom_html);
}
