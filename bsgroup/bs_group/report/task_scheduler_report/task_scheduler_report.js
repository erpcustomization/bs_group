// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

const PRIORITY_STYLE = {
	"Low":    { bg: "#e3f2fd", color: "#1565c0" },
	"Medium": { bg: "#fff8e1", color: "#f57f17" },
	"High":   { bg: "#fff3e0", color: "#e65100" },
	"Urgent": { bg: "#fce4ec", color: "#b71c1c" },
};

const STATUS_STYLE = {
	"Advance Payment - Invoice":    { bg: "#f3e5f5", color: "#6a1b9a" },
	"Pre-Implementation":           { bg: "#ede7f6", color: "#4527a0" },
	"Project Planning":             { bg: "#e8eaf6", color: "#283593" },
	"Delivery in Progress":         { bg: "#e0f2f1", color: "#00695c" },
	"In House Testing":             { bg: "#f1f8e9", color: "#33691e" },
	"Implementation In Progress":   { bg: "#e8f5e9", color: "#2e7d32" },
	"Completed":                    { bg: "#c8e6c9", color: "#1b5e20" },
	"Project Documentation":        { bg: "#e3f2fd", color: "#0d47a1" },
	"Sign-off in Progress":         { bg: "#fff8e1", color: "#f57f17" },
	"Active 3CX AMC Clients":       { bg: "#e0f7fa", color: "#006064" },
	"Active Infra AMC Clients":     { bg: "#b2ebf2", color: "#004d40" },
	"Only Delivery":                { bg: "#fce4ec", color: "#880e4f" },
	"Pending from Implementation":  { bg: "#fff3e0", color: "#bf360c" },
	"Pending from Sales Account":   { bg: "#fff3e0", color: "#bf360c" },
	"Pending from Client":          { bg: "#fff3e0", color: "#bf360c" },
	"Pending Sign-Off":             { bg: "#fff3e0", color: "#e65100" },
	"Pending Invoicing":            { bg: "#fff9c4", color: "#f57f17" },
};

const STATUS_OPTIONS = [
	"Advance Payment - Invoice", "Pre-Implementation", "Project Planning",
	"Delivery in Progress", "In House Testing", "Implementation In Progress",
	"Completed", "Project Documentation", "Sign-off in Progress",
	"Active 3CX AMC Clients", "Active Infra AMC Clients", "Only Delivery",
	"Pending from Implementation", "Pending from Sales Account",
	"Pending from Client", "Pending Sign-Off", "Pending Invoicing",
];

