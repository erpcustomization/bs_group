// frappe.pages['weekly-customer-das'].on_page_load = function(wrapper) {
// 	var page = frappe.ui.make_app_page({
// 		parent: wrapper,
// 		title: 'Weekly Customer Dashboard',
// 		single_column: true
// 	});
// }

// ── Dashboard state ────────────────────────────────────────────────────────
const _pd = {
	selected_project:  null,
	project_label:     "Select Project",
	from_date:         null,
	to_date:           null,
	selected_status:   null,
	status_label:      "All Statuses",
};

frappe.pages["weekly-customer-das"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title:  "Weekly Customer Dashboard",
		single_column: true,
	});

	// ── Inject CSS ────────────────────────────────────────────────────────
	if (!document.getElementById("pd-styles")) {
		const style = document.createElement("style");
		style.id = "pd-styles";
		style.textContent = `
			:root {
				--pd-brand:    #0f2d58;
				--pd-brand2:   #1e5bb8;
				--pd-accent:   #4f8df2;
				--pd-green:    #16a34a;
				--pd-amber:    #d97706;
				--pd-red:      #dc2626;
				--pd-muted:    #6b7280;
				--pd-line:     #e5e7eb;
				--pd-panel:    #ffffff;
				--pd-bg:       #f4f7fb;
				--pd-text:     #172033;
				--pd-soft-blue:#eef4ff;
				--pd-soft-grn: #edf9f0;
				--pd-soft-amb: #fff7eb;
				--pd-shadow:   0 12px 30px rgba(17,24,39,0.08);
				--pd-radius:   18px;
			}
			.pd-wrap {
				padding: 20px 24px 40px;
				background: linear-gradient(180deg,#eef3fa 0%,#f8fafc 100%);
				min-height: 100vh;
				font-family: Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;
				color: var(--pd-text);
			}

			/* ── Hero ── */
			.pd-hero {
				background: linear-gradient(135deg,#0f2d58 0%,#18478f 100%);
				color: #fff;
				border-radius: 24px;
				padding: 30px;
				box-shadow: var(--pd-shadow);
				display: grid;
				grid-template-columns: 1.4fr 1fr;
				gap: 24px;
				margin-bottom: 20px;
			}
			.pd-brand-row {
				display: flex;
				align-items: center;
				gap: 14px;
				margin-bottom: 20px;
			}
			.pd-logo {
				width: 52px; height: 52px;
				border-radius: 14px;
				background: rgba(255,255,255,0.14);
				border: 1px solid rgba(255,255,255,0.18);
				display: flex; align-items: center; justify-content: center;
				font-size: 22px; font-weight: 700;
				backdrop-filter: blur(4px);
			}
			.pd-eyebrow {
				font-size: 12px; letter-spacing: 0.18em;
				text-transform: uppercase; opacity: 0.78; margin-bottom: 4px;
			}
			.pd-hero-title { margin: 0; font-size: 28px; font-weight: 700; line-height: 1.2; color: #fff; }
			.pd-hero-sub {
				margin-top: 10px; font-size: 14px; line-height: 1.7;
				color: rgba(255,255,255,0.84);
			}
			.pd-status-pill {
				display: inline-flex; align-items: center; gap: 8px;
				padding: 7px 14px; border-radius: 999px; font-size: 13px; font-weight: 700;
				background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.22);
				margin-top: 14px;
			}
			.pd-dot {
				width: 9px; height: 9px; border-radius: 50%;
				background: #fbbf24; box-shadow: 0 0 0 6px rgba(251,191,36,0.2);
			}
			.pd-dot.green { background: #4ade80; box-shadow: 0 0 0 6px rgba(74,222,128,0.2); }
			.pd-dot.red   { background: #f87171; box-shadow: 0 0 0 6px rgba(248,113,113,0.2); }

			/* ── Hero filter buttons ── */
			#pd-proj-input::placeholder { color: rgba(255,255,255,0.55); }
			.pd-filter-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
			.pd-btn {
				background: rgba(255,255,255,0.16);
				border: 1px solid rgba(255,255,255,0.26);
				color: #fff; padding: 8px 16px;
				border-radius: 999px; cursor: pointer;
				font-size: 13px; font-weight: 600;
				transition: background .2s; white-space: nowrap; position: relative;
			}
			.pd-btn:hover      { background: rgba(255,255,255,0.26); }
			.pd-btn.active     { background: rgba(255,255,255,0.34); border-color: rgba(255,255,255,0.5); }
			.pd-btn.pd-fa      { background: rgba(255,220,80,0.22); border-color: rgba(255,220,80,0.45); }

			/* ── Hero meta cards ── */
			.pd-hero-meta {
				display: grid; grid-template-columns: repeat(2,1fr); gap: 14px; align-self: start;
			}
			.pd-meta-card {
				background: rgba(255,255,255,0.10);
				border: 1px solid rgba(255,255,255,0.14);
				border-radius: 18px; padding: 16px; min-height: 88px;
			}
			.pd-meta-label {
				font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
				opacity: .75; margin-bottom: 10px;
			}
			.pd-meta-value { font-size: 16px; font-weight: 600; line-height: 1.4; }

			/* ── Dropdown ── */
			.pd-dropdown {
				position: absolute; top: calc(100% + 6px); left: 0;
				background: #fff; border: 1px solid var(--pd-line);
				border-radius: 14px; box-shadow: 0 8px 28px rgba(17,24,39,0.13);
				min-width: 260px; z-index: 9999; overflow: hidden; color: var(--pd-text);
				max-height: 320px; overflow-y: auto;
			}
			.pd-dd-header {
				padding: 8px 14px 4px; font-size: 11px; font-weight: 700;
				color: var(--pd-muted); text-transform: uppercase; letter-spacing: .06em;
				position: sticky; top: 0; background: #fff; border-bottom: 1px solid #f3f4f6;
			}
			.pd-dd-item {
				padding: 9px 14px; font-size: 13px; cursor: pointer; transition: background .15s;
			}
			.pd-dd-item:hover    { background: #eef4ff; color: var(--pd-brand2); }
			.pd-dd-item.selected { background: #dbeafe; color: var(--pd-brand2); font-weight: 700; }
			.pd-dd-divider       { border-top: 1px solid #f0f4f5; margin: 4px 0; }

			/* ── Summary KPI grid ── */
			.pd-kpi-grid {
				display: grid; grid-template-columns: repeat(4,1fr); gap: 18px;
				margin-bottom: 20px;
			}
			.pd-kpi-card {
				background: var(--pd-panel); border: 1px solid rgba(17,24,39,0.06);
				border-radius: var(--pd-radius); box-shadow: var(--pd-shadow); padding: 22px;
			}
			.pd-kpi-label { font-size: 13px; color: var(--pd-muted); margin-bottom: 12px; }
			.pd-kpi-value { font-size: 32px; font-weight: 800; color: var(--pd-text); margin-bottom: 8px; }
			.pd-kpi-note  { font-size: 13px; color: var(--pd-muted); line-height: 1.5; }
			.pd-progress-bar {
				width: 100%; height: 10px; background: #e8edf5;
				border-radius: 999px; overflow: hidden; margin-top: 12px;
			}
			.pd-progress-fill {
				height: 100%; background: linear-gradient(90deg,var(--pd-brand2),var(--pd-accent));
				border-radius: 999px; transition: width .6s ease;
			}
			.pd-progress-fill.green { background: linear-gradient(90deg,#34d399,var(--pd-green)); }
			.pd-progress-fill.amber { background: linear-gradient(90deg,#fbbf24,var(--pd-amber)); }
			.pd-progress-fill.red   { background: linear-gradient(90deg,#f87171,var(--pd-red)); }

			/* ── Main two-column layout ── */
			.pd-main-grid {
				display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 18px;
			}
			.pd-col { display: grid; gap: 18px; align-content: start; }

			/* ── Panel ── */
			.pd-panel {
				background: var(--pd-panel);
				border: 1px solid rgba(17,24,39,0.06);
				border-radius: var(--pd-radius);
				box-shadow: var(--pd-shadow);
				padding: 24px;
			}
			.pd-panel h2 { margin: 0 0 6px; font-size: 18px; font-weight: 700; color: var(--pd-text); }
			.pd-panel .pd-desc { color: var(--pd-muted); font-size: 13px; margin-bottom: 16px; line-height: 1.6; }

			/* ── List items ── */
			.pd-list { display: grid; gap: 12px; }
			.pd-list-item {
				border: 1px solid var(--pd-line); border-radius: 16px;
				padding: 14px 16px; display: flex; gap: 14px; align-items: flex-start;
			}
			.pd-icon {
				width: 36px; height: 36px; border-radius: 12px; flex: 0 0 36px;
				display: flex; align-items: center; justify-content: center;
				font-size: 15px; font-weight: 700;
			}
			.pd-icon.blue   { background: var(--pd-soft-blue); color: var(--pd-brand2); }
			.pd-icon.green  { background: var(--pd-soft-grn);  color: var(--pd-green);  }
			.pd-icon.amber  { background: var(--pd-soft-amb);  color: var(--pd-amber);  }
			.pd-icon.red    { background: #fee2e2; color: var(--pd-red); }
			.pd-item-title  { font-size: 14px; font-weight: 700; margin-bottom: 4px; color: var(--pd-text); }
			.pd-item-text   { font-size: 13px; color: var(--pd-muted); line-height: 1.6; }

			/* ── Scope table ── */
			.pd-scope-table { width: 100%; border-collapse: collapse; font-size: 13px; }
			.pd-scope-table th, .pd-scope-table td {
				padding: 10px 10px; border-bottom: 1px solid #f0f4f5;
				text-align: left; vertical-align: middle;
			}
			.pd-scope-table th {
				color: var(--pd-muted); font-weight: 700; font-size: 11px;
				text-transform: uppercase; letter-spacing: .05em;
			}
			.pd-scope-table tr:last-child td { border-bottom: none; }
			.pd-scope-table tr:hover td { background: #f8fafc; }
			.pd-scope-pct { font-weight: 700; color: var(--pd-text); }

			/* ── Mini progress ── */
			.pd-mini-bar { height: 8px; background: #e8edf5; border-radius: 999px; overflow: hidden; min-width: 80px; }
			.pd-mini-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg,var(--pd-brand2),var(--pd-accent)); }
			.pd-mini-fill.done  { background: linear-gradient(90deg,#34d399,var(--pd-green)); }
			.pd-mini-fill.mid   { background: linear-gradient(90deg,var(--pd-brand2),var(--pd-accent)); }
			.pd-mini-fill.low   { background: linear-gradient(90deg,#fbbf24,var(--pd-amber)); }
			.pd-mini-fill.none  { background: linear-gradient(90deg,#f87171,var(--pd-red)); }

			/* ── Milestone bars ── */
			.pd-milestones { display: grid; gap: 14px; }
			.pd-ms-row { display: grid; grid-template-columns: 120px 1fr 44px; align-items: center; gap: 10px; font-size: 13px; }
			.pd-ms-label { color: var(--pd-text); font-weight: 600; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.pd-ms-track { height: 10px; background: #e8edf5; border-radius: 999px; overflow: hidden; }
			.pd-ms-fill  { height: 100%; border-radius: 999px; background: linear-gradient(90deg,var(--pd-brand2),var(--pd-accent)); }
			.pd-ms-fill.done  { background: linear-gradient(90deg,#34d399,var(--pd-green)); }
			.pd-ms-fill.amber { background: linear-gradient(90deg,#fbbf24,var(--pd-amber)); }
			.pd-ms-fill.red   { background: linear-gradient(90deg,#f87171,var(--pd-red)); }
			.pd-ms-pct { font-size: 12px; font-weight: 700; color: var(--pd-muted); text-align: right; }

			/* ── Badges ── */
			.pd-badge {
				display: inline-block; border-radius: 999px;
				padding: 3px 10px; font-size: 11px; font-weight: 700;
			}
			.pd-b-green  { background: #dcfce7; color: #15803d; }
			.pd-b-blue   { background: #dbeafe; color: #1d4ed8; }
			.pd-b-amber  { background: #fef3c7; color: #b45309; }
			.pd-b-red    { background: #fee2e2; color: #b91c1c; }
			.pd-b-gray   { background: #f3f4f6; color: #374151; }
			.pd-b-purple { background: #ede9fe; color: #6d28d9; }

			/* ── Footer ── */
			.pd-footer { text-align: center; margin-top: 28px; color: var(--pd-muted); font-size: 12px; }

			/* ── Loading / Empty ── */
			.pd-loading { text-align: center; padding: 60px; color: var(--pd-muted); font-size: 14px; }
			.pd-empty   { color: var(--pd-muted); font-size: 13px; padding: 12px 0; }

			/* ── Responsive ── */
			@media (max-width: 1100px) {
				.pd-kpi-grid  { grid-template-columns: repeat(2,1fr); }
				.pd-main-grid { grid-template-columns: 1fr; }
				.pd-hero      { grid-template-columns: 1fr; }
			}
			@media (max-width: 640px) {
				.pd-kpi-grid  { grid-template-columns: 1fr; }
				.pd-ms-row    { grid-template-columns: 90px 1fr 36px; }
			}
		`;
		document.head.appendChild(style);
	}

	// ── Shell HTML ─────────────────────────────────────────────────────────
	$(page.body).html(`
		<div class="pd-wrap">
			<div class="pd-hero">
				<div>
					<div class="pd-brand-row">
						<div class="pd-logo">🏗</div>
						<div>
							<div class="pd-eyebrow">Customer Weekly Report · Bits Secure IT</div>
							<div style="font-size:12px;opacity:.7" id="pd-company">—</div>
						</div>
					</div>

					<h1 class="pd-hero-title" id="pd-proj-name">Select a project to begin</h1>
					<div id="pd-proj-desc" style="font-size:13px;color:rgba(255,255,255,0.75);margin-top:6px;margin-bottom:2px;line-height:1.6;display:none"></div>
					<div class="pd-hero-sub" id="pd-proj-meta">Use the Project button below to load dashboard data.</div>
					<div id="pd-status-pill"></div>

					<div class="pd-filter-row">
						<!-- Project selector -->
						<div style="position:relative">
							<button class="pd-btn active" id="pd-proj-btn">📁 Select Project</button>
							<div class="pd-dropdown" id="pd-proj-dd" style="display:none">
								<div class="pd-dd-header">Select Project</div>
								<div style="padding:8px 10px;border-bottom:1px solid #f0f4f5;position:sticky;top:32px;background:#fff;z-index:1">
									<input id="pd-proj-input" type="text" placeholder="Search project…"
										autocomplete="off"
										style="width:100%;border:1px solid #e5e7eb;border-radius:8px;
										       padding:7px 10px;font-size:13px;outline:none;color:#172033;"
									/>
								</div>
								<div id="pd-proj-list"></div>
							</div>
						</div>

						<!-- Status filter -->
						<div style="position:relative">
							<button class="pd-btn" id="pd-status-btn">📋 All Statuses</button>
							<div class="pd-dropdown" id="pd-status-dd" style="display:none">
								<div class="pd-dd-header">Filter by Task Status</div>
								<div class="pd-dd-item selected" data-val="">All Statuses</div>
								<div class="pd-dd-divider"></div>
								<div class="pd-dd-item" data-val="Open">Open</div>
								<div class="pd-dd-item" data-val="Working">Working</div>
								<div class="pd-dd-item" data-val="Pending Review">Pending Review</div>
								<div class="pd-dd-item" data-val="Overdue">Overdue</div>
								<div class="pd-dd-item" data-val="Template">Template</div>
								<div class="pd-dd-item" data-val="Completed">Completed</div>
								<div class="pd-dd-item" data-val="Cancelled">Cancelled</div>
							</div>
						</div>

						<!-- Date range -->
						<button class="pd-btn" id="pd-date-btn">📅 This Week</button>

						<!-- Refresh -->
						<button class="pd-btn" id="pd-refresh">⟳ Refresh</button>

							<!-- Print -->
							<button class="pd-btn" id="pd-print-btn">🖨 Print</button>

							<!-- PDF -->
							<button class="pd-btn" id="pd-pdf-btn">⬇ PDF</button>
					</div>
				</div>

				<div class="pd-hero-meta">
					<div class="pd-meta-card">
						<div class="pd-meta-label">Reporting Period</div>
						<div class="pd-meta-value" id="hm-period">—</div>
					</div>
					<div class="pd-meta-card">
						<div class="pd-meta-label">Report Date</div>
						<div class="pd-meta-value" id="hm-date">—</div>
					</div>
					<div class="pd-meta-card">
						<div class="pd-meta-label">Customer</div>
						<div class="pd-meta-value" id="hm-pm" style="font-size:14px">—</div>
					</div>
					<div class="pd-meta-card">
						<div class="pd-meta-label">Overall Progress</div>
						<div class="pd-meta-value" id="hm-progress">—</div>
					</div>
				</div>
			</div>

			<div id="pd-body">
				<div class="pd-loading">Select a project to load the dashboard.</div>
			</div>

			<div class="pd-footer" id="pd-footer">Prepared by BITS Secure IT · Customer Weekly Dashboard</div>
		</div>
	`);

	// ── Project selector (button + searchable dropdown) ──────────────────
	let _proj_all  = [];
	let _proj_timer = null;

	function _render_proj_list(q) {
		const term = (q || "").toLowerCase();
		const list = term
			? _proj_all.filter(p =>
				(p.project_name || "").toLowerCase().includes(term) ||
				(p.name || "").toLowerCase().includes(term))
			: _proj_all;

		const $list = $("#pd-proj-list");
		if (!list.length) {
			$list.html('<div class="pd-dd-item" style="color:#9ca3af">No projects found</div>');
			return;
		}
		let html = "";
		list.forEach(p => {
			const sel = _pd.selected_project === p.name ? " selected" : "";
			html += `<div class="pd-dd-item${sel}" data-project="${p.name}" data-label="${p.project_name || p.name}">
				<div style="font-weight:600">${p.project_name || p.name}</div>
				<div style="font-size:11px;color:#9ca3af;margin-top:2px">${p.project_type || ""} · ${p.status || ""}</div>
			</div>`;
		});
		$list.html(html);
	}

	$("#pd-proj-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#pd-proj-dd");
		if ($dd.is(":visible")) { $dd.hide(); return; }
		$dd.show();
		$("#pd-proj-input").val("").focus();
		if (!_proj_all.length) {
			$("#pd-proj-list").html('<div class="pd-dd-item" style="color:#9ca3af">Loading…</div>');
			frappe.call({
				method: "bsgroup.bs_group.page.weekly_customer_das.weekly_customer_das.get_projects",
				callback: function (r) {
					_proj_all = r.message || [];
					_render_proj_list("");
				},
			});
		} else {
			_render_proj_list("");
		}
	});

	$(document).on("input", "#pd-proj-input", function () {
		clearTimeout(_proj_timer);
		const q = $(this).val();
		_proj_timer = setTimeout(() => _render_proj_list(q), 150);
	});

	$(document).on("click", "#pd-proj-list .pd-dd-item", function () {
		const proj  = $(this).data("project");
		const label = $(this).data("label");
		if (!proj) return;
		_pd.selected_project = proj;
		_pd.project_label    = label;
		$("#pd-proj-btn").text("📁 " + label).addClass("pd-fa");
		$("#pd-proj-dd").hide();
		load_dashboard();
	});

	// ── Status dropdown ────────────────────────────────────────────────────
	$("#pd-status-btn").on("click", function (e) {
		e.stopPropagation();
		const $dd = $("#pd-status-dd");
		$dd.is(":visible") ? $dd.hide() : $dd.show();
	});

	$(document).on("click", "#pd-status-dd .pd-dd-item", function () {
		_pd.selected_status = $(this).data("val") || null;
		_pd.status_label    = $(this).text().trim();
		$("#pd-status-dd .pd-dd-item").removeClass("selected");
		$(this).addClass("selected");
		$("#pd-status-btn").text("📋 " + _pd.status_label).toggleClass("pd-fa", !!_pd.selected_status);
		$("#pd-status-dd").hide();
		if (_pd.selected_project) load_dashboard();
	});

	// ── Date filter ────────────────────────────────────────────────────────
	const _now = frappe.datetime.get_today();
	_pd.from_date = frappe.datetime.add_days(_now, -7);
	_pd.to_date   = _now;

	$("#pd-date-btn").on("click", function () {
		frappe.prompt(
			[
				{ fieldname: "from_date", label: "From Date", fieldtype: "Date", reqd: 1,
				  default: _pd.from_date || frappe.datetime.add_days(frappe.datetime.get_today(), -7) },
				{ fieldname: "to_date",   label: "To Date",   fieldtype: "Date", reqd: 1,
				  default: _pd.to_date   || frappe.datetime.get_today() },
			],
			function (vals) {
				_pd.from_date = vals.from_date;
				_pd.to_date   = vals.to_date;
				const label = frappe.datetime.str_to_user(vals.from_date) + " → " + frappe.datetime.str_to_user(vals.to_date);
				$("#pd-date-btn").text("📅 " + label).addClass("pd-fa");
				if (_pd.selected_project) load_dashboard();
			},
			"Select Reporting Period",
			"Apply"
		);
	});

	// ── Close dropdowns outside click ─────────────────────────────────────
	$(document).on("click", function (e) {
		if (!$(e.target).closest("#pd-proj-btn,#pd-proj-dd").length)     $("#pd-proj-dd").hide();
		if (!$(e.target).closest("#pd-status-btn,#pd-status-dd").length) $("#pd-status-dd").hide();
	});

	$("#pd-refresh").on("click", () => { if (_pd.selected_project) load_dashboard(); });

	$("#pd-print-btn").on("click", () => {
		if (!_pd.selected_project) { frappe.msgprint("Please select a project first."); return; }
		pd_open_print_window(false);
	});

	$("#pd-pdf-btn").on("click", () => {
		if (!_pd.selected_project) { frappe.msgprint("Please select a project first."); return; }
		pd_download_pdf();
	});

	// ── Auto-load from URL param (?project=PROJ-0001) ─────────────────────
	const _urlProj = new URLSearchParams(window.location.search).get("project");
	if (_urlProj) {
		_pd.selected_project = _urlProj;
		_pd.project_label    = _urlProj;
		$("#pd-proj-btn").text("📁 " + _urlProj).addClass("pd-fa");
		load_dashboard();
	}
};

