// frappe.pages['presales-request-das'].on_page_load = function(wrapper) {
// 	var page = frappe.ui.make_app_page({
// 		parent: wrapper,
// 		title: 'None',
// 		single_column: true
// 	});
// }

// ── Dashboard state ────────────────────────────────────────────────────────
const _ps = {
	selected_user:     null,
	user_label:        "All Users",
	from_date:         null,
	to_date:           null,
	selected_status:   null,
	status_label:      "All Statuses",
	selected_priority: null,
	priority_label:    "All Priorities",
};

frappe.pages["presales-request-das"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Presales Request Dashboard",
		single_column: true,
	});

	// ── Inject CSS ─────────────────────────────────────────────────────────
	if (!document.getElementById("psd-styles")) {
		const style = document.createElement("style");
		style.id = "psd-styles";
		style.textContent = `
			:root {
				--ps-primary:   #0f6b78;
				--ps-primary2:  #1f8ea0;
				--ps-accent:    #00a3ad;
				--ps-success:   #1f8a5b;
				--ps-warning:   #d9981e;
				--ps-danger:    #cf4d4d;
				--ps-info:      #316ed6;
				--ps-purple:    #6d28d9;
				--ps-line:      #d9e4e8;
				--ps-panel:     #ffffff;
				--ps-bg:        #f4f7f9;
				--ps-text:      #16313a;
				--ps-muted:     #6b7f88;
				--ps-shadow:    0 12px 32px rgba(22,49,58,0.08);
				--ps-radius:    18px;
			}
			.psd-wrap {
				padding: 20px 24px;
				background: linear-gradient(180deg,#eef4f6 0%,#f9fbfc 100%);
				min-height: 100vh;
				font-family: Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;
				color: var(--ps-text);
			}
			/* ── Hero ── */
			.psd-hero {
				background: linear-gradient(135deg,var(--ps-primary) 0%,#155a88 52%,var(--ps-accent) 100%);
				color: #fff;
				border-radius: 28px;
				padding: 26px 30px;
				margin-bottom: 20px;
				display: grid;
				grid-template-columns: 1.5fr 1fr;
				gap: 20px;
				align-items: center;
				box-shadow: var(--ps-shadow);
			}
			.psd-hero h1 { margin: 0 0 6px; font-size: 30px; font-weight: 800; letter-spacing: -0.03em; color: #fff}
			.psd-hero p  { margin: 0 0 14px; opacity: 0.88; font-size: 14px; line-height: 1.5; }
			.psd-hero-actions { display: flex; gap: 8px; flex-wrap: wrap; }
			.psd-btn {
				background: rgba(255,255,255,0.18);
				border: 1px solid rgba(255,255,255,0.28);
				color: #fff;
				padding: 8px 16px;
				border-radius: 999px;
				cursor: pointer;
				font-size: 13px;
				font-weight: 600;
				transition: background .2s;
				white-space: nowrap;
				position: relative;
			}
			.psd-btn:hover    { background: rgba(255,255,255,0.28); }
			.psd-btn.active   { background: rgba(255,255,255,0.38); border-color: rgba(255,255,255,0.6); }
			.psd-btn.filter-active { background: rgba(255,220,80,0.25); border-color: rgba(255,220,80,0.5); }
			.psd-hero-meta {
				display: grid;
				grid-template-columns: 1fr 1fr;
				gap: 12px;
			}
			.psd-meta-card {
				background: rgba(255,255,255,0.14);
				border: 1px solid rgba(255,255,255,0.18);
				border-radius: 16px;
				padding: 14px 16px;
			}
			.psd-meta-label { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; opacity: .85; margin-bottom: 4px; }
			.psd-meta-value { font-size: 22px; font-weight: 800; }
			/* ── Dropdown ── */
			.psd-dropdown {
				position: absolute;
				top: calc(100% + 6px);
				left: 0;
				background: #fff;
				border: 1px solid var(--ps-line);
				border-radius: 14px;
				box-shadow: 0 8px 28px rgba(22,49,58,0.13);
				min-width: 210px;
				z-index: 9999;
				overflow: hidden;
				color: var(--ps-text);
			}
			.psd-dd-header {
				padding: 8px 14px 4px;
				font-size: 11px;
				font-weight: 700;
				color: var(--ps-muted);
				text-transform: uppercase;
				letter-spacing: .06em;
			}
			.psd-dd-item {
				padding: 9px 14px;
				font-size: 13px;
				cursor: pointer;
				transition: background .15s;
			}
			.psd-dd-item:hover    { background: #eef7f8; color: var(--ps-primary); }
			.psd-dd-item.selected { background: #d1edf0; color: var(--ps-primary); font-weight: 700; }
			.psd-dd-divider { border-top: 1px solid #f0f4f5; margin: 4px 0; }
			/* ── KPI Grid ── */
			.psd-kpi-grid {
				display: grid;
				grid-template-columns: repeat(4,1fr);
				gap: 14px;
				margin-bottom: 16px;
			}
			.psd-kpi-card {
				background: var(--ps-panel);
				border: 1px solid var(--ps-line);
				border-radius: var(--ps-radius);
				padding: 18px 20px;
				box-shadow: var(--ps-shadow);
				position: relative;
				overflow: hidden;
			}
			.psd-kpi-card::after {
				content: "";
				position: absolute;
				inset: auto -16px -16px auto;
				width: 80px; height: 80px;
				border-radius: 50%;
				background: radial-gradient(circle, rgba(15,107,120,.12), transparent 70%);
			}
			.psd-kpi-label { font-size: 13px; color: var(--ps-muted); margin-bottom: 10px; }
			.psd-kpi-value { font-size: 32px; font-weight: 800; line-height: 1; margin-bottom: 6px; color: var(--ps-text); }
			.psd-kpi-note  { font-size: 12px; color: var(--ps-muted); }
			.psd-c-danger  { color: var(--ps-danger); }
			.psd-c-warn    { color: var(--ps-warning); }
			.psd-c-good    { color: var(--ps-success); }
			.psd-c-info    { color: var(--ps-info); }
			.psd-c-primary { color: var(--ps-primary); }
			/* ── Grid layouts ── */
			.psd-grid2 {
				display: grid;
				grid-template-columns: 1.5fr 1fr;
				gap: 16px;
				margin-bottom: 16px;
			}
			.psd-grid2eq {
				display: grid;
				grid-template-columns: 1fr 1fr;
				gap: 16px;
				margin-bottom: 16px;
			}
			.psd-grid3 {
				display: grid;
				grid-template-columns: 1fr 1fr 1fr;
				gap: 16px;
				margin-bottom: 16px;
			}
			/* ── Panel ── */
			.psd-panel {
				background: var(--ps-panel);
				border: 1px solid var(--ps-line);
				border-radius: 22px;
				box-shadow: var(--ps-shadow);
				padding: 20px;
			}
			.psd-sec-title {
				display: flex;
				justify-content: space-between;
				align-items: center;
				margin-bottom: 16px;
			}
			.psd-sec-title h2 { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: -0.02em; }
			.psd-link { color: var(--ps-primary2); font-size: 13px; font-weight: 600; text-decoration: none; cursor: pointer; }
			.psd-link:hover { text-decoration: underline; }
			/* ── Bar rows ── */
			.psd-bar-group { display: grid; gap: 11px; }
			.psd-bar-row {
				display: grid;
				grid-template-columns: 130px 1fr 90px;
				align-items: center;
				gap: 10px;
				font-size: 13px;
			}
			.psd-bar-label { color: var(--ps-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.psd-bar-track {
				width: 100%; height: 11px;
				background: #d1edf0;
				border-radius: 999px;
				overflow: hidden;
			}
			.psd-bar-fill {
				height: 100%;
				background: linear-gradient(90deg,var(--ps-accent),var(--ps-primary));
				border-radius: 999px;
				transition: width .6s ease;
			}
			.psd-bar-fill.warn   { background: linear-gradient(90deg,#f5c542,var(--ps-warning)); }
			.psd-bar-fill.danger { background: linear-gradient(90deg,#f88,var(--ps-danger)); }
			.psd-bar-fill.info   { background: linear-gradient(90deg,#82b4f8,var(--ps-info)); }
			.psd-bar-fill.purple { background: linear-gradient(90deg,#c4b5fd,var(--ps-purple)); }
			.psd-bar-val { font-weight: 700; font-size: 12px; text-align: right; color: var(--ps-text); }
			/* ── Table ── */
			.psd-table { width: 100%; border-collapse: collapse; font-size: 13px; }
			.psd-table th, .psd-table td {
				padding: 10px 8px;
				border-bottom: 1px solid #f0f4f5;
				text-align: left;
				vertical-align: middle;
			}
			.psd-table th {
				color: var(--ps-muted);
				font-weight: 700;
				font-size: 11px;
				text-transform: uppercase;
				letter-spacing: .05em;
			}
			.psd-table tr:hover td { background: #f7fbfc; }
			/* ── Badges ── */
			.psd-badge {
				display: inline-block;
				border-radius: 999px;
				padding: 3px 10px;
				font-size: 11px;
				font-weight: 700;
			}
			.psd-b-teal   { background: #d0f0f3; color: #0c6570; }
			.psd-b-blue   { background: #dbeafe; color: #1d4ed8; }
			.psd-b-green  { background: #dcfce7; color: #15803d; }
			.psd-b-yellow { background: #fef3c7; color: #b45309; }
			.psd-b-red    { background: #fee2e2; color: #b91c1c; }
			.psd-b-purple { background: #ede9fe; color: #6d28d9; }
			.psd-b-gray   { background: #f3f4f6; color: #374151; }
			/* ── Hours efficiency bar ── */
			.psd-hours-row {
				display: grid;
				grid-template-columns: 120px 1fr 80px 60px;
				align-items: center;
				gap: 10px;
				font-size: 13px;
				padding: 6px 0;
				border-bottom: 1px solid #f0f4f5;
			}
			.psd-hours-row:last-child { border-bottom: none; }
			.psd-eff-bar  { height: 8px; background: #d1edf0; border-radius: 999px; overflow: hidden; }
			.psd-eff-fill { height: 100%; background: linear-gradient(90deg,var(--ps-accent),var(--ps-success)); border-radius: 999px; }
			.psd-eff-fill.over { background: linear-gradient(90deg,#f88,var(--ps-danger)); }
			/* ── Opp link ── */
			.psd-opp-link { color: var(--ps-primary2); text-decoration: none; font-weight: 600; }
			.psd-opp-link:hover { text-decoration: underline; }
			/* ── Loading ── */
			.psd-loading { text-align: center; padding: 60px; color: var(--ps-muted); font-size: 14px; }
			/* ── Responsive ── */
			@media (max-width: 1200px) {
				.psd-kpi-grid { grid-template-columns: repeat(2,1fr); }
				.psd-grid2    { grid-template-columns: 1fr; }
				.psd-grid3    { grid-template-columns: 1fr 1fr; }
				.psd-hero     { grid-template-columns: 1fr; }
			}
			@media (max-width: 700px) {
				.psd-kpi-grid  { grid-template-columns: 1fr; }
				.psd-grid2eq   { grid-template-columns: 1fr; }
				.psd-grid3     { grid-template-columns: 1fr; }
				.psd-bar-row   { grid-template-columns: 90px 1fr 70px; }
				.psd-hours-row { grid-template-columns: 90px 1fr 60px; }
			}
		`;
		document.head.appendChild(style);
	}

	// ── Shell HTML ─────────────────────────────────────────────────────────
	$(page.body).html(`
		<div class="psd-wrap">
			<div class="psd-hero">
				<div>
					<h1>🎯 Presales Dashboard</h1>
					<p id="psd-subtitle">BS Group · ERPNext CRM · Loading…</p>
					<div class="psd-hero-actions">

						<!-- User filter -->
						<div style="position:relative">
							<button class="psd-btn" id="psd-user-btn">👤 All Users</button>
							<div class="psd-dropdown" id="psd-user-dd" style="display:none"></div>
						</div>

						<!-- Status filter -->
						<div style="position:relative">
							<button class="psd-btn" id="psd-status-btn">📋 All Statuses</button>
							<div class="psd-dropdown" id="psd-status-dd" style="display:none">
								<div class="psd-dd-header">Filter by Status</div>
								<div class="psd-dd-item selected" data-val="">All Statuses</div>
								<div class="psd-dd-divider"></div>
								<div class="psd-dd-item" data-val="Draft">Draft</div>
								<div class="psd-dd-item" data-val="Open">Open</div>
								<div class="psd-dd-item" data-val="Assigned">Assigned</div>
								<div class="psd-dd-item" data-val="In Progress">In Progress</div>
								<div class="psd-dd-item" data-val="Awaiting Sales Input">Awaiting Sales Input</div>
								<div class="psd-dd-item" data-val="Awaiting Customer Input">Awaiting Customer Input</div>
								<div class="psd-dd-item" data-val="Costing in Progress">Costing in Progress</div>
								<div class="psd-dd-item" data-val="Ready for Quotation">Ready for Quotation</div>
								<div class="psd-dd-item" data-val="Submitted to Sales">Submitted to Sales</div>
								<div class="psd-dd-item" data-val="On Hold">On Hold</div>
								<div class="psd-dd-item" data-val="Completed">Completed</div>
								<div class="psd-dd-item" data-val="Won">Won</div>
								<div class="psd-dd-item" data-val="Lost">Lost</div>
								<div class="psd-dd-item" data-val="Cancelled">Cancelled</div>
							</div>
						</div>

						<!-- Priority filter -->
						<div style="position:relative">
							<button class="psd-btn" id="psd-priority-btn">🚦 All Priorities</button>
							<div class="psd-dropdown" id="psd-priority-dd" style="display:none">
								<div class="psd-dd-header">Filter by Priority</div>
								<div class="psd-dd-item selected" data-val="">All Priorities</div>
								<div class="psd-dd-divider"></div>
								<div class="psd-dd-item" data-val="Critical">Critical</div>
								<div class="psd-dd-item" data-val="High">High</div>
								<div class="psd-dd-item" data-val="Medium">Medium</div>
								<div class="psd-dd-item" data-val="Low">Low</div>
							</div>
						</div>

						<!-- Date range -->
						<button class="psd-btn" id="psd-date-btn">📅 This Month</button>

						<!-- Refresh -->
						<button class="psd-btn" id="psd-refresh">⟳ Refresh</button>
					</div>
				</div>
				<div class="psd-hero-meta" id="psd-hero-meta">
					<div class="psd-meta-card">
						<div class="psd-meta-label">Reporting Period</div>
						<div class="psd-meta-value" id="hm-period">—</div>
					</div>
					<div class="psd-meta-card">
						<div class="psd-meta-label">Last Refresh</div>
						<div class="psd-meta-value" id="hm-refresh">—</div>
					</div>
					<div class="psd-meta-card">
						<div class="psd-meta-label">Viewing As</div>
						<div class="psd-meta-value" id="hm-user" style="font-size:16px">All Users</div>
					</div>
					<div class="psd-meta-card">
						<div class="psd-meta-label">Active Owners</div>
						<div class="psd-meta-value" id="hm-owners">—</div>
					</div>
				</div>
			</div>

			<div id="psd-body">
				<div class="psd-loading">Loading presales data…</div>
			</div>
		</div>
	`);

	// ── User dropdown ──────────────────────────────────────────────────────
	$("#psd-user-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#psd-user-dd");
		if ($dd.is(":visible")) { $dd.hide(); return; }
		$dd.html('<div class="psd-dd-item" style="color:#9ca3af">Loading…</div>').show();

		frappe.call({
			method: "bsgroup.bs_group.page.presales_request_das.presales_request_das.get_presales_users",
			callback: function (r) {
				const users = r.message || [];
				if (!users.length) {
					$dd.html('<div class="psd-dd-item" style="color:#9ca3af">No users found</div>');
					return;
				}
				let html = '<div class="psd-dd-header">Filter by Owner</div>';
				html += `<div class="psd-dd-item${!_ps.selected_user ? " selected" : ""}" data-user="">All Users</div>`;
				html += '<div class="psd-dd-divider"></div>';
				users.forEach(u => {
					const name  = u.user || "";
					const label = name.split("@")[0].replace(/\./g, " ").replace(/\b\w/g, c => c.toUpperCase());
					const sel   = _ps.selected_user === name ? " selected" : "";
					html += `<div class="psd-dd-item${sel}" data-user="${name}" title="${name}">${label}</div>`;
				});
				$dd.html(html);
			},
		});
	});

	$(document).on("click", "#psd-user-dd .psd-dd-item", function () {
		_ps.selected_user = $(this).data("user") || null;
		_ps.user_label    = $(this).text().trim();
		$("#psd-user-btn").text("👤 " + _ps.user_label).toggleClass("filter-active", !!_ps.selected_user);
		$("#hm-user").text(_ps.user_label);
		$("#psd-user-dd").hide();
		load_dashboard();
	});

	// ── Status dropdown ────────────────────────────────────────────────────
	$("#psd-status-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#psd-status-dd");
		$dd.is(":visible") ? $dd.hide() : $dd.show();
	});

	$(document).on("click", "#psd-status-dd .psd-dd-item", function () {
		_ps.selected_status = $(this).data("val") || null;
		_ps.status_label    = $(this).text().trim();
		$("#psd-status-dd .psd-dd-item").removeClass("selected");
		$(this).addClass("selected");
		$("#psd-status-btn").text("📋 " + _ps.status_label).toggleClass("filter-active", !!_ps.selected_status);
		$("#psd-status-dd").hide();
		load_dashboard();
	});

	// ── Priority dropdown ──────────────────────────────────────────────────
	$("#psd-priority-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#psd-priority-dd");
		$dd.is(":visible") ? $dd.hide() : $dd.show();
	});

	$(document).on("click", "#psd-priority-dd .psd-dd-item", function () {
		_ps.selected_priority = $(this).data("val") || null;
		_ps.priority_label    = $(this).text().trim();
		$("#psd-priority-dd .psd-dd-item").removeClass("selected");
		$(this).addClass("selected");
		$("#psd-priority-btn").text("🚦 " + _ps.priority_label).toggleClass("filter-active", !!_ps.selected_priority);
		$("#psd-priority-dd").hide();
		load_dashboard();
	});

	// ── Date filter ────────────────────────────────────────────────────────
	$("#psd-date-btn").on("click", function () {
		frappe.prompt(
			[
				{ fieldname: "from_date", label: "From Date", fieldtype: "Date", reqd: 1,
				  default: _ps.from_date || frappe.datetime.month_start() },
				{ fieldname: "to_date",   label: "To Date",   fieldtype: "Date", reqd: 1,
				  default: _ps.to_date   || frappe.datetime.month_end() },
			],
			function (vals) {
				_ps.from_date = vals.from_date;
				_ps.to_date   = vals.to_date;
				const label = frappe.datetime.str_to_user(vals.from_date) + " → " + frappe.datetime.str_to_user(vals.to_date);
				$("#psd-date-btn").text("📅 " + label).addClass("filter-active");
				load_dashboard();
			},
			"Select Date Range",
			"Apply"
		);
	});

	// ── Close dropdowns when clicking outside ──────────────────────────────
	$(document).on("click", function (e) {
		if (!$(e.target).closest("#psd-user-btn,#psd-user-dd").length)     $("#psd-user-dd").hide();
		if (!$(e.target).closest("#psd-status-btn,#psd-status-dd").length) $("#psd-status-dd").hide();
		if (!$(e.target).closest("#psd-priority-btn,#psd-priority-dd").length) $("#psd-priority-dd").hide();
	});

	$("#psd-refresh").on("click", () => load_dashboard());
	load_dashboard();

	// ── TV mode (?tv=1) ────────────────────────────────────────────────────
	if (new URLSearchParams(window.location.search).get("tv") === "1") {
		// Hide Frappe chrome for full-screen display
		document.querySelector(".navbar-expand")?.style.setProperty("display", "none", "important");
		document.querySelector(".layout-side-section")?.style.setProperty("display", "none", "important");
		document.querySelector(".page-head")?.style.setProperty("display", "none", "important");
		document.querySelector(".layout-main-section-wrapper")
			?.style.setProperty("padding", "0", "important");

		if (!document.getElementById("psd-tv-styles")) {
			const tvStyle = document.createElement("style");
			tvStyle.id = "psd-tv-styles";
			tvStyle.textContent = `
				.psd-wrap          { padding: 28px 36px !important; }
				.psd-hero          { padding: 28px 36px !important; }
				.psd-hero h1       { font-size: clamp(32px, 3vw, 52px) !important; }
				.psd-hero .sub     { font-size: 18px !important; }
				.psd-kpi-label     { font-size: 16px !important; margin-bottom: 14px !important; }
				.psd-kpi-value     { font-size: clamp(64px, 5.5vw, 100px) !important; margin-bottom: 12px !important; }
				.psd-kpi-note      { font-size: 15px !important; }
				.psd-kpi-card      { padding: 26px 28px !important; }
				.psd-sec-title h2  { font-size: clamp(22px, 2vw, 30px) !important; }
				.psd-table         { font-size: 17px !important; }
				.psd-table th      { font-size: 13px !important; padding: 10px 12px !important; }
				.psd-table td      { padding: 14px 12px !important; }
				.psd-bar-label     { font-size: 16px !important; }
				.psd-bar-val       { font-size: 16px !important; font-weight: 700 !important; }
				.psd-bar-row       { margin-bottom: 14px !important; }
			`;
			document.head.appendChild(tvStyle);
		}

		// Auto-refresh every 60 seconds
		setInterval(() => load_dashboard(), 60000);
	}
};

