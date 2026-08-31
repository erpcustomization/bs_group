const TPG_METHOD = "bsgroup.bs_group.page.task_progress.task_progress";
const _tpg_state = { project: null, tasks: [], collapsed: {} };

frappe.pages["task-progress"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Task Progress",
		single_column: true,
	});

	if (!document.getElementById("tpg-styles")) {
		const style = document.createElement("style");
		style.id = "tpg-styles";
		style.textContent = `
			.tpg-wrap { padding: 20px 24px; background: #f5f7fb; min-height: 100vh; }
			.tpg-header {
				background: linear-gradient(135deg,#111827,#1f2937 55%,#374151);
				color: #fff; border-radius: 20px; padding: 22px 28px; margin-bottom: 18px;
				display: flex; justify-content: space-between; align-items: center;
				flex-wrap: wrap; gap: 14px; box-shadow: 0 10px 25px rgba(15,23,42,0.12);
			}
			.tpg-header h1 { margin: 0; font-size: 24px; font-weight: 800; color: #fff; }
			.tpg-header .sub { font-size: 13px; opacity: .85; margin-top: 4px; }
			.tpg-select {
				min-width: 260px; padding: 9px 12px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.25);
				background: rgba(255,255,255,0.12); color: #fff; font-size: 13px; font-weight: 600; outline: none;
			}
			.tpg-select option { color: #1f2937; }
			.tpg-kpis { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 16px; }
			@media (max-width: 950px) { .tpg-kpis { grid-template-columns: repeat(2,1fr); } }
			.tpg-kpi { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; padding: 18px 20px; box-shadow: 0 4px 16px rgba(15,23,42,0.06); }
			.tpg-kpi-label { font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: .04em; font-weight: 700; }
			.tpg-kpi-value { font-size: 24px; font-weight: 800; margin-top: 6px; color: #1f2937; }
			.tpg-card { background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 4px 16px rgba(15,23,42,0.06); overflow: hidden; }
			.tpg-table { width: 100%; border-collapse: collapse; font-size: 13px; }
			.tpg-table thead th {
				text-align: left; padding: 12px 14px; background: #f9fafb; border-bottom: 1px solid #e5e7eb;
				font-size: 11px; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
			}
			.tpg-table td { padding: 11px 14px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
			.tpg-table tbody tr:hover td { background: #f9fafb; }
			.tpg-row-parent td { font-weight: 700; background: #fafbfc; }
			.tpg-name-cell { display: flex; align-items: center; gap: 8px; }
			.tpg-toggle {
				width: 18px; height: 18px; display: inline-flex; align-items: center; justify-content: center;
				cursor: pointer; color: #6b7280; font-size: 11px; border-radius: 4px; flex-shrink: 0;
				transition: transform .15s, background .15s;
			}
			.tpg-toggle:hover { background: #eef2f7; }
			.tpg-toggle.collapsed { transform: rotate(-90deg); }
			.tpg-toggle-spacer { width: 18px; flex-shrink: 0; }
			.tpg-task-link { color: #1f2937; text-decoration: none; font-weight: 600; }
			.tpg-task-link:hover { color: #2563eb; text-decoration: underline; }
			.tpg-status { display: inline-flex; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; }
			.tpg-s-open     { background: #eff8ff; color: #175cd3; }
			.tpg-s-working  { background: #fff7e6; color: #b45309; }
			.tpg-s-review   { background: #fef3f2; color: #b42318; }
			.tpg-s-overdue  { background: #fef3f2; color: #b42318; }
			.tpg-s-completed{ background: #ecfdf3; color: #067647; }
			.tpg-s-cancelled{ background: #f3f4f6; color: #475467; }
			.tpg-s-template { background: #f3f4f6; color: #475467; }
			.tpg-progress-wrap { display: flex; align-items: center; gap: 8px; min-width: 120px; }
			.tpg-progress-bar { flex: 1; height: 7px; border-radius: 999px; background: #eef0f3; overflow: hidden; }
			.tpg-progress-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg,#2563eb,#22c55e); }
			.tpg-progress-pct { font-size: 12px; font-weight: 700; color: #374151; min-width: 34px; text-align: right; }
			.tpg-empty { color: #9ca3af; text-align: center; padding: 48px 0; font-size: 13px; }
			.tpg-loading { text-align: center; padding: 60px; color: #9ca3af; font-size: 14px; }
			.tpg-date { color: #4b5563; white-space: nowrap; }
		`;
		document.head.appendChild(style);
	}

	$(page.body).html(`
		<div class="tpg-wrap">
			<div class="tpg-header">
				<div>
					<h1>Task Progress</h1>
					<div class="sub" id="tpg-subtitle">Select a project to view its task hierarchy</div>
				</div>
				<select class="tpg-select" id="tpg-project-select">
					<option value="">Loading projects…</option>
				</select>
			</div>
			<div id="tpg-body"><div class="tpg-loading">Loading projects…</div></div>
		</div>
	`);

	tpg_boot();
};