// ── Helpers ────────────────────────────────────────────────────────────────
function pd_status_badge(s) {
	const map = {
		"Open":           "pd-b-blue",
		"Working":        "pd-b-blue",
		"Pending Review": "pd-b-purple",
		"Overdue":        "pd-b-red",
		"Completed":      "pd-b-green",
		"Cancelled":      "pd-b-gray",
		"Template":       "pd-b-gray",
	};
	return `<span class="pd-badge ${map[s] || "pd-b-gray"}">${s || "—"}</span>`;
}

function pd_priority_badge(p) {
	const map = { "High": "pd-b-red", "Medium": "pd-b-amber", "Low": "pd-b-gray", "Urgent": "pd-b-red" };
	return `<span class="pd-badge ${map[p] || "pd-b-gray"}">${p || "—"}</span>`;
}

function pd_proj_status_badge(s) {
	const map = {
		"Open":        "pd-b-blue",
		"Completed":   "pd-b-green",
		"Cancelled":   "pd-b-gray",
		"Hold":        "pd-b-amber",
	};
	return `<span class="pd-badge ${map[s] || "pd-b-gray"}">${s || "—"}</span>`;
}

function fill_class(pct) {
	if (pct >= 100) return "done";
	if (pct >= 60)  return "mid";
	if (pct >= 30)  return "low";
	return "none";
}