// ── Helpers ────────────────────────────────────────────────────────────────
function psd_fmt(val) {
	val = parseFloat(val) || 0;
	if (val >= 1e6) return "AED " + (val / 1e6).toFixed(1) + "M";
	if (val >= 1e3) return "AED " + Math.round(val / 1000) + "K";
	return "AED " + val.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function psd_opp_link(name, label) {
	return `<a class="psd-opp-link" href="/app/presales-request/${encodeURIComponent(name)}" target="_blank">${label || name}</a>`;
}

function psd_priority_badge(p) {
	const map = {
		"Critical": "psd-b-red",
		"High":     "psd-b-yellow",
		"Medium":   "psd-b-blue",
		"Low":      "psd-b-gray",
	};
	return `<span class="psd-badge ${map[p] || "psd-b-gray"}">${p || "—"}</span>`;
}

function psd_status_badge(s) {
	const map = {
		"Draft":                   "psd-b-gray",
		"Open":                    "psd-b-blue",
		"Assigned":                "psd-b-blue",
		"In Progress":             "psd-b-teal",
		"Awaiting Sales Input":    "psd-b-yellow",
		"Awaiting Customer Input": "psd-b-yellow",
		"Costing in Progress":     "psd-b-purple",
		"Ready for Quotation":     "psd-b-teal",
		"Submitted to Sales":      "psd-b-teal",
		"On Hold":                 "psd-b-gray",
		"Completed":               "psd-b-green",
		"Won":                     "psd-b-green",
		"Lost":                    "psd-b-red",
		"Cancelled":               "psd-b-gray",
	};
	return `<span class="psd-badge ${map[s] || "psd-b-gray"}">${s || "—"}</span>`;
}

function bar_color_for(index) {
	const colors = ["", "warn", "danger", "info", "purple"];
	return colors[index % colors.length];
}

function psd_bar_rows(items, label_key, val_key, max_val, fmt_fn, sub_key) {
	if (!items || !items.length) return `<div style="color:var(--ps-muted);font-size:13px">No data</div>`;
	let html = '<div class="psd-bar-group">';
	items.forEach((row, i) => {
		const val   = parseFloat(row[val_key]) || 0;
		const label = row[label_key] || "—";
		const pct   = max_val > 0 ? Math.min(100, (val / max_val) * 100).toFixed(1) : 0;
		const sub   = sub_key ? `<span style="color:var(--ps-muted);font-size:11px"> (${row[sub_key]})</span>` : "";
		const clr   = bar_color_for(i);
		const display = fmt_fn ? fmt_fn(val) : val;
		html += `
			<div class="psd-bar-row">
				<span class="psd-bar-label" title="${label}">${label}${sub}</span>
				<div class="psd-bar-track"><div class="psd-bar-fill ${clr}" style="width:${pct}%"></div></div>
				<span class="psd-bar-val">${display}</span>
			</div>`;
	});
	html += "</div>";
	return html;
}

// ── Main loader ────────────────────────────────────────────────────────────
function load_dashboard() {
	$("#psd-refresh").prop("disabled", true).text("Loading…");
	$("#psd-body").html('<div class="psd-loading">Fetching presales data…</div>');

	frappe.call({
		method: "bsgroup.bs_group.page.presales_request_das.presales_request_das.get_dashboard_data",
		args: {
			selected_user:     _ps.selected_user     || null,
			from_date:         _ps.from_date         || null,
			to_date:           _ps.to_date           || null,
			selected_status:   _ps.selected_status   || null,
			selected_priority: _ps.selected_priority || null,
		},
		callback: function (r) {
			$("#psd-refresh").prop("disabled", false).text("⟳ Refresh");
			if (r.exc || !r.message) {
				$("#psd-body").html(
					`<div class="psd-loading" style="color:var(--ps-danger)">Failed to load data. Check console for errors.</div>`
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
	const filters = d.active_filters || {};

	// Hide user filter for non-managers
	if (!d.is_manager) $("#psd-user-btn").hide();

	// Update hero meta cards
	const _now     = new Date();
	const _timeStr = _now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
	const _monthStr = _now.toLocaleString("en-US", { month: "long", year: "numeric" });
	$("#hm-period").text(filters.is_custom_date
		? `${frappe.datetime.str_to_user(filters.from_date)} – ${frappe.datetime.str_to_user(filters.to_date)}`
		: _monthStr);
	$("#hm-refresh").text(_timeStr);
	$("#hm-user").text(_ps.user_label || "All Users");
	$("#hm-owners").text((d.owner_data || []).length || 0);
	$("#psd-subtitle").text("BS Group · ERPNext CRM · " + (d.generated_at || ""));

	const due_label = filters.is_custom_date
		? `Due ${frappe.datetime.str_to_user(filters.from_date)} – ${frappe.datetime.str_to_user(filters.to_date)}`
		: "Due This Month";

	// ── KPI Cards ──────────────────────────────────────────────────────────
	const _total_for_wr = (kpis.completed_month || 0) + (kpis.total_active || 0);
	const _wr_val       = _total_for_wr > 0 ? Math.round((kpis.completed_month || 0) / _total_for_wr * 100) : null;
	const _wr_display   = _wr_val !== null ? _wr_val + "%" : "—";
	const _wr_class     = _wr_val === null ? "" : _wr_val >= 60 ? "psd-c-good" : _wr_val >= 30 ? "psd-c-warn" : "psd-c-danger";

	const kpi_html = `
	<div class="psd-kpi-grid">
		<div class="psd-kpi-card">
			<div class="psd-kpi-label">Active Requests</div>
			<div class="psd-kpi-value psd-c-primary">${kpis.total_active}</div>
			<div class="psd-kpi-note">Open opportunities in presales pipeline</div>
		</div>
		<div class="psd-kpi-card">
			<div class="psd-kpi-label">Pipeline Value</div>
			<div class="psd-kpi-value">${psd_fmt(kpis.total_pipeline)}</div>
			<div class="psd-kpi-note">Estimated value of active presales</div>
		</div>
		<div class="psd-kpi-card">
			<div class="psd-kpi-label">Overdue Requests</div>
			<div class="psd-kpi-value psd-c-danger">${kpis.overdue_count}</div>
			<div class="psd-kpi-note">Past due date and still open</div>
		</div>
		<div class="psd-kpi-card">
			<div class="psd-kpi-label">${due_label}</div>
			<div class="psd-kpi-value psd-c-warn">${kpis.due_period_count}</div>
			<div class="psd-kpi-note">Requests with due date in selected range</div>
		</div>
	</div>
	<div class="psd-kpi-grid" style="margin-bottom:20px">
		<div class="psd-kpi-card">
			<div class="psd-kpi-label">No Updates in 7 Days</div>
			<div class="psd-kpi-value psd-c-warn">${kpis.no_update_count}</div>
			<div class="psd-kpi-note">Stale requests needing attention</div>
		</div>
		<div class="psd-kpi-card">
			<div class="psd-kpi-label">Avg Quality Score</div>
			<div class="psd-kpi-value psd-c-good">${kpis.avg_quality > 0 ? kpis.avg_quality + " / 5" : "N/A"}</div>
			<div class="psd-kpi-note">Average score across completed requests</div>
		</div>
		<div class="psd-kpi-card">
			<div class="psd-kpi-label">Completed This Month</div>
			<div class="psd-kpi-value psd-c-good">${kpis.completed_month}</div>
			<div class="psd-kpi-note">Successfully closed this month</div>
		</div>
		<div class="psd-kpi-card">
			<div class="psd-kpi-label">Win Rate (Est.)</div>
			<div class="psd-kpi-value ${_wr_class}">${_wr_display}</div>
			<div class="psd-kpi-note">Completed vs total this period</div>
		</div>
	</div>`;

	// ── Charts: Status + Priority + Owner ─────────────────────────────────
	const status_items   = d.status_data   || [];
	const priority_items = d.priority_data || [];
	const owner_items    = d.owner_data    || [];

	const status_max   = status_items.length   ? Math.max(...status_items.map(x => x.amount))   : 1;
	const priority_max = priority_items.length ? Math.max(...priority_items.map(x => x.amount)) : 1;
	const owner_max    = owner_items.length    ? Math.max(...owner_items.map(x => x.amount))    : 1;

	const charts_html = `
	<div class="psd-grid3">
		<div class="psd-panel">
			<div class="psd-sec-title">
				<h2>Pipeline by Status</h2>
				<a class="psd-link" href="/app/presales-request" target="_blank">View all</a>
			</div>
			${psd_bar_rows(status_items, "status", "amount", status_max, psd_fmt, "count")}
		</div>
		<div class="psd-panel">
			<div class="psd-sec-title">
				<h2>Pipeline by Priority</h2>
				<a class="psd-link" href="/app/presales-request" target="_blank">View all</a>
			</div>
			${psd_bar_rows(priority_items, "priority", "amount", priority_max, psd_fmt, "count")}
		</div>
		<div class="psd-panel">
			<div class="psd-sec-title">
				<h2>Owner Pipeline</h2>
				<a class="psd-link" href="/app/presales-request" target="_blank">View all</a>
			</div>
			${psd_bar_rows(owner_items.map(r => ({ ...r, label: r.owner_short })), "label", "amount", owner_max, psd_fmt, "count")}
		</div>
	</div>`;

	// ── Overdue + Due This Period tables ───────────────────────────────────
	let overdue_rows = "";
	(d.overdue_list || []).forEach(row => {
		overdue_rows += `<tr>
			<td>${psd_opp_link(row.name, row.customer || row.name)}</td>
			<td>${psd_status_badge(row.status)}</td>
			<td>${psd_priority_badge(row.priority)}</td>
			<td><span style="color:var(--ps-danger);font-weight:700">${row.due_display || "—"}</span></td>
			<td style="color:var(--ps-danger);font-weight:700">${row.delay_days ? row.delay_days + "d" : "—"}</td>
		</tr>`;
	});
	if (!overdue_rows) overdue_rows = `<tr><td colspan="5" style="color:var(--ps-muted);text-align:center;padding:20px">✓ No overdue requests</td></tr>`;

	let due_rows = "";
	(d.due_list || []).forEach(row => {
		due_rows += `<tr>
			<td>${psd_opp_link(row.name, row.customer || row.name)}</td>
			<td style="font-weight:700">${psd_fmt(row.estimated_value)}</td>
			<td>${psd_status_badge(row.status)}</td>
			<td>${psd_priority_badge(row.priority)}</td>
			<td><span style="font-weight:700;color:var(--ps-primary)">${row.due_display || "—"}</span></td>
		</tr>`;
	});
	if (!due_rows) due_rows = `<tr><td colspan="5" style="color:var(--ps-muted);text-align:center;padding:20px">No requests due in this period</td></tr>`;

	const tables_html = `
	<div class="psd-grid2eq">
		<div class="psd-panel">
			<div class="psd-sec-title">
				<h2>⚠️ Overdue Requests</h2>
				<a class="psd-link" href="/app/presales-request?overdue=1" target="_blank">See all</a>
			</div>
			<table class="psd-table">
				<thead><tr><th>Customer</th><th>Status</th><th>Priority</th><th>Due</th><th>Delay</th></tr></thead>
				<tbody>${overdue_rows}</tbody>
			</table>
		</div>
		<div class="psd-panel">
			<div class="psd-sec-title">
				<h2>📅 ${due_label}</h2>
				<a class="psd-link" href="/app/presales-request" target="_blank">View all</a>
			</div>
			<table class="psd-table">
				<thead><tr><th>Customer</th><th>Value</th><th>Status</th><th>Priority</th><th>Due</th></tr></thead>
				<tbody>${due_rows}</tbody>
			</table>
		</div>
	</div>`;

	// ── High-value deals ───────────────────────────────────────────────────
	let highval_rows = "";
	(d.highval_list || []).forEach(row => {
		// const dm_known  = row.decision_maker_known ? "✅" : "❌";
		// const budget_ok = row.budget_confirmed     ? "✅" : "❌";
		highval_rows += `<tr>
			<td>${psd_opp_link(row.name, row.customer || row.name)}</td>
			<td style="font-weight:800;color:var(--ps-primary)">${psd_fmt(row.estimated_value)}</td>
			<td>${psd_status_badge(row.status)}</td>
			<td>${psd_priority_badge(row.priority)}</td>
			<td style="color:var(--ps-muted);font-size:12px">${row.close_display || "—"}</td>
			<td style="color:var(--ps-muted)">${row.owner_short}</td>
		</tr>`;
	});
	if (!highval_rows) highval_rows = `<tr><td colspan="8" style="color:var(--ps-muted);text-align:center;padding:20px">No high-value requests</td></tr>`;

	// ── Hours efficiency ───────────────────────────────────────────────────
	let hours_html = "";
	(d.hours_data || []).forEach(row => {
		const eff     = row.efficiency || 0;
		const is_over = row.actual > row.estimated && row.estimated > 0;
		const bar_pct = Math.min(100, eff).toFixed(0);
		hours_html += `
		<div class="psd-hours-row">
			<span style="font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${row.owner_short}</span>
			<div class="psd-eff-bar"><div class="psd-eff-fill ${is_over ? "over" : ""}" style="width:${bar_pct}%"></div></div>
			<span style="font-size:12px;color:var(--ps-muted)">${row.actual}h / ${row.estimated}h</span>
			<span style="font-size:12px;font-weight:700;color:${is_over ? "var(--ps-danger)" : "var(--ps-success)"}">${eff}%</span>
		</div>`;
	});
	if (!hours_html) hours_html = `<div style="color:var(--ps-muted);font-size:13px">No hours data available</div>`;

	const bottom_html = `
	<div class="psd-panel" style="margin-bottom:16px">
		<div class="psd-sec-title">
			<h2>💎 High-Value Presales Requests</h2>
			<a class="psd-link" href="/app/presales-request" target="_blank">View all</a>
		</div>
		<table class="psd-table">
			<thead><tr><th>Customer</th><th>Est. Value</th><th>Status</th><th>Priority</th><th>Close</th><th>Owner</th></tr></thead>
			<tbody>${highval_rows}</tbody>
		</table>
	</div>
	<div class="psd-panel">
		<div class="psd-sec-title">
			<h2>⏱️ Hours Efficiency by Owner</h2>
			<span style="font-size:13px;color:var(--ps-muted)">Actual vs Estimated (higher = better utilization)</span>
		</div>
		${hours_html}
	</div>`;

	$("#psd-body").html(kpi_html + charts_html + tables_html + bottom_html);
}