function tpg_status_class(status) {
	// BS Group overrides Task.status with its own project-workflow values
	// (see bsgroup/bs_group/custom/task.json) instead of the stock
	// Open/Working/Completed set - map by keyword so new statuses degrade
	// gracefully to a sensible color instead of a wrong/blank badge.
	const s = (status || "").toLowerCase();
	if (s === "completed") return "tpg-s-completed";
	if (s.includes("overdue")) return "tpg-s-overdue";
	if (s.includes("cancel")) return "tpg-s-cancelled";
	if (s.includes("pending") || s.includes("sign-off") || s.includes("invoic")) return "tpg-s-review";
	if (s.includes("progress") || s.includes("implementation") || s.includes("testing") || s.includes("planning")) return "tpg-s-working";
	return "tpg-s-open";
}

function tpg_status_badge(status) {
	return `<span class="tpg-status ${tpg_status_class(status)}">${frappe.utils.escape_html(status || "Open")}</span>`;
}

function tpg_fmt_date(d) {
	if (!d) return `<span style="color:#c1c7d0">—</span>`;
	return frappe.datetime.str_to_user(d);
}

function tpg_boot() {
	frappe.call({
		method: `${TPG_METHOD}.get_projects`,
		callback: function (r) {
			const projects = r.message || [];
			const $select = $("#tpg-project-select");
			if (!projects.length) {
				$select.html('<option value="">No projects found</option>');
				$("#tpg-body").html('<div class="tpg-card"><div class="tpg-empty">No projects to show.</div></div>');
				return;
			}
			$select.html(
				`<option value="">Select a project…</option>` +
				projects.map((p) => `<option value="${frappe.utils.escape_html(p.name)}">${frappe.utils.escape_html(p.project_name || p.name)}</option>`).join("")
			);
			$select.on("change", function () {
				const project = $(this).val();
				_tpg_state.project = project;
				_tpg_state.collapsed = {};
				if (project) {
					tpg_load_tasks(project);
				} else {
					$("#tpg-subtitle").text("Select a project to view its task hierarchy");
					$("#tpg-body").html('<div class="tpg-card"><div class="tpg-empty">Choose a project above to see its tasks.</div></div>');
				}
			});

			// Auto-select the first project for a fast first-glance view.
			$select.val(projects[0].name).trigger("change");
		},
	});
}

function tpg_load_tasks(project) {
	$("#tpg-body").html('<div class="tpg-loading">Loading tasks…</div>');
	frappe.call({
		method: `${TPG_METHOD}.get_project_tasks`,
		args: { project },
		callback: function (r) {
			_tpg_state.tasks = r.message || [];
			// Show parent tasks only by default; each parent's arrow expands its children.
			_tpg_state.collapsed = {};
			const collapse_all = (nodes) => {
				for (const n of nodes) {
					if (n.children && n.children.length) {
						_tpg_state.collapsed[n.name] = true;
						collapse_all(n.children);
					}
				}
			};
			collapse_all(_tpg_state.tasks);
			$("#tpg-subtitle").text(`Project: ${project}`);
			tpg_render();
		},
	});
}