function dot_class(status) {
	if (status === "Completed") return "green";
	if (status === "Cancelled" || status === "Hold") return "red";
	return "";
}

// ── Main loader ────────────────────────────────────────────────────────────
function load_dashboard() {
	if (!_pd.selected_project) return;
	$("#pd-refresh").prop("disabled", true).text("Loading…");
	$("#pd-body").html('<div class="pd-loading">Fetching project data…</div>');

	frappe.call({
		method: "bsgroup.bs_group.page.weekly_customer_das.weekly_customer_das.get_dashboard_data",
		args: {
			project:         _pd.selected_project,
			from_date:       _pd.from_date || null,
			to_date:         _pd.to_date   || null,
			selected_status: _pd.selected_status || null,
		},
		callback: function (r) {
			$("#pd-refresh").prop("disabled", false).text("⟳ Refresh");
			if (r.exc || !r.message) {
				$("#pd-body").html(
					`<div class="pd-loading" style="color:#dc2626">Failed to load data. Check console for errors.</div>`
				);
				return;
			}
			render_dashboard(r.message);
		},
	});
}

// ── Renderer ───────────────────────────────────────────────────────────────
function render_dashboard(d) {
	const proj    = d.project    || {};
	const kpis    = d.kpis       || {};
	const filters = d.filters    || {};

	// ── Hero updates ──────────────────────────────────────────────────────
	const proj_name = proj.project_name || proj.name || "—";
	$("#pd-proj-name").text(proj_name);
	if (proj.custom_project_description) {
		$("#pd-proj-desc").text(proj.custom_project_description).show();
	} else {
		$("#pd-proj-desc").hide();
	}
	$("#pd-company").text(proj.company || "");
	$("#pd-proj-meta").html(
		`<strong>${proj.project_type || "Project"}</strong> · ${proj.name || ""} · Priority: ${proj.priority || "—"}`
	);

	// Status pill
	const _dc = dot_class(proj.status);
	$("#pd-status-pill").html(
		`<span class="pd-status-pill"><span class="pd-dot ${_dc}"></span>${proj.status || "—"} &nbsp;|&nbsp; ${proj.is_active === "Yes" ? "Active" : "Inactive"}</span>`
	);

	// Hero meta cards
	const _today = new Date();
	const _dateStr = _today.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
	$("#hm-date").text(_dateStr);
	$("#hm-period").text(
		frappe.datetime.str_to_user(filters.from_date) + " – " + frappe.datetime.str_to_user(filters.to_date)
	);
	$("#hm-pm").text(proj.customer || "—");
	const _pct = proj.percent_complete || 0;
	$("#hm-progress").text(_pct + "%");

	// ── KPI Cards ─────────────────────────────────────────────────────────
	const _pfc  = fill_class(_pct);
	const kpi_html = `
	<div class="pd-kpi-grid">
		<div class="pd-kpi-card">
			<div class="pd-kpi-label">Overall Progress</div>
			<div class="pd-kpi-value">${_pct}%</div>
			<div class="pd-kpi-note">Measured across task completion and milestones.</div>
			<div class="pd-progress-bar"><div class="pd-progress-fill ${_pfc}" style="width:${_pct}%"></div></div>
		</div>
		<div class="pd-kpi-card">
			<div class="pd-kpi-label">Completed This Period</div>
			<div class="pd-kpi-value" style="color:#16a34a">${kpis.completed_period}</div>
			<div class="pd-kpi-note">Tasks completed within the selected reporting window.</div>
		</div>
		<div class="pd-kpi-card">
			<div class="pd-kpi-label">Open Tasks</div>
			<div class="pd-kpi-value" style="color:#1e5bb8">${kpis.open_tasks}</div>
			<div class="pd-kpi-note">Active tasks currently in progress or pending start.</div>
		</div>
		<div class="pd-kpi-card">
			<div class="pd-kpi-label">Overdue Tasks</div>
			<div class="pd-kpi-value" style="color:#dc2626">${kpis.overdue_tasks}</div>
			<div class="pd-kpi-note">Tasks past their expected completion date.</div>
		</div>
	</div>`;

	// ── Executive Summary ──────────────────────────────────────────────────
	const completed_this_week = d.completed_tasks || [];
	const planned_next_week   = d.planned_tasks   || [];
	const open_items          = d.open_items      || [];

	// Auto-generate executive summary lines
	const sum_done   = completed_this_week.length;
	const sum_plan   = planned_next_week.length;
	const sum_open   = open_items.length;
	const sum_over   = kpis.overdue_tasks || 0;

	const exec_this  = sum_done > 0
		? `${sum_done} task${sum_done > 1 ? "s" : ""} were completed during this reporting period, keeping the project on its delivery trajectory.`
		: "No tasks were marked as completed in this reporting window.";

	const exec_next  = sum_plan > 0
		? `The upcoming period targets ${sum_plan} task${sum_plan > 1 ? "s" : ""} for completion, focused on progressing the project toward handover readiness.`
		: "No tasks are currently planned for the upcoming reporting window.";

	const exec_attn  = sum_over > 0
		? `${sum_over} task${sum_over > 1 ? "s are" : " is"} currently overdue. ${sum_open > 0 ? sum_open + " open item" + (sum_open > 1 ? "s" : "") + " require" + (sum_open === 1 ? "s" : "") + " customer-side coordination to maintain the delivery schedule." : ""}`
		: sum_open > 0
			? `${sum_open} open item${sum_open > 1 ? "s" : ""} pending attention to maintain the agreed delivery timeline.`
			: "No critical attention items at this time. Project is progressing as planned.";

	const exec_html = `
	<div class="pd-panel">
		<h2>Executive Summary</h2>
		<div class="pd-desc">A concise weekly view for business stakeholders.</div>
		<div class="pd-list">
			<div class="pd-list-item">
				<div class="pd-icon green">✓</div>
				<div>
					<div class="pd-item-title">This week's progress</div>
					<div class="pd-item-text">${exec_this}</div>
				</div>
			</div>
			<div class="pd-list-item">
				<div class="pd-icon blue">→</div>
				<div>
					<div class="pd-item-title">Upcoming focus</div>
					<div class="pd-item-text">${exec_next}</div>
				</div>
			</div>
			<div class="pd-list-item">
				<div class="pd-icon amber">!</div>
				<div>
					<div class="pd-item-title">Management attention</div>
					<div class="pd-item-text">${exec_attn}</div>
				</div>
			</div>
		</div>
	</div>`;

	// ── Work Completed This Period ─────────────────────────────────────────
	let done_items = "";
	if (completed_this_week.length) {
		completed_this_week.forEach((t, i) => {
			done_items += `
			<div class="pd-list-item">
				<div class="pd-icon green">${i + 1}</div>
				<div>
					<div class="pd-item-title">${t.subject}</div>
					<div class="pd-item-text">${t.parent_label ? "Under: " + t.parent_label + ". " : ""}${t.completed_on ? "Completed " + frappe.datetime.str_to_user(t.completed_on) + "." : ""} ${pd_priority_badge(t.priority)}</div>
				</div>
			</div>`;
		});
	} else {
		done_items = `<div class="pd-empty">No tasks completed in this period.</div>`;
	}

	const done_html = `
	<div class="pd-panel">
		<h2>Work Completed This Period</h2>
		<div class="pd-desc">Customer-facing highlights of completed activities.</div>
		<div class="pd-list">${done_items}</div>
	</div>`;

	// ── Work Planned Next Period ───────────────────────────────────────────
	let plan_items = "";
	if (planned_next_week.length) {
		planned_next_week.forEach((t, i) => {
			plan_items += `
			<div class="pd-list-item">
				<div class="pd-icon blue">${i + 1}</div>
				<div>
					<div class="pd-item-title">${t.subject}</div>
					<div class="pd-item-text">${t.parent_label ? "Under: " + t.parent_label + ". " : ""}${t.exp_end_date ? "Expected by " + frappe.datetime.str_to_user(t.exp_end_date) + "." : ""} ${pd_priority_badge(t.priority)}</div>
				</div>
			</div>`;
		});
	} else {
		plan_items = `<div class="pd-empty">No upcoming tasks scheduled for the next period.</div>`;
	}

	const plan_html = `
	<div class="pd-panel">
		<h2>Work Planned Next Period</h2>
		<div class="pd-desc">Expected activities for the upcoming reporting window.</div>
		<div class="pd-list">${plan_items}</div>
	</div>`;

	// ── Scope Progress Snapshot ────────────────────────────────────────────
	const scope_data = d.scope_groups || [];
	let scope_rows = "";
	if (scope_data.length) {
		scope_data.forEach(g => {
			const fc = fill_class(g.progress);
			scope_rows += `
			<tr>
				<td style="font-weight:600">${g.subject}</td>
				<td>${pd_status_badge(g.status)}</td>
				<td>
					<div style="display:flex;align-items:center;gap:8px">
						<div class="pd-mini-bar"><div class="pd-mini-fill ${fc}" style="width:${g.progress}%"></div></div>
						<span class="pd-scope-pct">${g.progress}%</span>
					</div>
				</td>
				<td style="color:var(--pd-muted);font-size:12px">${g.remark || "—"}</td>
			</tr>`;
		});
	} else {
		scope_rows = `<tr><td colspan="4" style="color:var(--pd-muted);text-align:center;padding:16px">No task groups defined for this project.</td></tr>`;
	}

	const scope_html = `
	<div class="pd-panel">
		<h2>Scope Progress Snapshot</h2>
		<div class="pd-desc">Progress view across major task groups and work areas.</div>
		<table class="pd-scope-table">
			<thead><tr><th>Scope Area</th><th>Status</th><th>Progress</th><th>Remarks</th></tr></thead>
			<tbody>${scope_rows}</tbody>
		</table>
	</div>`;

	// ── Key Open Items ────────────────────────────────────────────────────
	let open_html_items = "";
	const labels = ["A","B","C","D","E","F","G","H"];
	if (open_items.length) {
		open_items.forEach((t, i) => {
			const is_overdue = t.is_overdue;
			open_html_items += `
			<div class="pd-list-item">
				<div class="pd-icon ${is_overdue ? "red" : "amber"}">${labels[i] || (i + 1)}</div>
				<div>
					<div class="pd-item-title">${t.subject} ${is_overdue ? '<span class="pd-badge pd-b-red" style="font-size:10px">OVERDUE</span>' : ""}</div>
					<div class="pd-item-text">${t.parent_label ? "Area: " + t.parent_label + ". " : ""}${t.exp_end_date ? "Due: " + frappe.datetime.str_to_user(t.exp_end_date) + "." : "No due date set."} ${pd_status_badge(t.status)}</div>
				</div>
			</div>`;
		});
	} else {
		open_html_items = `<div class="pd-empty">✓ No critical open items at this time.</div>`;
	}

	const open_panel_html = `
	<div class="pd-panel">
		<h2>Key Open Items</h2>
		<div class="pd-desc">Items requiring attention to maintain the delivery schedule.</div>
		<div class="pd-list">${open_html_items}</div>
	</div>`;

	// ── Milestone Progress ────────────────────────────────────────────────
	const milestones = d.milestones || [];
	let ms_rows = "";
	if (milestones.length) {
		milestones.forEach(m => {
			const pct = m.progress || 0;
			const fc  = pct >= 100 ? "done" : pct >= 50 ? "" : pct >= 25 ? "amber" : "red";
			ms_rows += `
			<div class="pd-ms-row">
				<div class="pd-ms-label" title="${m.subject}">${m.subject}</div>
				<div class="pd-ms-track"><div class="pd-ms-fill ${fc}" style="width:${pct}%"></div></div>
				<div class="pd-ms-pct">${pct}%</div>
			</div>`;
		});
	} else {
		// Fallback: show task-group milestones if no milestone tasks
		const fallback = d.scope_groups || [];
		if (fallback.length) {
			fallback.forEach(g => {
				const pct = g.progress || 0;
				const fc  = pct >= 100 ? "done" : pct >= 60 ? "" : pct >= 30 ? "amber" : "red";
				ms_rows += `
				<div class="pd-ms-row">
					<div class="pd-ms-label" title="${g.subject}">${g.subject}</div>
					<div class="pd-ms-track"><div class="pd-ms-fill ${fc}" style="width:${pct}%"></div></div>
					<div class="pd-ms-pct">${pct}%</div>
				</div>`;
			});
		} else {
			ms_rows = `<div class="pd-empty">No milestones defined for this project.</div>`;
		}
	}

	const ms_html = `
	<div class="pd-panel">
		<h2>Milestone Progress</h2>
		<div class="pd-desc">High-level milestone status for executive review.</div>
		<div class="pd-milestones">${ms_rows}</div>
	</div>`;

	// ── Remarks panel ─────────────────────────────────────────────────────
	const remarks_html = `
	<div class="pd-panel">
		<h2>Remarks</h2>
		<div class="pd-desc">This dashboard is a customer-friendly weekly update. It presents a simplified business view and excludes internal operational details, user allocations, and system-specific statuses.</div>
		<div class="pd-list-item" style="margin-top:8px">
			<div class="pd-icon blue">i</div>
			<div>
				<div class="pd-item-title">Reporting note</div>
				<div class="pd-item-text">Data is pulled live from ERPNext. Progress percentages reflect task completion ratios within each scope group. Report generated on ${d.generated_at || "—"}.</div>
			</div>
		</div>
	</div>`;

	// ── Assemble ──────────────────────────────────────────────────────────
	const body_html = `
	${kpi_html}
	<div class="pd-main-grid">
		<div class="pd-col">
			${exec_html}
			${done_html}
			${plan_html}
			${scope_html}
		</div>
		<div class="pd-col">
			${open_panel_html}
			${ms_html}
			${remarks_html}
		</div>
	</div>`;

	$("#pd-body").html(body_html);
	$("#pd-footer").text(
		"Prepared by BITS Secure IT · Customer Weekly Dashboard · " + (d.generated_at || "")
	);
}

