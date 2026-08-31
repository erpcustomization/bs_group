const HRD_METHOD = "bsgroup.bs_group.page.hr_dashboard.hr_dashboard";
const _hrd_state = { tab: "employee" };

frappe.pages["hr-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "HR Dashboard",
		single_column: true,
	});

	if (!document.getElementById("hrd-styles")) {
		const style = document.createElement("style");
		style.id = "hrd-styles";
		style.textContent = `
			.hrd-wrap { padding: 20px 24px; background: #f5f7fb; min-height: 100vh; }
			.hrd-header {
				background: linear-gradient(135deg,#111827,#1f2937 55%,#374151);
				color: #fff; border-radius: 20px; padding: 24px 28px; margin-bottom: 18px;
				display: flex; justify-content: space-between; align-items: flex-start;
				flex-wrap: wrap; gap: 14px; box-shadow: 0 10px 25px rgba(15,23,42,0.12);
			}
			.hrd-header h1 { margin: 0; font-size: 26px; font-weight: 800; color: #fff; }
			.hrd-header .sub { font-size: 13px; opacity: .85; margin-top: 4px; }
			.hrd-tabs { display: flex; gap: 8px; flex-wrap: wrap; }
			.hrd-tab {
				background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.22);
				color: #fff; padding: 8px 16px; border-radius: 999px; cursor: pointer;
				font-size: 13px; font-weight: 600; white-space: nowrap; transition: background .2s;
			}
			.hrd-tab:hover { background: rgba(255,255,255,0.22); }
			.hrd-tab.active { background: #2563eb; border-color: #2563eb; }
			.hrd-grid4 { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 16px; }
			.hrd-grid2 { display: grid; grid-template-columns: 1.2fr .8fr; gap: 16px; margin-bottom: 16px; }
			@media (max-width: 1100px) { .hrd-grid4 { grid-template-columns: repeat(2,1fr); } .hrd-grid2 { grid-template-columns: 1fr; } }
			@media (max-width: 650px) { .hrd-grid4 { grid-template-columns: 1fr; } }
			.hrd-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 20px; box-shadow: 0 4px 16px rgba(15,23,42,0.06); }
			.hrd-kpi-label { font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: .04em; }
			.hrd-kpi-value { font-size: 26px; font-weight: 800; margin-top: 8px; color: #1f2937; }
			.hrd-kpi-foot { font-size: 12px; color: #9ca3af; margin-top: 6px; }
			.hrd-sec-title { font-size: 15px; font-weight: 700; margin-bottom: 14px; color: #1f2937; }
			.hrd-status { display: inline-flex; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; }
			.hrd-s-green  { background: #ecfdf3; color: #067647; }
			.hrd-s-amber  { background: #fffaeb; color: #b54708; }
			.hrd-s-red    { background: #fef3f2; color: #b42318; }
			.hrd-s-blue   { background: #eff8ff; color: #175cd3; }
			.hrd-s-gray   { background: #f3f4f6; color: #475467; }
			.hrd-table { width: 100%; border-collapse: collapse; font-size: 13px; }
			.hrd-table th, .hrd-table td { text-align: left; padding: 10px 8px; border-bottom: 1px solid #f3f4f6; }
			.hrd-table th { font-size: 11px; color: #9ca3af; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
			.hrd-table tr:hover td { background: #f9fafb; }
			.hrd-empty { color: #9ca3af; text-align: center; padding: 28px 0; font-size: 13px; }
			.hrd-loading { text-align: center; padding: 60px; color: #9ca3af; font-size: 14px; }
			.hrd-link { color: #2563eb; text-decoration: none; font-weight: 600; }
			.hrd-link:hover { text-decoration: underline; }
		`;
		document.head.appendChild(style);
	}

	$(page.body).html(`
		<div class="hrd-wrap">
			<div class="hrd-header">
				<div>
					<h1>HR Dashboard</h1>
					<div class="sub" id="hrd-subtitle">Loading…</div>
				</div>
				<div class="hrd-tabs" id="hrd-tabs"></div>
			</div>
			<div id="hrd-body"><div class="hrd-loading">Loading dashboard…</div></div>
		</div>
	`);

	hrd_boot();
};

function hrd_status_badge(status) {
	const map = { Present: "hrd-s-green", "Half Day": "hrd-s-amber", Absent: "hrd-s-red", "On Leave": "hrd-s-blue", Open: "hrd-s-amber" };
	const cls = map[status] || "hrd-s-gray";
	return `<span class="hrd-status ${cls}">${frappe.utils.escape_html(status || "Not Marked")}</span>`;
}