function tpg_flatten(nodes, depth) {
	let rows = [];
	for (const n of nodes) {
		rows.push({ node: n, depth });
		if (n.children && n.children.length && !_tpg_state.collapsed[n.name]) {
			rows = rows.concat(tpg_flatten(n.children, depth + 1));
		}
	}
	return rows;
}

function tpg_count_all(nodes) {
	let total = 0, completed = 0, overdue = 0, working = 0;
	const walk = (list) => {
		for (const n of list) {
			total += 1;
			if (n.status === "Completed") completed += 1;
			if (n.status === "Overdue") overdue += 1;
			if (n.status === "Working") working += 1;
			if (n.children && n.children.length) walk(n.children);
		}
	};
	walk(nodes);
	return { total, completed, overdue, working };
}

function tpg_render() {
	const tasks = _tpg_state.tasks;
	const stats = tpg_count_all(tasks);

	$("#tpg-body").html(`
		<div class="tpg-kpis">
			<div class="tpg-kpi"><div class="tpg-kpi-label">Total Tasks</div><div class="tpg-kpi-value">${stats.total}</div></div>
			<div class="tpg-kpi"><div class="tpg-kpi-label">Completed</div><div class="tpg-kpi-value">${stats.completed}</div></div>
			<div class="tpg-kpi"><div class="tpg-kpi-label">In Progress</div><div class="tpg-kpi-value">${stats.working}</div></div>
			<div class="tpg-kpi"><div class="tpg-kpi-label">Overdue</div><div class="tpg-kpi-value">${stats.overdue}</div></div>
		</div>
		<div class="tpg-card">
			<table class="tpg-table">
				<thead>
					<tr>
						<th style="width:34%">Task Name</th>
						<th style="width:14%">Status</th>
						<th style="width:14%">Start Date</th>
						<th style="width:14%">End Date</th>
						<th style="width:24%">Progress</th>
					</tr>
				</thead>
				<tbody id="tpg-tbody"></tbody>
			</table>
		</div>
	`);

	tpg_render_rows();
}

function tpg_render_rows() {
	const tasks = _tpg_state.tasks;
	if (!tasks.length) {
		$("#tpg-tbody").html(`<tr><td colspan="5"><div class="tpg-empty">No tasks found for this project.</div></td></tr>`);
		return;
	}

	const rows = tpg_flatten(tasks, 0);
	const html = rows.map(({ node, depth }) => {
		const hasChildren = node.children && node.children.length > 0;
		const collapsed = !!_tpg_state.collapsed[node.name];
		const toggle = hasChildren
			? `<span class="tpg-toggle${collapsed ? " collapsed" : ""}" data-toggle="${frappe.utils.escape_html(node.name)}">▾</span>`
			: `<span class="tpg-toggle-spacer"></span>`;
		const progress = Math.max(0, Math.min(100, Math.round(node.progress || 0)));

		return `
			<tr class="${hasChildren ? "tpg-row-parent" : ""}">
				<td>
					<div class="tpg-name-cell" style="padding-left:${depth * 22}px">
						${toggle}
						<a class="tpg-task-link" href="/app/task/${encodeURIComponent(node.name)}" target="_blank">${frappe.utils.escape_html(node.subject || node.name)}</a>
					</div>
				</td>
				<td>${tpg_status_badge(node.status)}</td>
				<td class="tpg-date">${tpg_fmt_date(node.exp_start_date)}</td>
				<td class="tpg-date">${tpg_fmt_date(node.exp_end_date)}</td>
				<td>
					<div class="tpg-progress-wrap">
						<div class="tpg-progress-bar"><div class="tpg-progress-fill" style="width:${progress}%"></div></div>
						<div class="tpg-progress-pct">${progress}%</div>
					</div>
				</td>
			</tr>
		`;
	}).join("");

	$("#tpg-tbody").html(html);
	$("#tpg-tbody .tpg-toggle[data-toggle]").on("click", function () {
		const name = $(this).data("toggle");
		_tpg_state.collapsed[name] = !_tpg_state.collapsed[name];
		tpg_render_rows();
	});
}