// ── Print / PDF helpers ────────────────────────────────────────────────────

function pd_get_print_styles() {
	return `
		* { box-sizing: border-box; margin: 0; padding: 0; }
		body {
			font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif;
			color: #172033; background: #fff; font-size: 12px; line-height: 1.5;
		}
		.pd-wrap { padding: 20px; }
		.pd-hero {
			background: linear-gradient(135deg,#0f2d58 0%,#18478f 100%);
			color: #fff; border-radius: 14px; padding: 20px;
			display: grid; grid-template-columns: 1.4fr 1fr; gap: 16px; margin-bottom: 16px;
			-webkit-print-color-adjust: exact; print-color-adjust: exact;
		}
		.pd-brand-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
		.pd-logo {
			width: 40px; height: 40px; border-radius: 10px;
			background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.18);
			display: flex; align-items: center; justify-content: center;
			font-size: 18px; font-weight: 700;
		}
		.pd-eyebrow { font-size: 10px; letter-spacing: 0.15em; text-transform: uppercase; opacity: 0.78; margin-bottom: 3px; }
		.pd-hero-title { font-size: 20px; font-weight: 700; color: #fff; }
		.pd-hero-sub { margin-top: 6px; font-size: 12px; color: rgba(255,255,255,0.84); }
		.pd-status-pill {
			display: inline-flex; align-items: center; gap: 6px;
			padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 700;
			background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.22); margin-top: 8px;
		}
		.pd-dot { width: 7px; height: 7px; border-radius: 50%; background: #fbbf24; }
		.pd-dot.green { background: #4ade80; }
		.pd-dot.red   { background: #f87171; }
		.pd-hero-meta { display: grid; grid-template-columns: repeat(2,1fr); gap: 10px; align-self: start; }
		.pd-meta-card {
			background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.14);
			border-radius: 12px; padding: 10px;
			-webkit-print-color-adjust: exact; print-color-adjust: exact;
		}
		.pd-meta-label { font-size: 10px; text-transform: uppercase; letter-spacing:.06em; opacity:.75; margin-bottom:6px; }
		.pd-meta-value { font-size: 13px; font-weight: 600; }
		.pd-kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 14px; }
		.pd-kpi-card {
			background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px;
			-webkit-print-color-adjust: exact; print-color-adjust: exact;
		}
		.pd-kpi-label { font-size: 11px; color: #6b7280; margin-bottom: 6px; }
		.pd-kpi-value { font-size: 22px; font-weight: 800; color: #172033; margin-bottom: 4px; }
		.pd-kpi-note  { font-size: 11px; color: #6b7280; line-height: 1.4; }
		.pd-progress-bar { width: 100%; height: 7px; background: #e8edf5; border-radius: 999px; overflow: hidden; margin-top: 8px; }
		.pd-progress-fill {
			height: 100%; background: linear-gradient(90deg,#1e5bb8,#4f8df2);
			border-radius: 999px;
			-webkit-print-color-adjust: exact; print-color-adjust: exact;
		}
		.pd-progress-fill.green { background: linear-gradient(90deg,#34d399,#16a34a); }
		.pd-progress-fill.amber { background: linear-gradient(90deg,#fbbf24,#d97706); }
		.pd-progress-fill.red   { background: linear-gradient(90deg,#f87171,#dc2626); }
		.pd-main-grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 14px; }
		.pd-col { display: grid; gap: 14px; align-content: start; }
		.pd-panel {
			background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px;
			page-break-inside: avoid;
		}
		.pd-panel h2 { font-size: 14px; font-weight: 700; color: #172033; margin-bottom: 4px; }
		.pd-desc { color: #6b7280; font-size: 11px; margin-bottom: 10px; line-height: 1.5; }
		.pd-list { display: grid; gap: 8px; }
		.pd-list-item { border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 12px; display: flex; gap: 10px; align-items: flex-start; }
		.pd-icon { width: 28px; height: 28px; border-radius: 8px; flex: 0 0 28px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
		.pd-icon.blue   { background: #eef4ff; color: #1e5bb8; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		.pd-icon.green  { background: #edf9f0; color: #16a34a; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		.pd-icon.amber  { background: #fff7eb; color: #d97706; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		.pd-icon.red    { background: #fee2e2; color: #dc2626; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		.pd-item-title  { font-size: 12px; font-weight: 700; margin-bottom: 2px; color: #172033; }
		.pd-item-text   { font-size: 11px; color: #6b7280; line-height: 1.5; }
		.pd-scope-table { width: 100%; border-collapse: collapse; font-size: 11px; }
		.pd-scope-table th, .pd-scope-table td { padding: 7px 8px; border-bottom: 1px solid #f0f4f5; text-align: left; vertical-align: middle; }
		.pd-scope-table th { color: #6b7280; font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: .05em; }
		.pd-scope-table tr:last-child td { border-bottom: none; }
		.pd-mini-bar { height: 6px; background: #e8edf5; border-radius: 999px; overflow: hidden; min-width: 60px; }
		.pd-mini-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg,#1e5bb8,#4f8df2); -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		.pd-mini-fill.done  { background: linear-gradient(90deg,#34d399,#16a34a); }
		.pd-mini-fill.low   { background: linear-gradient(90deg,#fbbf24,#d97706); }
		.pd-mini-fill.none  { background: linear-gradient(90deg,#f87171,#dc2626); }
		.pd-milestones { display: grid; gap: 10px; }
		.pd-ms-row { display: grid; grid-template-columns: 100px 1fr 36px; align-items: center; gap: 8px; font-size: 11px; }
		.pd-ms-label { color: #172033; font-weight: 600; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
		.pd-ms-track { height: 8px; background: #e8edf5; border-radius: 999px; overflow: hidden; }
		.pd-ms-fill  { height: 100%; border-radius: 999px; background: linear-gradient(90deg,#1e5bb8,#4f8df2); -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		.pd-ms-fill.done  { background: linear-gradient(90deg,#34d399,#16a34a); }
		.pd-ms-fill.amber { background: linear-gradient(90deg,#fbbf24,#d97706); }
		.pd-ms-fill.red   { background: linear-gradient(90deg,#f87171,#dc2626); }
		.pd-ms-pct { font-size: 10px; font-weight: 700; color: #6b7280; text-align: right; }
		.pd-badge { display: inline-block; border-radius: 999px; padding: 2px 7px; font-size: 10px; font-weight: 700; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		.pd-b-green  { background: #dcfce7; color: #15803d; }
		.pd-b-blue   { background: #dbeafe; color: #1d4ed8; }
		.pd-b-amber  { background: #fef3c7; color: #b45309; }
		.pd-b-red    { background: #fee2e2; color: #b91c1c; }
		.pd-b-gray   { background: #f3f4f6; color: #374151; }
		.pd-b-purple { background: #ede9fe; color: #6d28d9; }
		.pd-scope-pct { font-weight: 700; color: #172033; }
		.pd-empty { color: #6b7280; font-size: 11px; padding: 8px 0; }
		.pd-footer { text-align: center; margin-top: 20px; color: #6b7280; font-size: 10px; }

		/* ── Single-column PDF layout ── */
		.pd-pdf-body { margin-top: 0; }
		.pd-pdf-panels {
			display: grid;
			grid-template-columns: 1fr 1fr;
			gap: 12px;
			margin-top: 0;
		}
		.pd-pdf-panels .pd-panel { break-inside: avoid; page-break-inside: avoid; }
		/* Executive summary and scope table span full width */
		.pd-pdf-panels .pd-panel:nth-child(1),
		.pd-pdf-panels .pd-panel:nth-child(4) {
			grid-column: 1 / -1;
		}
		.pd-kpi-grid { margin-bottom: 12px; }

		@media print {
			body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
			.pd-hero, .pd-meta-card, .pd-icon, .pd-badge, .pd-progress-fill,
			.pd-mini-fill, .pd-ms-fill { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
		}
	`;
}

