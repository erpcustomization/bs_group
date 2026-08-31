// ── Dashboard state ────────────────────────────────────────────────────────
const _hd = {
	selected_agent:    null,
	from_date:         null,
	to_date:           null,
	selected_status:   null,
	selected_priority: null,
	current_screen:    0,
};

frappe.pages["hd-ticket-das"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Helpdesk Ticket Dashboard",
		single_column: true,
	});

	// ── Inject CSS ─────────────────────────────────────────────────────────
	if (!document.getElementById("hd-styles")) {
		const style = document.createElement("style");
		style.id = "hd-styles";
		style.textContent = `
			:root {
				--hd-bg:     #0f172a;
				--hd-panel:  rgba(255,255,255,0.07);
				--hd-border: rgba(255,255,255,0.10);
				--hd-text:   #f1f5f9;
				--hd-muted:  #94a3b8;
				--hd-red:    #ef4444;
				--hd-orange: #f59e0b;
				--hd-green:  #22c55e;
				--hd-cyan:   #06b6d4;
				--hd-blue:   #3b82f6;
				--hd-purple: #8b5cf6;
				--hd-pink:   #ec4899;
				--hd-r:      20px;
				--hd-shadow: 0 12px 32px rgba(0,0,0,0.22);
			}
			/* ── Reset Frappe overrides ── */
			.hd-wrap, .hd-wrap * { box-sizing: border-box; }
			.hd-wrap h1, .hd-wrap h2, .hd-wrap h3,
			.hd-wrap th, .hd-wrap td, .hd-wrap span,
			.hd-wrap div, .hd-wrap li, .hd-wrap p { color: inherit; }
			/* ── Wrapper ── */
			.hd-wrap {
				background: linear-gradient(135deg,#0f172a 0%,#111827 55%,#172554 100%);
				min-height: 100vh;
				padding: 20px 24px;
				font-family: "Segoe UI", Inter, sans-serif;
				color: var(--hd-text);
				display: flex;
				flex-direction: column;
				gap: 18px;
			}
			/* ── Screen visibility ── */
			.hd-screen { display: none; }
			.hd-screen.active {
				display: flex;
				flex-direction: column;
				gap: 18px;
			}
			/* ── Header ── */
			.hd-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				gap: 14px;
				flex-wrap: wrap;
			}
			.hd-logo-dot {
				width: 15px; height: 15px; border-radius: 50%; flex-shrink: 0;
				background: linear-gradient(135deg,var(--hd-cyan),var(--hd-purple),var(--hd-pink));
				box-shadow: 0 0 18px rgba(139,92,246,0.7);
			}
			.hd-title-wrap { display: flex; align-items: center; gap: 14px; }
			.hd-title-wrap h1 {
				margin: 0; font-size: clamp(20px,2.2vw,34px);
				font-weight: 800; letter-spacing: -0.01em;
				color: var(--hd-text) !important;
			}
			.hd-subtitle { color: var(--hd-muted) !important; font-size: 13px; margin-top: 3px; }
			/* ── Toolbar ── */
			.hd-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
			.hd-btn {
				padding: 8px 16px; border-radius: 999px;
				background: rgba(255,255,255,0.09);
				border: 1px solid rgba(255,255,255,0.13);
				color: var(--hd-text) !important;
				font-size: 13px; font-weight: 600;
				cursor: pointer; white-space: nowrap;
				transition: background .18s; position: relative;
			}
			.hd-btn:hover { background: rgba(255,255,255,0.16); }
			.hd-btn.filter-active { background: rgba(250,204,21,0.18); border-color: rgba(250,204,21,0.35); }
			/* Screen tabs */
			.hd-screen-nav { display: flex; gap: 6px; }
			.hd-screen-tab {
				padding: 8px 18px; border-radius: 999px;
				background: rgba(255,255,255,0.07);
				border: 1px solid rgba(255,255,255,0.12);
				color: var(--hd-muted) !important; font-size: 13px; font-weight: 700;
				cursor: pointer; transition: all .18s;
			}
			.hd-screen-tab.active {
				background: linear-gradient(135deg,var(--hd-cyan),var(--hd-purple));
				color: #fff !important; border-color: transparent;
				box-shadow: 0 4px 16px rgba(139,92,246,0.35);
			}
			/* Dropdown */
			.hd-dropdown {
				position: absolute; top: calc(100% + 6px); left: 0;
				background: #1e293b; border: 1px solid rgba(255,255,255,0.12);
				border-radius: 14px; box-shadow: 0 8px 28px rgba(0,0,0,0.4);
				min-width: 200px; z-index: 9999; overflow: hidden;
			}
			.hd-dd-header { padding: 8px 14px 4px; font-size: 11px; font-weight: 700; color: var(--hd-muted) !important; text-transform: uppercase; letter-spacing: .06em; }
			.hd-dd-item   { padding: 9px 14px; font-size: 13px; cursor: pointer; transition: background .14s; color: var(--hd-text) !important; }
			.hd-dd-item:hover    { background: rgba(255,255,255,0.07); color: var(--hd-cyan) !important; }
			.hd-dd-item.selected { background: rgba(6,182,212,0.13); color: var(--hd-cyan) !important; font-weight: 700; }
			.hd-dd-divider { border-top: 1px solid rgba(255,255,255,0.07); margin: 4px 0; }
			/* ── KPI grid ── */
			.hd-kpi-row {
				display: grid;
				grid-template-columns: repeat(6,1fr);
				gap: 14px;
			}
			.hd-kpi-card {
				background: var(--hd-panel);
				border: 1px solid var(--hd-border);
				border-radius: var(--hd-r);
				padding: 18px 20px;
				box-shadow: var(--hd-shadow);
				position: relative; overflow: hidden;
			}
			.hd-kpi-card::before {
				content:""; position:absolute; top:0; left:0; right:0; height:3px;
				background: linear-gradient(90deg,var(--hd-cyan),var(--hd-purple),var(--hd-pink));
			}
			.hd-kpi-label {
				color: var(--hd-muted) !important;
				font-size: 12px; text-transform: uppercase;
				letter-spacing: .07em; margin-bottom: 10px;
			}
			.hd-kpi-value {
				font-size: clamp(24px,2.2vw,40px); font-weight: 800;
				line-height: 1; margin-bottom: 8px;
			}
			.hd-kpi-note { color: var(--hd-muted) !important; font-size: 12px; }
			/* ── Main content grids ── */
			.hd-row {
				display: grid;
				gap: 16px;
			}
			.hd-cols-2-1 { grid-template-columns: 1.85fr 1fr; }
			.hd-cols-2eq { grid-template-columns: 1fr 1fr; }
			/* ── Card ── */
			.hd-card {
				background: var(--hd-panel);
				border: 1px solid var(--hd-border);
				border-radius: var(--hd-r);
				padding: 20px;
				box-shadow: var(--hd-shadow);
			}
			.hd-card-head {
				display: flex; justify-content: space-between;
				align-items: baseline; gap: 10px;
				margin-bottom: 16px; flex-wrap: wrap;
			}
			.hd-card-head h2 {
				margin: 0; font-size: clamp(15px,1.4vw,21px);
				font-weight: 700; color: var(--hd-text) !important;
				letter-spacing: -0.01em;
			}
			.hd-card-note { color: var(--hd-muted) !important; font-size: 12px; }
			/* ── Side stack ── */
			.hd-stack { display: flex; flex-direction: column; gap: 16px; }
			/* ── Table ── */
			.hd-table { width:100%; border-collapse:collapse; font-size: clamp(12px,0.88vw,14px); }
			.hd-table th {
				padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.09);
				text-align:left; font-size:11px; text-transform:uppercase;
				letter-spacing:.07em; color: #cbd5e1 !important; font-weight:700;
			}
			.hd-table td {
				padding: 10px 10px; border-bottom: 1px solid rgba(255,255,255,0.06);
				text-align:left; vertical-align:middle; color: var(--hd-text) !important;
			}
			.hd-table tr:last-child td { border-bottom: none; }
			.hd-table tr:hover td { background: rgba(255,255,255,0.03); }
			/* ── Badges ── */
			.hd-badge {
				display: inline-block; padding: 4px 10px; border-radius: 999px;
				font-size: 11px; font-weight: 700; letter-spacing:.04em; text-transform:uppercase;
			}
			.hd-b-red    { background: rgba(239,68,68,0.16);   color: #fecaca !important; }
			.hd-b-orange { background: rgba(245,158,11,0.18);  color: #fde68a !important; }
			.hd-b-blue   { background: rgba(59,130,246,0.16);  color: #bfdbfe !important; }
			.hd-b-green  { background: rgba(34,197,94,0.18);   color: #bbf7d0 !important; }
			.hd-b-purple { background: rgba(139,92,246,0.16);  color: #ddd6fe !important; }
			.hd-b-cyan   { background: rgba(6,182,212,0.16);   color: #a5f3fc !important; }
			.hd-b-gray   { background: rgba(255,255,255,0.09); color: #cbd5e1 !important; }
			/* ── Meter / Bar ── */
			.hd-meter { margin-bottom: 14px; }
			.hd-meter:last-child { margin-bottom: 0; }
			.hd-meter-head {
				display:flex; justify-content:space-between;
				font-size:13px; margin-bottom:6px; font-weight:600;
				color: var(--hd-text) !important;
			}
			.hd-bar { height:11px; width:100%; background:rgba(255,255,255,0.07); border-radius:999px; overflow:hidden; }
			.hd-fill { height:100%; border-radius:999px; transition:width .5s ease; }
			.hd-fill.green  { background:linear-gradient(90deg,#16a34a,#4ade80); }
			.hd-fill.orange { background:linear-gradient(90deg,#d97706,#fbbf24); }
			.hd-fill.red    { background:linear-gradient(90deg,#dc2626,#fb7185); }
			.hd-fill.blue   { background:linear-gradient(90deg,#2563eb,#38bdf8); }
			.hd-fill.purple { background:linear-gradient(90deg,#7c3aed,#ec4899); }
			.hd-fill.cyan   { background:linear-gradient(90deg,#0891b2,#06b6d4); }
			/* ── Summary strip (Screen 1 bottom of queue) ── */
			.hd-strip {
				display: grid; grid-template-columns: repeat(3,1fr);
				gap: 12px; margin-top: 16px;
			}
			.hd-strip-item {
				background: rgba(255,255,255,0.06);
				border: 1px solid rgba(255,255,255,0.09);
				border-radius: 14px; padding: 12px;
				text-align: center;
			}
			.hd-strip-item .sv { font-size: 24px; font-weight: 800; margin-bottom: 4px; }
			.hd-strip-item .sl { font-size: 11px; color: var(--hd-muted) !important; text-transform: uppercase; letter-spacing:.07em; }
			/* ── Activity list ── */
			.hd-activity { list-style:none; margin:0; padding:0; }
			.hd-activity li {
				padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.07);
				font-size: 13px; line-height: 1.5; color: var(--hd-text) !important;
			}
			.hd-activity li:last-child { border-bottom: none; }
			/* ── Priority breakdown rows ── */
			.hd-pri-row {
				display: flex; align-items: center; gap: 12px;
				padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.07);
			}
			.hd-pri-row:last-child { border-bottom: none; }
			.hd-pri-label { width: 90px; font-size: 13px; font-weight: 600; color: var(--hd-text) !important; flex-shrink:0; }
			.hd-pri-count { width: 38px; font-size: 18px; font-weight: 800; text-align:right; flex-shrink:0; }
			.hd-pri-bar-wrap { flex: 1; }
			/* ── Ticket link ── */
			.hd-link { color: var(--hd-cyan) !important; text-decoration:none; font-weight:700; }
			.hd-link:hover { text-decoration: underline; }
			/* ── Colors ── */
			.hd-red    { color: var(--hd-red)    !important; }
			.hd-orange { color: var(--hd-orange) !important; }
			.hd-green  { color: var(--hd-green)  !important; }
			.hd-cyan   { color: var(--hd-cyan)   !important; }
			.hd-blue   { color: var(--hd-blue)   !important; }
			.hd-purple { color: var(--hd-purple) !important; }
			.hd-muted  { color: var(--hd-muted)  !important; }
			/* ── Loading / footer ── */
			.hd-loading { text-align:center; padding:60px; color:var(--hd-muted); font-size:14px; }
			.hd-footer  { font-size:12px; color:var(--hd-muted) !important; text-align:right; }
			/* ── Responsive ── */
			@media (max-width: 1400px) {
				.hd-kpi-row  { grid-template-columns: repeat(3,1fr); }
				.hd-cols-2-1 { grid-template-columns: 1fr; }
			}
			@media (max-width: 900px) {
				.hd-kpi-row  { grid-template-columns: repeat(2,1fr); }
				.hd-cols-2-1, .hd-cols-2eq { grid-template-columns: 1fr; }
			}
		`;
		document.head.appendChild(style);
	}

	// ── Shell HTML ─────────────────────────────────────────────────────────
	$(page.body).html(`
		<div class="hd-wrap">
			<div class="hd-header">
				<div class="hd-title-wrap">
					<div class="hd-logo-dot"></div>
					<div>
						<h1>🎧 Helpdesk Command Center</h1>
						<div class="hd-subtitle" id="hd-subtitle">BS Group · ERPNext Helpdesk · Loading…</div>
					</div>
				</div>
				<div class="hd-toolbar">
					<div class="hd-screen-nav">
						<button class="hd-screen-tab active" data-screen="0">📊 Live Operations</button>
						<button class="hd-screen-tab"        data-screen="1">📈 Analytics</button>
					</div>
					<div style="position:relative">
						<button class="hd-btn" id="hd-agent-btn">👤 All Agents</button>
						<div class="hd-dropdown" id="hd-agent-dd" style="display:none"></div>
					</div>
					<div style="position:relative">
						<button class="hd-btn" id="hd-status-btn">📋 All Statuses</button>
						<div class="hd-dropdown" id="hd-status-dd" style="display:none">
							<div class="hd-dd-header">Filter by Status</div>
							<div class="hd-dd-item selected" data-val="">All Statuses</div>
							<div class="hd-dd-divider"></div>
							<div class="hd-dd-item" data-val="Open">Open</div>
							<div class="hd-dd-item" data-val="Replied">Replied</div>
							<div class="hd-dd-item" data-val="Resolved">Resolved</div>
							<div class="hd-dd-item" data-val="Closed">Closed</div>
						</div>
					</div>
					<div style="position:relative">
						<button class="hd-btn" id="hd-priority-btn">🚦 All Priorities</button>
						<div class="hd-dropdown" id="hd-priority-dd" style="display:none">
							<div class="hd-dd-header">Filter by Priority</div>
							<div class="hd-dd-item selected" data-val="">All Priorities</div>
							<div class="hd-dd-divider"></div>
							<div class="hd-dd-item" data-val="Urgent">Urgent</div>
							<div class="hd-dd-item" data-val="High">High</div>
							<div class="hd-dd-item" data-val="Medium">Medium</div>
							<div class="hd-dd-item" data-val="Low">Low</div>
						</div>
					</div>
					<button class="hd-btn" id="hd-date-btn">📅 This Month</button>
					<button class="hd-btn" id="hd-refresh">↻ Refresh</button>
				</div>
			</div>
			<div id="hd-body"><div class="hd-loading">Loading helpdesk data…</div></div>
			<div class="hd-footer" id="hd-footer"></div>
		</div>
	`);

	// ── Screen tabs ───────────────────────────────────────────────────────
	$(document).on("click", ".hd-screen-tab", function () {
		_hd.current_screen = parseInt($(this).data("screen"));
		$(".hd-screen-tab").removeClass("active");
		$(this).addClass("active");
		$(".hd-screen").removeClass("active");
		$("#hd-screen-" + _hd.current_screen).addClass("active");
	});

	// ── Agent dropdown ────────────────────────────────────────────────────
	$("#hd-agent-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#hd-agent-dd");
		if ($dd.is(":visible")) { $dd.hide(); return; }
		$dd.html('<div class="hd-dd-item hd-muted">Loading…</div>').show();
		frappe.call({
			method: "bsgroup.bs_group.page.hd_ticket_das.hd_ticket_das.get_helpdesk_agents",
			callback: function (r) {
				const agents = r.message || [];
				let html = '<div class="hd-dd-header">Filter by Agent</div>';
				html += `<div class="hd-dd-item${!_hd.selected_agent ? " selected" : ""}" data-agent="">All Agents</div>`;
				html += '<div class="hd-dd-divider"></div>';
				agents.forEach(a => {
					const name  = a.agent || "";
					const label = name.split("@")[0].replace(/\./g, " ").replace(/\b\w/g, c => c.toUpperCase());
					const sel   = _hd.selected_agent === name ? " selected" : "";
					html += `<div class="hd-dd-item${sel}" data-agent="${name}" title="${name}">${label}</div>`;
				});
				$dd.html(html);
			},
		});
	});
	$(document).on("click", "#hd-agent-dd .hd-dd-item", function () {
		_hd.selected_agent = $(this).data("agent") || null;
		$("#hd-agent-btn").text("👤 " + $(this).text().trim()).toggleClass("filter-active", !!_hd.selected_agent);
		$("#hd-agent-dd").hide();
		load_hd_dashboard();
	});

	// ── Status dropdown ───────────────────────────────────────────────────
	$("#hd-status-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#hd-status-dd");
		$dd.is(":visible") ? $dd.hide() : $dd.show();
	});
	$(document).on("click", "#hd-status-dd .hd-dd-item", function () {
		_hd.selected_status = $(this).data("val") || null;
		$("#hd-status-dd .hd-dd-item").removeClass("selected");
		$(this).addClass("selected");
		$("#hd-status-btn").text("📋 " + $(this).text().trim()).toggleClass("filter-active", !!_hd.selected_status);
		$("#hd-status-dd").hide();
		load_hd_dashboard();
	});

	// ── Priority dropdown ─────────────────────────────────────────────────
	$("#hd-priority-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#hd-priority-dd");
		$dd.is(":visible") ? $dd.hide() : $dd.show();
	});
	$(document).on("click", "#hd-priority-dd .hd-dd-item", function () {
		_hd.selected_priority = $(this).data("val") || null;
		$("#hd-priority-dd .hd-dd-item").removeClass("selected");
		$(this).addClass("selected");
		$("#hd-priority-btn").text("🚦 " + $(this).text().trim()).toggleClass("filter-active", !!_hd.selected_priority);
		$("#hd-priority-dd").hide();
		load_hd_dashboard();
	});

	// ── Date filter ───────────────────────────────────────────────────────
	$("#hd-date-btn").on("click", function () {
		frappe.prompt(
			[
				{ fieldname: "from_date", label: "From Date", fieldtype: "Date", reqd: 1,
				  default: _hd.from_date || frappe.datetime.month_start() },
				{ fieldname: "to_date",   label: "To Date",   fieldtype: "Date", reqd: 1,
				  default: _hd.to_date   || frappe.datetime.month_end() },
			],
			function (vals) {
				_hd.from_date = vals.from_date;
				_hd.to_date   = vals.to_date;
				const label = frappe.datetime.str_to_user(vals.from_date) + " → " + frappe.datetime.str_to_user(vals.to_date);
				$("#hd-date-btn").text("📅 " + label).addClass("filter-active");
				load_hd_dashboard();
			},
			"Select Date Range", "Apply"
		);
	});

	// ── Close dropdowns on outside click ─────────────────────────────────
	$(document).on("click", function (e) {
		if (!$(e.target).closest("#hd-agent-btn,#hd-agent-dd").length)       $("#hd-agent-dd").hide();
		if (!$(e.target).closest("#hd-status-btn,#hd-status-dd").length)     $("#hd-status-dd").hide();
		if (!$(e.target).closest("#hd-priority-btn,#hd-priority-dd").length) $("#hd-priority-dd").hide();
	});

	$("#hd-refresh").on("click", () => load_hd_dashboard());
	load_hd_dashboard();

	// ── TV mode (?tv=1) ────────────────────────────────────────────────────
	if (new URLSearchParams(window.location.search).get("tv") === "1") {
		// Hide Frappe chrome for full-screen display
		document.querySelector(".navbar-expand")?.style.setProperty("display", "none", "important");
		document.querySelector(".layout-side-section")?.style.setProperty("display", "none", "important");
		document.querySelector(".page-head")?.style.setProperty("display", "none", "important");
		document.querySelector(".layout-main-section-wrapper")
			?.style.setProperty("padding", "0", "important");

		if (!document.getElementById("hd-tv-styles")) {
			const tvStyle = document.createElement("style");
			tvStyle.id = "hd-tv-styles";
			tvStyle.textContent = `
				.hd-wrap          { padding: 28px 36px !important; gap: 22px !important; }
				.hd-title-wrap h1 { font-size: clamp(32px, 3vw, 52px) !important; }
				.hd-subtitle      { font-size: 17px !important; }
				.hd-kpi-label     { font-size: 16px !important; margin-bottom: 14px !important; }
				.hd-kpi-value     { font-size: clamp(64px, 5.5vw, 100px) !important; margin-bottom: 12px !important; }
				.hd-kpi-note      { font-size: 15px !important; }
				.hd-kpi-card      { padding: 26px 28px !important; }
				.hd-card-head h2  { font-size: clamp(22px, 2vw, 30px) !important; }
				.hd-card-note     { font-size: 15px !important; }
				.hd-table         { font-size: 17px !important; }
				.hd-table th      { font-size: 13px !important; padding: 10px 12px !important; }
				.hd-table td      { padding: 14px 12px !important; }
				.hd-badge         { font-size: 13px !important; padding: 5px 13px !important; }
				.hd-btn, .hd-screen-tab { font-size: 15px !important; padding: 10px 20px !important; }
			`;
			document.head.appendChild(tvStyle);
		}

		// Auto-refresh every 60 seconds
		setInterval(() => load_hd_dashboard(), 60000);
	}
};