frappe.query_reports["Task Scheduler Report"] = {

	_dnd_key:       "frappe_report_order_task_scheduler",
	_dnd_rendering: false,
	_dnd_state:     null,

	// ── Lifecycle ──────────────────────────────────────────────────────────────
	after_datatable_render: function() {
		let R = frappe.query_reports["Task Scheduler Report"];
		if (R._dnd_rendering) return;

		let data = frappe.query_report.data;
		if (!data || !data.length) return;

		let saved = R._dnd_load();
		if (saved.length) {
			let pos = Object.fromEntries(saved.map((n, i) => [n, i]));
			data.sort((a, b) => (pos[a.name] ?? 1e9) - (pos[b.name] ?? 1e9));
			R._dnd_rendering = true;
			frappe.query_report.render_datatable();
			R._dnd_rendering = false;
		}

		R._dnd_bind();
	},

	// ── Drag binding ──────────────────────────────────────────────────────────
	_dnd_bind: function() {
		let R  = frappe.query_reports["Task Scheduler Report"];
		let el = document.querySelector(".datatable .dt-scrollable");
		if (!el) return;

		if (el._dnd_off) el._dnd_off();

		function down(e) {
			if (!e.target.closest(".drag-handle")) return;
			let row = e.target.closest(".dt-row[data-row-index]");
			if (!row) return;
			e.preventDefault();

			let rect  = row.getBoundingClientRect();
			let clone = row.cloneNode(true);
			Object.assign(clone.style, {
				position: "fixed", zIndex: "9999", pointerEvents: "none",
				top: rect.top + "px", left: rect.left + "px",
				width: rect.width + "px", opacity: "0.85",
				background: "#fff", boxShadow: "0 6px 20px rgba(0,0,0,.18)",
				borderRadius: "3px",
			});
			document.body.appendChild(clone);
			row.style.opacity = "0.25";

			R._dnd_state = {
				row, clone,
				fromIdx:       parseInt(row.dataset.rowIndex),
				startY:        e.clientY,
				cloneStartTop: rect.top,
				targetRow:     null,
				insertBefore:  true,
			};
		}

		function move(e) {
			let s = R._dnd_state;
			if (!s) return;
			e.preventDefault();

			s.clone.style.top = (s.cloneStartTop + e.clientY - s.startY) + "px";

			s.clone.style.display = "none";
			let under = document.elementFromPoint(e.clientX, e.clientY);
			s.clone.style.display = "";

			let overRow = under && under.closest(".dt-row[data-row-index]");

			el.querySelectorAll(".dt-row[data-row-index]").forEach(r => {
				r.style.borderTop = r.style.borderBottom = "";
			});

			if (overRow && overRow !== s.row) {
				let data        = frappe.query_report.data;
				let draggedItem = data[s.fromIdx];
				let overItem    = data[parseInt(overRow.dataset.rowIndex)];

				// Only allow drop among rows with the same parent and same indent level.
				let sameGroup = overItem &&
				    (overItem.parent_task || "") === (draggedItem.parent_task || "") &&
				    (overItem.indent || 0)       === (draggedItem.indent || 0);

				if (sameGroup) {
					let mid = overRow.getBoundingClientRect().top +
					          overRow.getBoundingClientRect().height / 2;
					s.insertBefore = e.clientY < mid;
					overRow.style[s.insertBefore ? "borderTop" : "borderBottom"] = "2px solid #1565c0";
					s.targetRow = overRow;
				} else {
					s.targetRow = null;
				}
			} else {
				s.targetRow = null;
			}
		}

		function up(e) {
			let s = R._dnd_state;
			if (!s) return;
			R._dnd_state = null;

			s.clone.remove();
			s.row.style.opacity = "";
			el.querySelectorAll(".dt-row[data-row-index]").forEach(r => {
				r.style.borderTop = r.style.borderBottom = "";
			});

			if (!s.targetRow) return;

			let fromIdx = s.fromIdx;
			let toIdx   = parseInt(s.targetRow.dataset.rowIndex);
			if (fromIdx === toIdx) return;

			let data = frappe.query_report.data;
			let [item] = data.splice(fromIdx, 1);
			let adj = toIdx > fromIdx ? toIdx - 1 : toIdx;
			data.splice(s.insertBefore ? adj : adj + 1, 0, item);

			R._dnd_save(data.map(r => r.name).filter(Boolean));
			R._dnd_rendering = true;
			frappe.query_report.render_datatable();
			R._dnd_rendering = false;
			R._dnd_bind();
		}

		el.addEventListener("mousedown", down);
		document.addEventListener("mousemove", move);
		document.addEventListener("mouseup", up);

		el._dnd_off = () => {
			el.removeEventListener("mousedown", down);
			document.removeEventListener("mousemove", move);
			document.removeEventListener("mouseup", up);
		};
	},

	// ── Persistence ───────────────────────────────────────────────────────────
	_dnd_save: function(order) {
		try { localStorage.setItem(
			frappe.query_reports["Task Scheduler Report"]._dnd_key,
			JSON.stringify(order)
		); } catch {}
	},
	_dnd_load: function() {
		try { return JSON.parse(localStorage.getItem(
			frappe.query_reports["Task Scheduler Report"]._dnd_key
		) || "[]"); } catch { return []; }
	},

	// ── Filters ────────────────────────────────────────────────────────────────
	filters: [
		{ fieldname: "task",        label: __("Task"),        fieldtype: "Link", options: "Task" },
		{ fieldname: "project",     label: __("Project"),     fieldtype: "Link", options: "Project" },
		{ fieldname: "created_by",  label: __("Created By"),  fieldtype: "Link", options: "User" },
		{ fieldname: "assigned_to", label: __("Assigned To"), fieldtype: "Link", options: "User" },
		{ fieldname: "from_date",   label: __("From Date"),   fieldtype: "Date" },
		{ fieldname: "to_date",     label: __("To Date"),     fieldtype: "Date" },
		{ fieldname: "schedule",    label: __("Schedule"),    fieldtype: "Select", options: "\nScheduled for Today\nNext Day\nWeek" },
		{ fieldname: "task_state",  label: __("Task State"),  fieldtype: "Select", options: "\nClosed\nDelayed" },
	],

	// ── Field helpers ──────────────────────────────────────────────────────────
	_apply_color: function(el) {
		let map   = el.dataset.fieldname === "priority" ? PRIORITY_STYLE : STATUS_STYLE;
		let style = map[el.value] || { bg: "#f5f5f5", color: "#333" };
		el.style.background = style.bg;
		el.style.color      = style.color;
	},

	_save_field: function(el) {
		frappe.call({
			method: "frappe.client.set_value",
			args: { doctype: "Task", name: el.dataset.name, fieldname: el.dataset.fieldname, value: el.value || null },
			callback: r => frappe.show_alert({ message: r.exc ? __("Save failed") : __("Saved"), indicator: r.exc ? "red" : "green" }),
		});
	},

	// ── Formatter ──────────────────────────────────────────────────────────────
	formatter: function(value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);
		if (data.is_group && column.fieldname !== "subject" && column.fieldname !== "progress") return "";

		const rname = `frappe.query_reports['Task Scheduler Report']`;

		if (column.fieldname === "status") {
			let style = STATUS_STYLE[value] || { bg: "#f5f5f5", color: "#333" };
			let opts  = STATUS_OPTIONS.map(o => `<option value="${o}"${o === value ? " selected" : ""}>${o}</option>`).join("");
			return `<select data-fieldname="status" data-name="${data.name}"
						onclick="event.stopPropagation()"
						onchange="${rname}._save_field(this);${rname}._apply_color(this)"
						style="width:100%;border:none;border-radius:4px;padding:2px 4px;cursor:pointer;
						       font-size:inherit;font-weight:500;background:${style.bg};color:${style.color};">
						${opts}</select>`;
		}

		if (column.fieldname === "priority") {
			let style = PRIORITY_STYLE[value] || { bg: "#f5f5f5", color: "#333" };
			let opts  = ["Low","Medium","High","Urgent"].map(o => `<option value="${o}"${o === value ? " selected" : ""}>${__(o)}</option>`).join("");
			return `<select data-fieldname="priority" data-name="${data.name}"
						onclick="event.stopPropagation()"
						onchange="${rname}._save_field(this);${rname}._apply_color(this)"
						style="width:100%;border:none;border-radius:4px;padding:2px 4px;cursor:pointer;
						       font-size:inherit;font-weight:600;background:${style.bg};color:${style.color};">
						${opts}</select>`;
		}

		if (column.fieldname === "exp_start_date" || column.fieldname === "exp_end_date") {
			let dateVal = value ? String(value).split(" ")[0] : "";
			return `<input type="date" data-fieldname="${column.fieldname}" data-name="${data.name}"
						value="${dateVal}" onclick="event.stopPropagation()"
						ondblclick="event.stopPropagation();this.showPicker&&this.showPicker();"
						onchange="${rname}._save_field(this)"
						style="width:100%;border:none;background:transparent;cursor:pointer;font-size:inherit;padding:0;color:inherit;">`;
		}

		if (column.fieldname === "subject" && data.name) {
			value = default_formatter(value, row, column, data);
			let indent = data.indent || 0;
			let icon   = data.is_group ? "📁" : "📄";
			let link   = `/app/task/${encodeURIComponent(data.name)}`;
			let anchor = `<a href="${link}" title="${__("Open Task")}" style="color:inherit;">${value}</a>`;
			let label  = data.is_group ? `<b>${anchor}</b>` : anchor;
			let handle = `<span class="drag-handle" title="${__("Drag to reorder")}"
			                   style="cursor:grab;margin-right:6px;color:#bbb;font-size:15px;
			                          user-select:none;flex-shrink:0;">⠿</span>`;
			return `<div style="padding-left:${indent*20}px;display:flex;align-items:center;">${handle}${icon}&nbsp;${label}</div>`;
		}

		return default_formatter(value, row, column, data);
	},
};