function pd_build_print_html() {
	const $hero = $(".pd-hero").clone();
	$hero.find(".pd-filter-row").remove();

	// Extract all panels in a flat order: KPI cards first, then panels left-col then right-col
	const $body   = $("#pd-body");
	const $kpi    = $body.find(".pd-kpi-grid").clone();
	const $panels = $body.find(".pd-panel").clone();
	const footer_txt = $("#pd-footer").text() || "";

	const panels_html = $panels.map(function() { return this.outerHTML; }).get().join("\n");

	return `<!DOCTYPE html>
<html>
<head>
	<meta charset="UTF-8"/>
	<title>Weekly Customer Dashboard</title>
	<style>${pd_get_print_styles()}</style>
</head>
<body>
<div class="pd-wrap">
	${$hero.get(0) ? $hero.get(0).outerHTML : ""}
	<div class="pd-pdf-body">
		${$kpi.get(0) ? $kpi.get(0).outerHTML : ""}
		<div class="pd-pdf-panels">${panels_html}</div>
	</div>
	<div class="pd-footer">${footer_txt}</div>
</div>
</body>
</html>`;
}

function pd_open_print_window() {
	const win = window.open("", "_blank", "width=1200,height=900");
	if (!win) { frappe.msgprint("Please allow pop-ups to use the Print feature."); return; }
	win.document.open();
	win.document.write(pd_build_print_html());
	win.document.close();
	win.onload = () => { win.focus(); win.print(); };
}