// ── Helpers ────────────────────────────────────────────────────────────────
function _badge(text, cls) {
	return `<span class="hd-badge ${cls}">${text}</span>`;
}
function hd_priority_badge(p) {
	const m = { Urgent:"hd-b-red", High:"hd-b-orange", Medium:"hd-b-blue", Low:"hd-b-gray" };
	return _badge(p || "—", m[p] || "hd-b-gray");
}
function hd_status_badge(s) {
	const m = { Open:"hd-b-cyan", Replied:"hd-b-blue", Resolved:"hd-b-green", Closed:"hd-b-gray" };
	return _badge(s || "—", m[s] || "hd-b-gray");
}
function hd_sla_badge(s) {
	const m = { Fulfilled:"hd-b-green", Failed:"hd-b-red", "First Response Due":"hd-b-orange", "Resolution Due":"hd-b-orange" };
	return _badge(s || "—", m[s] || "hd-b-gray");
}
function hd_link(name, label) {
	return `<a class="hd-link" href="/app/hd-ticket/${encodeURIComponent(name)}" target="_blank">${label || "#" + name}</a>`;
}
function hd_mins(secs) {
	if (!secs) return "—";
	const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60);
	return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// ── Main loader ────────────────────────────────────────────────────────────
function load_hd_dashboard() {
	$("#hd-refresh").prop("disabled", true).text("Loading…");
	$("#hd-body").html('<div class="hd-loading">Fetching helpdesk data…</div>');
	frappe.call({
		method: "bsgroup.bs_group.page.hd_ticket_das.hd_ticket_das.get_dashboard_data",
		args: {
			selected_agent:    _hd.selected_agent    || null,
			from_date:         _hd.from_date         || null,
			to_date:           _hd.to_date           || null,
			selected_status:   _hd.selected_status   || null,
			selected_priority: _hd.selected_priority || null,
		},
		callback: function (r) {
			$("#hd-refresh").prop("disabled", false).text("↻ Refresh");
			if (r.exc || !r.message) {
				$("#hd-body").html(`<div class="hd-loading hd-red">Failed to load. Check console.</div>`);
				return;
			}
			render_hd_dashboard(r.message);
		},
	});
}