function hrd_boot() {
	frappe.call({
		method: `${HRD_METHOD}.get_dashboard_context`,
		callback: function (r) {
			const ctx = r.message || {};
			const tabs = [{ key: "employee", label: "My Dashboard" }];
			if (ctx.is_manager) tabs.push({ key: "manager", label: "Manager" });
			if (ctx.is_hr) tabs.push({ key: "hr", label: "HR" });

			$("#hrd-subtitle").text("BS Group · " + (ctx.employee_name || frappe.session.user));
			$("#hrd-tabs").html(
				tabs.map((t) => `<div class="hrd-tab${t.key === _hrd_state.tab ? " active" : ""}" data-tab="${t.key}">${t.label}</div>`).join("")
			);
			$("#hrd-tabs .hrd-tab").on("click", function () {
				_hrd_state.tab = $(this).data("tab");
				$("#hrd-tabs .hrd-tab").removeClass("active");
				$(this).addClass("active");
				hrd_render(_hrd_state.tab);
			});
			if (!tabs.find((t) => t.key === _hrd_state.tab)) _hrd_state.tab = tabs[0].key;
			hrd_render(_hrd_state.tab);
		},
	});
}

function hrd_render(tab) {
	$("#hrd-body").html('<div class="hrd-loading">Fetching live data…</div>');
	if (tab === "employee") hrd_render_employee();
	else if (tab === "manager") hrd_render_manager();
	else if (tab === "hr") hrd_render_hr();
}

function hrd_render_employee() {
	frappe.call({
		method: `${HRD_METHOD}.get_employee_summary`,
		callback: function (r) {
			const d = r.message || {};
			if (!d.has_employee) {
				$("#hrd-body").html('<div class="hrd-card"><div class="hrd-empty">No active Employee record is linked to your user account, so personal attendance/leave data is unavailable. Ask HR to link your User ID on the Employee record.</div></div>');
				return;
			}
			const att = d.attendance_summary || {};
			const leaveRows = (d.leave_balances || []).map((l) => `
				<tr><td>${frappe.utils.escape_html(l.leave_type)}</td><td>${l.entitlement}</td><td>${l.used}</td><td>${l.pending}</td><td><strong>${l.available}</strong></td></tr>
			`).join("") || `<tr><td colspan="5" class="hrd-empty">No leave allocation found</td></tr>`;

			const pendingRows = (d.pending_requests || []).map((p) => `
				<tr><td>${frappe.utils.escape_html(p.leave_type)}</td><td>${frappe.datetime.str_to_user(p.from_date)} – ${frappe.datetime.str_to_user(p.to_date)}</td><td>${hrd_status_badge(p.status)}</td></tr>
			`).join("") || `<tr><td colspan="3" class="hrd-empty">No pending requests</td></tr>`;

			$("#hrd-body").html(`
				<div class="hrd-grid4">
					<div class="hrd-card"><div class="hrd-kpi-label">Today</div><div class="hrd-kpi-value">${d.today_status ? hrd_status_badge(d.today_status === "IN" ? "Present" : d.today_status) : hrd_status_badge("Not Marked")}</div><div class="hrd-kpi-foot">${d.today_time ? frappe.datetime.str_to_user(d.today_time) : ""}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">Present (month)</div><div class="hrd-kpi-value">${att.Present || 0}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">On leave (month)</div><div class="hrd-kpi-value">${att["On Leave"] || 0}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">Pending requests</div><div class="hrd-kpi-value">${(d.pending_requests || []).length}</div></div>
				</div>
				<div class="hrd-grid2">
					<div class="hrd-card">
						<div class="hrd-sec-title">My Leave</div>
						<table class="hrd-table"><thead><tr><th>Leave Type</th><th>Entitlement</th><th>Used</th><th>Pending</th><th>Available</th></tr></thead><tbody>${leaveRows}</tbody></table>
					</div>
					<div class="hrd-card">
						<div class="hrd-sec-title">Pending Requests</div>
						<table class="hrd-table"><thead><tr><th>Type</th><th>Dates</th><th>Status</th></tr></thead><tbody>${pendingRows}</tbody></table>
					</div>
				</div>
			`);
		},
	});
}