function pd_download_pdf() {
	const $btn = $("#pd-pdf-btn");
	$btn.prop("disabled", true).text("Generating…");

	function _do_pdf() {
		const element = document.createElement("div");
		element.innerHTML = pd_build_print_html();
		// Extract just the body content for html2pdf
		const body_el = element.querySelector("body") || element;

		const proj_name = (_pd.project_label || "dashboard").replace(/[^a-z0-9_-]/gi, "_");
		const filename  = `weekly_report_${proj_name}_${frappe.datetime.get_today()}.pdf`;

		html2pdf()
			.set({
				margin:      [8, 8, 8, 8],
				filename:    filename,
				image:       { type: "jpeg", quality: 0.97 },
				html2canvas: { scale: 2, useCORS: true, logging: false },
				jsPDF:       { unit: "mm", format: "a4", orientation: "portrait" },
				pagebreak:   { mode: "css", before: ".page-break", avoid: ".pd-panel,.pd-kpi-card" },
			})
			.from(body_el)
			.save()
			.then(() => { $btn.prop("disabled", false).text("⬇ PDF"); })
			.catch(() => { $btn.prop("disabled", false).text("⬇ PDF"); });
	}

	if (typeof html2pdf !== "undefined") {
		_do_pdf();
	} else {
		const script = document.createElement("script");
		script.src = "https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js";
		script.onload  = _do_pdf;
		script.onerror = () => {
			$btn.prop("disabled", false).text("⬇ PDF");
			frappe.msgprint("Could not load PDF library. Please check your internet connection.");
		};
		document.head.appendChild(script);
	}
}