// ── Renderer ───────────────────────────────────────────────────────────────
function render_hd_dashboard(d) {
	const k = d.kpis || {};
	if (!d.is_manager) $("#hd-agent-btn").hide();

	$("#hd-subtitle").text("BS Group · ERPNext Helpdesk · " + (d.generated_at || ""));
	$("#hd-footer").text("Generated: " + (d.generated_at || ""));

	// ── SLA percentages ────────────────────────────────────────────────────
	const total_sla  = (k.sla_fulfilled || 0) + (k.sla_failed || 0) + (k.sla_near_breach || 0);
	const sla_ok_pct   = total_sla ? Math.round(k.sla_fulfilled   / total_sla * 100) : 0;
	const sla_near_pct = total_sla ? Math.round(k.sla_near_breach / total_sla * 100) : 0;
	const sla_fail_pct = total_sla ? Math.round(k.sla_failed      / total_sla * 100) : 0;

	// ── Category meters ────────────────────────────────────────────────────
	const cat_data   = d.category_data || [];
	const cat_max    = cat_data.length ? Math.max(...cat_data.map(x => x.count)) : 1;
	const cat_colors = ["blue","purple","red","green","orange","cyan"];
	let cat_meters   = "";
	cat_data.slice(0, 6).forEach((row, i) => {
		const pct = cat_max > 0 ? Math.round(row.count / cat_max * 100) : 0;
		cat_meters += `
		<div class="hd-meter">
			<div class="hd-meter-head"><span>${row.category || "Unspecified"}</span><span>${row.count}</span></div>
			<div class="hd-bar"><div class="hd-fill ${cat_colors[i % cat_colors.length]}" style="width:${pct}%"></div></div>
		</div>`;
	});
	if (!cat_meters) cat_meters = `<div class="hd-muted" style="font-size:12px">No category data</div>`;

	// ── Priority queue rows ────────────────────────────────────────────────
	let pq_rows = "";
	(d.priority_queue || []).forEach(row => {
		let na_date_html = "<span class='hd-muted'>—</span>";
		if (row.custom_next_action_date) {
			const today_str = frappe.datetime.get_today();
			const d_str = row.custom_next_action_date.split(" ")[0];
			const cls = d_str < today_str ? "hd-red" : d_str === today_str ? "hd-orange" : "hd-green";
			na_date_html = `<span class="${cls}" style="font-weight:600">${frappe.datetime.str_to_user(d_str)}</span>`;
		}
		pq_rows += `<tr>
			<td>${hd_link(row.name, "#" + row.name)}</td>
			<td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${row.subject || "—"}</td>
			<td>${row.custom_category || "—"}</td>
			<td>${hd_priority_badge(row.priority)}</td>
			<td>${hd_status_badge(row.status)}</td>
			<td>${hd_sla_badge(row.agreement_status)}</td>
			<td class="hd-muted" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px">${row.custom_next_action || "—"}</td>
			<td>${na_date_html}</td>
			<td class="hd-muted" style="font-size:11px;white-space:nowrap">${row.age_display || "—"}</td>
		</tr>`;
	});
	if (!pq_rows) pq_rows = `<tr><td colspan="9" class="hd-muted" style="text-align:center;padding:18px">✓ No urgent tickets</td></tr>`;

	// ── Agent rows ─────────────────────────────────────────────────────────
	let agent_rows = "";
	(d.agent_data || []).forEach(row => {
		const cls = row.sla_pct >= 90 ? "hd-green" : row.sla_pct >= 70 ? "hd-orange" : "hd-red";
		agent_rows += `<tr>
			<td style="font-weight:700">${row.agent_short}</td>
			<td class="hd-cyan" style="font-weight:700">${row.open_count}</td>
			<td class="hd-orange">${row.replied_count}</td>
			<td class="hd-red">${row.overdue_count}</td>
			<td class="${cls}" style="font-weight:700">${row.sla_pct > 0 ? row.sla_pct + "%" : "—"}</td>
			<td class="hd-muted" style="font-size:11px">${hd_mins(row.avg_first_response)}</td>
		</tr>`;
	});
	if (!agent_rows) agent_rows = `<tr><td colspan="6" class="hd-muted" style="text-align:center;padding:16px">No agent data</td></tr>`;

	// ── Category rows ──────────────────────────────────────────────────────
	let cat_rows = "";
	(d.category_data || []).forEach(row => {
		const alert = row.count >= 10
			? _badge("High Volume","hd-b-red")
			: row.count >= 5 ? _badge("Monitor","hd-b-orange") : _badge("Normal","hd-b-gray");
		cat_rows += `<tr>
			<td>${row.category || "Unspecified"}</td>
			<td style="font-weight:700">${row.count}</td>
			<td>${alert}</td>
			<td>${hd_sla_badge(row.sla_status || "")}</td>
		</tr>`;
	});
	if (!cat_rows) cat_rows = `<tr><td colspan="4" class="hd-muted" style="text-align:center;padding:16px">No categories</td></tr>`;

	// ── Activity items ─────────────────────────────────────────────────────
	let activity = "";
	(d.recent_activity || []).forEach(row => {
		activity += `<li>
			${hd_link(row.name, "#" + row.name)}
			<span style="margin-left:5px">${row.subject || ""}</span>
			<div class="hd-muted" style="margin-top:2px">${row.customer || ""} · ${row.age_display || ""}</div>
		</li>`;
	});
	if (!activity) activity = `<li class="hd-muted">No recent activity</li>`;

	// ── Group meters ───────────────────────────────────────────────────────
	const grp_data = d.agent_group_data || [];
	const grp_max  = grp_data.length ? Math.max(...grp_data.map(x => x.count)) : 1;
	let grp_meters = "";
	grp_data.slice(0, 5).forEach((row, i) => {
		const pct = grp_max > 0 ? Math.round(row.count / grp_max * 100) : 0;
		grp_meters += `
		<div class="hd-meter">
			<div class="hd-meter-head"><span>${row.agent_group || "Unassigned"}</span><span>${row.count}</span></div>
			<div class="hd-bar"><div class="hd-fill ${cat_colors[i % cat_colors.length]}" style="width:${pct}%"></div></div>
		</div>`;
	});
	if (!grp_meters) grp_meters = `<div class="hd-muted" style="font-size:12px">No group data</div>`;

	// ── Customer rows ──────────────────────────────────────────────────────
	let cust_rows = "";
	(d.customer_data || []).forEach(row => {
		cust_rows += `<tr>
			<td style="font-weight:700">${row.customer || "—"}</td>
			<td class="hd-cyan" style="font-weight:700">${row.total}</td>
			<td class="hd-red">${row.open_count}</td>
			<td>${hd_sla_badge(row.agreement_status || "")}</td>
			<td class="hd-muted" style="font-size:11px">${row.last_ticket || "—"}</td>
		</tr>`;
	});
	if (!cust_rows) cust_rows = `<tr><td colspan="5" class="hd-muted" style="text-align:center;padding:16px">No customer data</td></tr>`;

	// ── Priority breakdown rows ────────────────────────────────────────────
	const pri_max = Math.max(k.urgent_count||0, k.high_count||0, k.replied_count||0, k.unassigned_count||0, 1);
	const pri_items = [
		{ label:"Urgent",     val: k.urgent_count||0,     cls:"hd-fill red",    color:"hd-red"    },
		{ label:"High",       val: k.high_count||0,       cls:"hd-fill orange", color:"hd-orange" },
		{ label:"Replied",    val: k.replied_count||0,    cls:"hd-fill blue",   color:"hd-blue"   },
		{ label:"Unassigned", val: k.unassigned_count||0, cls:"hd-fill cyan",   color:"hd-cyan"   },
		{ label:"Next Action Overdue", val: k.next_action_overdue||0, cls:"hd-fill purple", color:"hd-purple" },
		{ label:"Due Today",  val: k.next_action_today||0, cls:"hd-fill orange",color:"hd-orange" },
	];
	let pri_html = "";
	pri_items.forEach(item => {
		const pct = Math.round(item.val / pri_max * 100);
		pri_html += `<div class="hd-pri-row">
			<div class="hd-pri-label">${item.label}</div>
			<div class="hd-pri-count ${item.color}">${item.val}</div>
			<div class="hd-pri-bar-wrap">
				<div class="hd-bar"><div class="${item.cls}" style="width:${pct}%"></div></div>
			</div>
		</div>`;
	});

	// ══════════════════════════════════════════════════════════════════════
	//  SCREEN 1: Live Operations
	// ══════════════════════════════════════════════════════════════════════
	const screen1 = `
	<div id="hd-screen-0" class="hd-screen ${_hd.current_screen === 0 ? "active" : ""}">

		<!-- KPI Row -->
		<div class="hd-kpi-row">
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Open Tickets</div>
				<div class="hd-kpi-value hd-cyan">${k.open_count}</div>
				<div class="hd-kpi-note">Currently open</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Urgent / High</div>
				<div class="hd-kpi-value hd-red">${k.urgent_high_count}</div>
				<div class="hd-kpi-note">Immediate attention</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">SLA Breached</div>
				<div class="hd-kpi-value hd-red">${k.sla_failed}</div>
				<div class="hd-kpi-note">Agreement: Failed</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Near Breach</div>
				<div class="hd-kpi-value hd-orange">${k.sla_near_breach}</div>
				<div class="hd-kpi-note">Response / Resolution Due</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Resolved This Month</div>
				<div class="hd-kpi-value hd-green">${k.resolved_month}</div>
				<div class="hd-kpi-note">Closed + Resolved</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Avg First Response</div>
				<div class="hd-kpi-value" style="font-size:clamp(18px,1.6vw,28px)">${hd_mins(k.avg_first_response)}</div>
				<div class="hd-kpi-note">This month</div>
			</div>
		</div>

		<!-- Priority Queue + SLA + Mix -->
		<div class="hd-row hd-cols-2-1">
			<div class="hd-card">
				<div class="hd-card-head">
					<h2>⚡ Priority Action Queue</h2>
					<div class="hd-card-note">Urgent & High — Immediate attention</div>
				</div>
				<table class="hd-table">
					<thead>
						<tr><th>ID</th><th>Subject</th><th>Category</th><th>Priority</th><th>Status</th><th>SLA</th><th>Next Action</th><th>Due Date</th><th>Age</th></tr>
					</thead>
					<tbody>${pq_rows}</tbody>
				</table>
				<div class="hd-strip">
					<div class="hd-strip-item">
						<div class="sv hd-red">${k.urgent_count || 0}</div>
						<div class="sl">Urgent</div>
					</div>
					<div class="hd-strip-item">
						<div class="sv hd-orange">${k.high_count || 0}</div>
						<div class="sl">High</div>
					</div>
					<div class="hd-strip-item">
						<div class="sv hd-cyan">${k.unassigned_count || 0}</div>
						<div class="sl">Unassigned</div>
					</div>
				</div>
			</div>

			<div class="hd-stack">
				<div class="hd-card">
					<div class="hd-card-head">
						<h2>🛡️ SLA Health</h2>
						<div class="hd-card-note">Live summary</div>
					</div>
					<div class="hd-meter">
						<div class="hd-meter-head"><span>Within SLA</span><span class="hd-green">${sla_ok_pct}%</span></div>
						<div class="hd-bar"><div class="hd-fill green" style="width:${sla_ok_pct}%"></div></div>
					</div>
					<div class="hd-meter">
						<div class="hd-meter-head"><span>Near Breach</span><span class="hd-orange">${sla_near_pct}%</span></div>
						<div class="hd-bar"><div class="hd-fill orange" style="width:${sla_near_pct}%"></div></div>
					</div>
					<div class="hd-meter">
						<div class="hd-meter-head"><span>Breached</span><span class="hd-red">${sla_fail_pct}%</span></div>
						<div class="hd-bar"><div class="hd-fill red" style="width:${sla_fail_pct}%"></div></div>
					</div>
				</div>
				<div class="hd-card">
					<div class="hd-card-head">
						<h2>🗂️ Ticket Mix</h2>
						<div class="hd-card-note">By category</div>
					</div>
					${cat_meters}
				</div>
			</div>
		</div>

	</div>`;

	// ══════════════════════════════════════════════════════════════════════
	//  SCREEN 2: Analytics
	// ══════════════════════════════════════════════════════════════════════
	const screen2 = `
	<div id="hd-screen-1" class="hd-screen ${_hd.current_screen === 1 ? "active" : ""}">

		<!-- KPI Row -->
		<div class="hd-kpi-row">
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Total Tickets</div>
				<div class="hd-kpi-value hd-cyan">${k.total_count}</div>
				<div class="hd-kpi-note">Selected range</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Replied</div>
				<div class="hd-kpi-value hd-blue">${k.replied_count}</div>
				<div class="hd-kpi-note">Awaiting customer</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Unassigned</div>
				<div class="hd-kpi-value hd-orange">${k.unassigned_count}</div>
				<div class="hd-kpi-note">No agent assigned</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Next Action Overdue</div>
				<div class="hd-kpi-value hd-red">${k.next_action_overdue}</div>
				<div class="hd-kpi-note">Action date passed</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Next Action Today</div>
				<div class="hd-kpi-value hd-orange">${k.next_action_today}</div>
				<div class="hd-kpi-note">Due today</div>
			</div>
			<div class="hd-kpi-card">
				<div class="hd-kpi-label">Via Portal</div>
				<div class="hd-kpi-value hd-purple">${k.portal_count}</div>
				<div class="hd-kpi-note">Customer portal</div>
			</div>
		</div>

		<!-- Row 1: Agent Workload | Category Summary -->
		<div class="hd-row hd-cols-2eq">
			<div class="hd-card">
				<div class="hd-card-head">
					<h2>👷 Agent Workload</h2>
					<div class="hd-card-note">Distribution snapshot</div>
				</div>
				<table class="hd-table">
					<thead>
						<tr><th>Agent</th><th>Open</th><th>Replied</th><th>Overdue</th><th>SLA %</th><th>Avg Resp</th></tr>
					</thead>
					<tbody>${agent_rows}</tbody>
				</table>
			</div>
			<div class="hd-card">
				<div class="hd-card-head">
					<h2>🗂️ Category Summary</h2>
					<div class="hd-card-note">Volume & alert flags</div>
				</div>
				<table class="hd-table">
					<thead>
						<tr><th>Category</th><th>Count</th><th>Alert</th><th>SLA</th></tr>
					</thead>
					<tbody>${cat_rows}</tbody>
				</table>
			</div>
		</div>

		<!-- Row 2: Recent Activity | Top Customers by Volume -->
		<div class="hd-row hd-cols-2eq">
			<div class="hd-card">
				<div class="hd-card-head">
					<h2>🕐 Recent Activity</h2>
					<div class="hd-card-note">Last modified</div>
				</div>
				<ul class="hd-activity">${activity}</ul>
			</div>
			<div class="hd-card">
				<div class="hd-card-head">
					<h2>🏢 Top Customers by Volume</h2>
					<div class="hd-card-note">Accounts needing focus</div>
				</div>
				<table class="hd-table">
					<thead>
						<tr><th>Customer</th><th>Total</th><th>Open</th><th>SLA</th><th>Latest</th></tr>
					</thead>
					<tbody>${cust_rows}</tbody>
				</table>
			</div>
		</div>

		<!-- Row 3: Priority Breakdown | Tickets by Agent Group -->
		<div class="hd-row hd-cols-2eq">
			<div class="hd-card">
				<div class="hd-card-head">
					<h2>🚦 Priority Breakdown</h2>
					<div class="hd-card-note">Open tickets by priority</div>
				</div>
				${pri_html}
			</div>
			<div class="hd-card">
				<div class="hd-card-head">
					<h2>📦 Tickets by Agent Group</h2>
					<div class="hd-card-note">Team load</div>
				</div>
				${grp_meters}
			</div>
		</div>

	</div>`;

	$("#hd-body").html(screen1 + screen2);
}