function hrd_render_manager() {
	frappe.call({
		method: `${HRD_METHOD}.get_manager_summary`,
		callback: function (r) {
			const d = r.message || {};
			if (!d.has_reports) {
				$("#hrd-body").html('<div class="hrd-card"><div class="hrd-empty">No direct reports or leave-approver assignments found for your user.</div></div>');
				return;
			}
			const k = d.kpis || {};
			const approvalRows = (d.pending_approvals || []).map((p) => `
				<tr><td>${frappe.utils.escape_html(p.employee_name)}</td><td>${frappe.utils.escape_html(p.leave_type)}</td><td>${frappe.datetime.str_to_user(p.from_date)} – ${frappe.datetime.str_to_user(p.to_date)}</td><td>${hrd_status_badge("Open")}</td><td><a class="hrd-link" href="/app/leave-application/${encodeURIComponent(p.name)}" target="_blank">Review</a></td></tr>
			`).join("") || `<tr><td colspan="5" class="hrd-empty">No pending approvals</td></tr>`;

			const teamRows = (d.team_today || []).map((t) => `
				<tr><td>${frappe.utils.escape_html(t.employee_name)}</td><td>${hrd_status_badge(t.status)}</td></tr>
			`).join("") || `<tr><td colspan="2" class="hrd-empty">No team members</td></tr>`;

			$("#hrd-body").html(`
				<div class="hrd-grid4">
					<div class="hrd-card"><div class="hrd-kpi-label">Present today</div><div class="hrd-kpi-value">${k.present_today || 0}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">On leave</div><div class="hrd-kpi-value">${k.on_leave || 0}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">Pending approvals</div><div class="hrd-kpi-value">${k.pending_approvals || 0}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">Attendance exceptions</div><div class="hrd-kpi-value">${k.attendance_exceptions || 0}</div></div>
				</div>
				<div class="hrd-grid2">
					<div class="hrd-card">
						<div class="hrd-sec-title">Pending Approvals</div>
						<table class="hrd-table"><thead><tr><th>Employee</th><th>Request</th><th>Dates</th><th>Status</th><th></th></tr></thead><tbody>${approvalRows}</tbody></table>
					</div>
					<div class="hrd-card">
						<div class="hrd-sec-title">Team Today</div>
						<table class="hrd-table"><thead><tr><th>Employee</th><th>Status</th></tr></thead><tbody>${teamRows}</tbody></table>
					</div>
				</div>
			`);
		},
	});
}

function hrd_render_hr() {
	frappe.call({
		method: `${HRD_METHOD}.get_hr_summary`,
		callback: function (r) {
			const d = r.message || {};
			const k = d.kpis || {};
			const recRows = (d.leave_reconciliation || []).map((x) => `
				<tr><td>${frappe.utils.escape_html(x.employee_name)}</td><td>${frappe.utils.escape_html(x.leave_type)}</td><td>${x.ledger_balance}</td><td>${x.pending}</td><td><strong>${x.available}</strong></td><td><span class="hrd-status ${x.available < 0 ? "hrd-s-red" : "hrd-s-amber"}">${frappe.utils.escape_html(x.exception)}</span></td></tr>
			`).join("") || `<tr><td colspan="6" class="hrd-empty">No exceptions found</td></tr>`;

			$("#hrd-body").html(`
				<div class="hrd-grid4">
					<div class="hrd-card"><div class="hrd-kpi-label">Missing leave allocation</div><div class="hrd-kpi-value">${k.missing_leave_allocation || 0}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">Missing leave approver</div><div class="hrd-kpi-value">${k.missing_leave_approver || 0}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">Active employees</div><div class="hrd-kpi-value">${k.total_active_employees || 0}</div></div>
					<div class="hrd-card"><div class="hrd-kpi-label">Balance exceptions</div><div class="hrd-kpi-value">${(d.leave_reconciliation || []).length}</div></div>
				</div>
				<div class="hrd-card">
					<div class="hrd-sec-title">Leave Balance Reconciliation</div>
					<table class="hrd-table"><thead><tr><th>Employee</th><th>Leave Type</th><th>Ledger Balance</th><th>Pending</th><th>Available</th><th>Exception</th></tr></thead><tbody>${recRows}</tbody></table>
				</div>
			`);
		},
		error: function (e) {
			$("#hrd-body").html(`<div class="hrd-card"><div class="hrd-empty">${e && e.message ? frappe.utils.escape_html(e.message) : "Not permitted."}</div></div>`);
		},
	});
}
