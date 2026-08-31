const AIRA_ICON   = __('<img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIiB3aWR0aD0iMTYiIGhlaWdodD0iMTYiPjxkZWZzPjxyYWRpYWxHcmFkaWVudCBpZD0iYWlyYWciIGN4PSI1MCUiIGN5PSI2MCUiIHI9IjU1JSIgZng9IjUwJSIgZnk9IjcwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iIzAwZTVjYyIvPjxzdG9wIG9mZnNldD0iNTAlIiBzdG9wLWNvbG9yPSIjM2I2ZWY4Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjN2IzZmU0Ii8+PC9yYWRpYWxHcmFkaWVudD48L2RlZnM+PGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iNDgiIGZpbGw9InVybCgjYWlyYWcpIi8+PHBhdGggZD0iTTI1IDc1IEw1MCAyNSBMNzUgNzUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMTAiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIgZmlsbD0ibm9uZSIvPjxwb2x5Z29uIHBvaW50cz0iNTAsNTIgNTMsNTggNTksNTggNTQsNjIgNTYsNjggNTAsNjQgNDQsNjggNDYsNjIgNDEsNTggNDcsNTgiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjkiLz48L3N2Zz4=" style="width:16px;height:16px;vertical-align:middle;margin-right:4px;border-radius:50%"> AIRA');

frappe.ui.form.on("Project", {
    refresh(frm){
        frm.add_custom_button("Task", () => {
            frappe.new_doc("Task", {
                project: frm.doc.name
            })
        }, __("Create"))

        // ── AIRA Button Group ─────────────────────────────────────────
        frm.add_custom_button(__('📅 Generate Project Plan'),   () => aira_generate_plan(frm),    AIRA_ICON);
        frm.add_custom_button(__('📋 BOQ Verify'),             () => aira_boq_verify(frm),       AIRA_ICON);
        frm.add_custom_button(__('📊 Analyze Progress'),       () => aira_analyze_progress(frm), AIRA_ICON);

        PSU.render(frm);
        PSU.exposeDeveloperTools();

        render_progress_task_tab(frm);
    }

})

// ── "Progress Task" tab (custom_progress_task HTML field) ──────────────
// Renders the same Parent → Child task hierarchy as the Task Progress
// desk page, inline on the Project form. The field ships empty by
// default (it's a plain HTML field) - this is what fills it in.
const _ptt_state = { tasks: [], expanded: {} };

function render_progress_task_tab(frm) {
    const $wrapper = frm.fields_dict.custom_progress_task && frm.fields_dict.custom_progress_task.$wrapper;
    if (!$wrapper) return;

    if (frm.is_new()) {
        $wrapper.html('<div class="text-muted" style="padding:16px 0">Save the project first to see its tasks here.</div>');
        return;
    }

    $wrapper.html('<div class="text-muted" style="padding:16px 0">Loading tasks…</div>');

    frappe.call({
        method: "bsgroup.bs_group.page.task_progress.task_progress.get_project_tasks",
        args: { project: frm.doc.name },
        callback: function (r) {
            _ptt_state.tasks = r.message || [];
            _ptt_state.expanded = {}; // collapsed by default - only parent tasks show until expanded
            ptt_render($wrapper);
        },
    });
}

function ptt_render($wrapper) {
    $wrapper.html(build_progress_task_html(_ptt_state.tasks));
    $wrapper.find(".ptt-toggle[data-toggle]").on("click", function () {
        const name = $(this).data("toggle");
        _ptt_state.expanded[name] = !_ptt_state.expanded[name];
        ptt_render($wrapper);
    });
}

function ptt_status_class(status) {
    const s = (status || "").toLowerCase();
    if (s === "completed") return "ptt-s-completed";
    if (s.includes("overdue")) return "ptt-s-overdue";
    if (s.includes("cancel")) return "ptt-s-cancelled";
    if (s.includes("pending") || s.includes("sign-off") || s.includes("invoic")) return "ptt-s-review";
    if (s.includes("progress") || s.includes("implementation") || s.includes("testing") || s.includes("planning")) return "ptt-s-working";
    return "ptt-s-open";
}

function ptt_flatten(nodes, depth) {
    let rows = [];
    for (const n of nodes) {
        rows.push({ node: n, depth });
        // Only descend into children once the parent has been expanded via its dropdown arrow.
        if (n.children && n.children.length && _ptt_state.expanded[n.name]) {
            rows = rows.concat(ptt_flatten(n.children, depth + 1));
        }
    }
    return rows;
}

function build_progress_task_html(tasks) {
    const style = `
        <style>
            .ptt-table { width: 100%; border-collapse: collapse; font-size: 13px; }
            .ptt-table thead th {
                text-align: left; padding: 10px 12px; background: #f9fafb; border-bottom: 1px solid #e5e7eb;
                font-size: 11px; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
            }
            .ptt-table td { padding: 9px 12px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }
            .ptt-table tbody tr:hover td { background: #f9fafb; }
            .ptt-row-parent td { font-weight: 700; background: #fafbfc; }
            .ptt-name-cell { display: flex; align-items: center; gap: 6px; }
            .ptt-toggle {
                width: 16px; height: 16px; display: inline-flex; align-items: center; justify-content: center;
                cursor: pointer; color: #6b7280; font-size: 10px; border-radius: 4px; flex-shrink: 0;
                transition: transform .15s, background .15s;
            }
            .ptt-toggle:hover { background: #eef2f7; }
            .ptt-toggle.expanded { transform: rotate(90deg); }
            .ptt-toggle-spacer { width: 16px; flex-shrink: 0; }
            .ptt-task-link { color: #1f2937; text-decoration: none; font-weight: 600; }
            .ptt-task-link:hover { color: #2563eb; text-decoration: underline; }
            .ptt-status { display: inline-flex; padding: 3px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; white-space: nowrap; }
            .ptt-s-open      { background: #eff8ff; color: #175cd3; }
            .ptt-s-working   { background: #fff7e6; color: #b45309; }
            .ptt-s-review    { background: #fef3f2; color: #b42318; }
            .ptt-s-overdue   { background: #fef3f2; color: #b42318; }
            .ptt-s-completed { background: #ecfdf3; color: #067647; }
            .ptt-s-cancelled { background: #f3f4f6; color: #475467; }
            .ptt-progress-wrap { display: flex; align-items: center; gap: 8px; min-width: 110px; }
            .ptt-progress-bar { flex: 1; height: 7px; border-radius: 999px; background: #eef0f3; overflow: hidden; }
            .ptt-progress-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg,#2563eb,#22c55e); }
            .ptt-progress-pct { font-size: 12px; font-weight: 700; color: #374151; min-width: 32px; text-align: right; }
            .ptt-empty { color: #9ca3af; text-align: center; padding: 32px 0; font-size: 13px; }
            .ptt-date { color: #4b5563; white-space: nowrap; }
        </style>
    `;

    if (!tasks.length) {
        return style + '<div class="ptt-empty">No tasks found for this project.</div>';
    }

    const rows = ptt_flatten(tasks, 0);
    const body = rows.map(({ node, depth }) => {
        const hasChildren = node.children && node.children.length > 0;
        const expanded = !!_ptt_state.expanded[node.name];
        const toggle = hasChildren
            ? `<span class="ptt-toggle${expanded ? " expanded" : ""}" data-toggle="${frappe.utils.escape_html(node.name)}">▶</span>`
            : `<span class="ptt-toggle-spacer"></span>`;
        const startDate = node.exp_start_date ? frappe.datetime.str_to_user(node.exp_start_date.split(" ")[0]) : "—";
        const endDate = node.exp_end_date ? frappe.datetime.str_to_user(node.exp_end_date.split(" ")[0]) : "—";
        const assignedTo = node.assigned_to ? frappe.utils.escape_html(node.assigned_to) : "—";

        return `
            <tr class="${hasChildren ? "ptt-row-parent" : ""}">
                <td style="padding-left:${12 + depth * 22}px">
                    <div class="ptt-name-cell">
                        ${toggle}
                        <a class="ptt-task-link" href="/app/task/${encodeURIComponent(node.name)}" target="_blank">
                            ${frappe.utils.escape_html(node.subject || node.name)}
                        </a>
                    </div>
                </td>
                <td><span class="ptt-status ${ptt_status_class(node.status)}">${frappe.utils.escape_html(node.status || "Open")}</span></td>
                <td class="ptt-date">${startDate}</td>
                <td class="ptt-date">${endDate}</td>
                <td>${assignedTo}</td>
            </tr>
        `;
    }).join("");

    return `
        ${style}
        <table class="ptt-table">
            <thead>
                <tr>
                    <th style="width:34%">Task Name</th>
                    <th style="width:14%">Status</th>
                    <th style="width:14%">Start Date</th>
                    <th style="width:14%">End Date</th>
                    <th style="width:24%">Assigned To</th>
                </tr>
            </thead>
            <tbody>${body}</tbody>
        </table>
    `;
}

// HELPER: Call Claude API
// ══════════════════════════════════════════════════════════════════════
async function aira_claude(system, user, max_tokens = 4000) {
    // AIRA Gateway v3.0 — Server-side AI call, no browser fetch, no API key exposure
    return new Promise((resolve, reject) => {
        frappe.call({
            method: 'aira_ai_gateway',
            args: {
                caller: 'project_plan',
                system_prompt: system,
                user_message: user,
                max_tokens: max_tokens
            },
            callback: function(r) {
                const res = r.message || {};
                if (res.success && res.text) {
                    resolve(res.text);
                } else {
                    reject(new Error(res.error || 'AI gateway returned no response'));
                }
            },
            error: function(e) {
                reject(new Error('Gateway error: ' + JSON.stringify(e).substring(0, 80)));
            }
        });
    });
}

function aira_generate_plan(frm) {
    const d = new frappe.ui.Dialog({
        title: '📅 AIRA — Generate Project Plan',
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                options: `<div style="background:#eaf4fb;padding:10px 14px;border-radius:6px;margin-bottom:8px;font-size:12px;line-height:1.7">
                    <b>💡 How to use:</b><br>
                    Paste any of the following in the box below:<br>
                    • Technician notes / site survey findings<br>
                    • WhatsApp / email discussion summary<br>
                    • BOQ scope of work text<br>
                    • Verbal briefing notes<br>
                    AIRA will auto-create structured Tasks with milestones in ERPNext.
                </div>`
            },
            {
                label: 'Project Direction / Brief (paste any text)',
                fieldname: 'brief',
                fieldtype: 'Text',
                reqd: 0,
                description: 'Leave blank to use Project Description + current data'
            },
            {
                label: 'Expected Start Date',
                fieldname: 'start_date',
                fieldtype: 'Date',
                default: frm.doc.expected_start_date || frappe.datetime.get_today()
            },
            {
                label: 'Expected End Date',
                fieldname: 'end_date',
                fieldtype: 'Date',
                default: frm.doc.expected_end_date || ''
            },
            { fieldtype: 'Column Break' },
            {
                label: 'Project Type / Domain',
                fieldname: 'domain',
                fieldtype: 'Select',
                options: '\nCCTV / Surveillance\nNetwork Infrastructure\nAccess Control\nELV Systems\nPAVA / Audio\nFirewall / Cybersecurity\nWireless / WiFi\nIT Support / AMC\nStructured Cabling\nGeneral IT',
                default: ''
            },
            {
                label: 'Overwrite existing tasks?',
                fieldname: 'overwrite',
                fieldtype: 'Check',
                default: 0,
                description: 'If checked, deletes existing tasks before creating new ones'
            }
        ],
        primary_action_label: '🤖 Generate & Create Tasks',
        async primary_action(vals) {
            d.hide();
            frappe.show_progress('AIRA is thinking...', 20, 100, 'Analysing project brief...');

            // Gather context from ERPNext
            const tasks_existing = await frappe.db.get_list('Task', {
                filters: [['project', '=', frm.doc.name]],
                fields: ['name', 'subject', 'status', 'is_milestone', 'parent_task'],
                limit: 50
            });

            const brief = (vals.brief || '').trim() || frm.doc.custom_project_description || frm.doc.project_name;
            const domain = vals.domain || 'General IT';
            const start  = vals.start_date || frappe.datetime.get_today();
            const end    = vals.end_date || '';

            const system = `You are an expert IT project manager for Bits Secure IT Infrastructure LLC (UAE).
You create structured project plans for ERPNext with tasks organised as:
- GROUP tasks  (is_group=true)  → act as Phase headers (e.g. "Phase 1: Site Survey")
- MILESTONE tasks (is_milestone=true) → key deliverables
- Regular tasks  → actual work items under a parent group

STRICT OUTPUT FORMAT — respond ONLY with valid JSON array, no markdown, no prose:
[
  {"subject":"Phase 1: Site Preparation","is_group":true,"is_milestone":false,"priority":"Medium","duration_days":3,"description":"...","parent_index":null},
  {"subject":"Site Survey & Assessment","is_group":false,"is_milestone":false,"priority":"High","duration_days":1,"description":"...","parent_index":0},
  {"subject":"✅ Survey Complete","is_group":false,"is_milestone":true,"priority":"High","duration_days":0,"description":"Milestone: site survey signed off","parent_index":0},
  ...
]
Rules:
- parent_index references the array index (0-based) of the parent group task, null if top-level
- duration_days is integer (0 for milestones)
- priority: Low / Medium / High / Urgent
- Include 3-6 phases, each with 2-5 tasks and 1 milestone
- Total tasks: 15-25`;

            const user = `Project: ${frm.doc.project_name}
Customer: ${frm.doc.customer || 'TBD'}
Domain: ${domain}
Start: ${start} | End: ${end || 'TBD'}
Stage: ${frm.doc.custom_current_stage || 'Planning'}

Project Brief / Direction:
${brief}

Existing tasks (do not duplicate):
${tasks_existing.map(t => '- ' + t.subject).join('\n') || 'None yet'}

Generate a complete project plan JSON array now.`;

            try {
                frappe.show_progress('AIRA is thinking...', 60, 100, 'Generating plan...');
                const raw = await aira_claude(system, user, 3000);

                // Parse JSON — strip any accidental markdown fences
                let jsonStr = raw.trim();
                if (jsonStr.startsWith('```')) jsonStr = jsonStr.replace(/^```[^\n]*\n/, '').replace(/```$/, '').trim();
                const plan = JSON.parse(jsonStr);

                frappe.hide_progress();

                // Preview dialog
                aira_show_plan_preview(frm, plan, vals, tasks_existing);

            } catch(e) {
                frappe.hide_progress();
                frappe.msgprint({ title: 'AIRA Error', message: e.message, indicator: 'red' });
            }
        }
    });
    d.show();
}

function aira_show_plan_preview(frm, plan, vals, existing_tasks) {
    let rows = plan.map((t, i) => {
        const indent = t.parent_index !== null ? '&nbsp;&nbsp;&nbsp;&nbsp;' : '';
        const icon = t.is_milestone ? '🏁' : t.is_group ? '📁' : '▸';
        const badge = t.is_milestone
            ? '<span style="background:#27ae60;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px">MILESTONE</span>'
            : t.is_group
                ? '<span style="background:#2980b9;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px">PHASE</span>'
                : '';
        return `<tr style="background:${i%2===0?'#f9f9f9':'#fff'}">
            <td style="padding:5px 8px">${i+1}</td>
            <td style="padding:5px 8px">${indent}${icon} ${t.subject} ${badge}</td>
            <td style="padding:5px 8px;text-align:center">${t.priority}</td>
            <td style="padding:5px 8px;text-align:center">${t.duration_days}d</td>
        </tr>`;
    }).join('');

    const html = `<div style="font-size:13px">
        <p style="margin-bottom:8px">AIRA generated <b>${plan.length} tasks</b> for <b>${frm.doc.project_name}</b>. Review and confirm to create them in ERPNext.</p>
        <table style="width:100%;border-collapse:collapse">
            <thead><tr style="background:#2c3e50;color:#fff;font-size:12px">
                <th style="padding:6px 8px">#</th>
                <th style="padding:6px 8px;text-align:left">Task / Milestone</th>
                <th style="padding:6px 8px">Priority</th>
                <th style="padding:6px 8px">Days</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>
    </div>`;

    frappe.confirm(
        html,
        async () => {
            // User confirmed — create tasks
            frappe.show_progress('Creating tasks...', 10, 100, 'Building project structure...');

            // Optionally delete existing tasks
            if (vals.overwrite && existing_tasks.length > 0) {
                for (const t of existing_tasks) {
                    await frappe.db.delete_doc('Task', t.name);
                }
            }

            const created_names = [];
            let start_dt = new Date(vals.start_date || frappe.datetime.get_today());

            for (let i = 0; i < plan.length; i++) {
                const t = plan[i];
                const exp_start = new Date(start_dt);
                const exp_end   = new Date(start_dt);
                exp_end.setDate(exp_end.getDate() + Math.max(t.duration_days, 1));

                const task_doc = {
                    doctype: 'Task',
                    subject: t.subject,
                    project: frm.doc.name,
                    status: 'Open',
                    priority: t.priority || 'Medium',
                    is_group: t.is_group ? 1 : 0,
                    is_milestone: t.is_milestone ? 1 : 0,
                    exp_start_date: frappe.datetime.obj_to_str(exp_start),
                    exp_end_date:   frappe.datetime.obj_to_str(exp_end),
                    description: t.description || ''
                };

                // Link to parent
                if (t.parent_index !== null && created_names[t.parent_index]) {
                    task_doc.parent_task = created_names[t.parent_index];
                }

                try {
                    const res = await frappe.call({
                        method: 'frappe.client.insert',
                        args: { doc: task_doc }
                    });
                    created_names.push(res.message?.name || null);
                } catch(e) {
                    created_names.push(null);
                }

                // Advance start date for non-groups
                if (!t.is_group) start_dt = exp_end;

                frappe.show_progress('Creating tasks...', Math.round((i+1)/plan.length*90)+10, 100,
                    `Created: ${t.subject}`);
            }

            frappe.hide_progress();
            frappe.show_alert({ message: `✅ ${plan.length} tasks created in PROJ!`, indicator: 'green' });
            frm.reload_doc();
        },
        'Cancel'
    );
}


// ══════════════════════════════════════════════════════════════════════
// FEATURE 2: BOQ VERIFY
// Cross-checks Project BOQ (custom_boq field) against
// Deal Cost Sheet, Quotation, and Sales Order for the same customer
// Highlights: missing items, qty mismatches, price deviations
// ══════════════════════════════════════════════════════════════════════
function aira_boq_verify(frm) {
    if (!frm.doc.customer && !frm.doc.sales_order) {
        frappe.msgprint({
            title: 'No Customer / Sales Order linked',
            message: 'Please link a <b>Customer</b> or <b>Sales Order</b> to this project first, or link a Deal Cost Sheet via the BOQ field.',
            indicator: 'orange'
        });
        return;
    }

    frappe.show_progress('BOQ Verify...', 10, 100, 'Fetching documents...');

    const customer = frm.doc.customer;
    // custom_boq is a Text Editor (HTML) field — strip tags for the AI prompt
    const project_boq_raw = (frm.doc.custom_boq || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

    // Fetch data in parallel
    Promise.all([
        // Deal Cost Sheets for this customer
        frappe.db.get_list('Deal Cost Sheet', {
            filters: customer ? [['customer', '=', customer]] : [],
            fields: ['name', 'customer', 'status'],
            limit: 5,
            order_by: 'creation desc'
        }),
        // Quotations for this customer
        frappe.db.get_list('Quotation', {
            filters: customer ? [['customer_name', '=', customer]] : [],
            fields: ['name', 'customer_name', 'grand_total', 'status'],
            limit: 5,
            order_by: 'creation desc'
        }),
        // Sales Orders for this project/customer
        frappe.db.get_list('Sales Order', {
            filters: customer
                ? [['customer', '=', customer]]
                : frm.doc.sales_order
                    ? [['name', '=', frm.doc.sales_order]]
                    : [],
            fields: ['name', 'customer', 'grand_total', 'status'],
            limit: 3,
            order_by: 'creation desc'
        })
    ]).then(async ([dcs_list, quot_list, so_list]) => {
        frappe.show_progress('BOQ Verify...', 40, 100, 'Loading line items...');

        // Fetch all items from each document type
        let all_sources = [];

        // DCS items
        for (const dcs of dcs_list.slice(0, 2)) {
            const items = await frappe.db.get_list('Deal Cost Item', {
                filters: [['parent', '=', dcs.name]],
                fields: ['item_code', 'item_name', 'qty', 'cost_rate', 'selling_rate', 'item_category'],
                limit: 100
            });
            all_sources.push({ type: 'Deal Cost Sheet', ref: dcs.name, items });
        }

        // Quotation items
        for (const q of quot_list.slice(0, 2)) {
            const items = await frappe.db.get_list('Quotation Item', {
                filters: [['parent', '=', q.name]],
                fields: ['item_code', 'item_name', 'qty', 'rate', 'amount'],
                limit: 100
            });
            all_sources.push({ type: 'Quotation', ref: q.name, items });
        }

        // Sales Order items
        for (const so of so_list.slice(0, 1)) {
            const items = await frappe.db.get_list('Sales Order Item', {
                filters: [['parent', '=', so.name]],
                fields: ['item_code', 'item_name', 'qty', 'rate', 'amount'],
                limit: 100
            });
            all_sources.push({ type: 'Sales Order', ref: so.name, items });
        }

        frappe.show_progress('BOQ Verify...', 70, 100, 'Analysing with AIRA...');

        // Build comparison data
        const sources_summary = all_sources.map(s =>
            `[${s.type}: ${s.ref}]\n` +
            s.items.map(i => `  - ${i.item_code || i.item_name}: qty=${i.qty}, rate=${i.rate || i.selling_rate || i.cost_rate || 0}`).join('\n')
        ).join('\n\n');

        const project_boq_summary = project_boq_raw
            ? project_boq_raw
            : 'No BOQ data available for this project';

        const system = `You are a BOQ verification specialist for an IT infrastructure company in UAE.
Compare the Project BOQ against Deal Cost Sheets, Quotations, and Sales Orders.
Identify:
1. Items in Project BOQ not in any commercial document (MISSING from quote)
2. Items in commercial documents not in Project BOQ (EXTRA — scope creep risk)
3. Qty mismatches (>5% deviation flagged as WARNING)
4. Price deviations vs deal cost sheet (>10% flagged)
5. Overall scope alignment score (%)
Output a clear HTML report with tables and colour-coded status rows.`;

        const user_prompt = `Project: ${frm.doc.project_name}
Customer: ${customer || 'N/A'}

== PROJECT BOQ (pasted by user) ==
${project_boq_summary}

== COMMERCIAL DOCUMENTS (from ERPNext) ==
${sources_summary || 'No linked commercial documents found for this customer.'}

Generate the BOQ Verification Report.`;

        try {
            const report_html = await aira_claude(system, user_prompt, 3000);
            frappe.hide_progress();

            frappe.msgprint({
                title: `📋 BOQ Verification — ${frm.doc.project_name}`,
                message: `<div style="font-size:13px;line-height:1.7">${report_html.replace(/```html/g,'').replace(/```/g,'')}</div>`,
                wide: true
            });
        } catch(e) {
            frappe.hide_progress();
            frappe.msgprint({ title: 'Error', message: e.message, indicator: 'red' });
        }
    });
}

// ══════════════════════════════════════════════════════════════════════
// FEATURE 4: ANALYZE PROJECT PROGRESS
// ══════════════════════════════════════════════════════════════════════
async function aira_analyze_progress(frm) {
    if (!frm.doc.name) return;
    frappe.show_progress('Analysing...', 30, 100, 'Fetching tasks...');

    const tasks = await frappe.db.get_list('Task', {
        filters: [['project', '=', frm.doc.name]],
        fields: ['subject', 'status', 'priority', 'exp_start_date', 'exp_end_date', 'is_milestone', 'progress'],
        limit: 100
    });

    const completed  = tasks.filter(t => t.status === 'Completed').length;
    const overdue    = tasks.filter(t => t.exp_end_date && new Date(t.exp_end_date) < new Date() && t.status !== 'Completed').length;
    const milestones = tasks.filter(t => t.is_milestone);

    const task_details = tasks.map(t =>
        `- ${t.is_milestone ? '🏁 [MILESTONE] ' : ''}${t.subject} [${t.status}]${t.exp_end_date ? ' Due:' + t.exp_end_date.substring(0,10) : ''}`
    ).join('\n');

    frappe.show_progress('Analysing...', 60, 100, 'AIRA reviewing...');

    const system = `You are a project health analyst for an IT infrastructure company in UAE.
    Provide a concise but actionable project health report in HTML format with:
    - RAG status indicator (Red/Amber/Green) with clear reasoning
    - Milestone status table
    - Top 3 risks
    - Recommended immediate actions
    - Completion forecast with confidence %
    Use tables and colour-coded badges for readability.`;

    const user_prompt = `Project: ${frm.doc.project_name}
Customer: ${frm.doc.customer || 'N/A'}
Stage: ${frm.doc.custom_current_stage || 'N/A'}
% Complete: ${frm.doc.percent_complete || 0}%
Total Tasks: ${tasks.length} | Completed: ${completed} | Overdue: ${overdue}
Milestones: ${milestones.length} (${milestones.filter(m => m.status === 'Completed').length} done)

Tasks:\n${task_details}

Generate the project health report.`;

    try {
        const report = await aira_claude(system, user_prompt, 2000);
        frappe.hide_progress();
        frappe.msgprint({
            title: `📊 Project Health — ${frm.doc.project_name}`,
            message: `<div style="font-size:13px;line-height:1.7">${report.replace(/```html/g,'').replace(/```/g,'')}</div>`,
            wide: true
        });
    } catch(e) {
        frappe.hide_progress();
        frappe.msgprint({ title: 'Error', message: e.message, indicator: 'red' });
    }
}


const PSU = {
    // ============================================================
    // MODULE 01 -- CONFIGURATION AND CONSTANTS
    // ============================================================

    CLOSED_TASK_STATUSES: ["Completed"],

    TASK_PAGE_LIMIT: 500,

    HEALTH_WEIGHTS: {
        task_completion: 25,
        overdue_tasks: 20,
        timeline_condition: 20,
        project_progress: 15,
        documentation: 10,
        update_recency: 10
    },

    HEALTH_COMPONENT_LABELS: {
        task_completion: 'Task Completion',
        overdue_tasks: 'Overdue Tasks',
        timeline_condition: 'Timeline Condition',
        project_progress: 'Project Progress',
        documentation: 'Documentation',
        update_recency: 'Update Recency'
    },

    SETUP_EXECUTION_STAGES: ['Material', 'Installation', 'Testing', 'Handover'],

    STAGE_CLASSIFICATION: {
        Planning: 'planning',
        Material: 'pre_execution',
        Installation: 'execution',
        Testing: 'execution',
        Handover: 'post_execution'
    },

    DEBUG: false,

    // ============================================================
    // MODULE 02 -- UTILITIES AND FIELD RESOLUTION
    // ============================================================

    fixWidth: function(frm) {
        const wrapperField = 'custom_project_status_update';
        if (!frm.fields_dict[wrapperField]) return;
        const $w = frm.fields_dict[wrapperField].$wrapper;
        const $col = $w.closest('.form-column');
        const $body = $col.closest('.section-body');
        $w.css('width', '100%');
        $col.css('max-width', '100%').css('flex', '1 1 100%');
        $body.css('max-width', '100%').css('width', '100%');
    },

    isPermissionError: function(err) {
        if (!err) return false;
        const msg = (err.message || err._server_messages || JSON.stringify(err) || '').toString().toLowerCase();
        return msg.indexOf('permission') !== -1 || msg.indexOf('not permitted') !== -1 || (err.exc_type === 'PermissionError');
    },

    esc: function(value) {
        if (value === null || value === undefined) return '';
        return frappe.utils.escape_html(String(value));
    },

    stripHTML: function(html) {
        if (!html) return '';
        const tmp = document.createElement('div');
        tmp.innerHTML = html;
        return (tmp.textContent || tmp.innerText || '').trim();
    },

    clampNum: function(val, min, max) {
        if (typeof val !== 'number' || isNaN(val) || !isFinite(val)) return null;
        return Math.min(max, Math.max(min, val));
    },

    daysSince: function(dateStr) {
        if (!dateStr) return null;
        const diff = frappe.datetime.get_diff(frappe.datetime.get_today(), dateStr);
        return (typeof diff === 'number' && isFinite(diff)) ? diff : null;
    },

    normalizeProjectProgress: function(value) {
        if (typeof value !== 'number' || isNaN(value) || !isFinite(value)) return null;
        return PSU.clampNum(value, 0, 100);
    },

    progressColor: function(pct) {
        if (pct === null || pct === undefined) return 'grey';
        if (pct >= 100) return 'green';
        if (pct >= 80) return 'blue';
        if (pct >= 50) return 'amber';
        return 'red';
    },

    hasMeaningfulText: function(value) {
        if (value === null || value === undefined) return false;
        const text = String(value)
            .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
            .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
            .replace(/<[^>]*>/g, ' ')
            .replace(/&nbsp;/gi, ' ')
            .replace(/&#160;/gi, ' ')
            .replace(/\u00a0/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        return text.length > 0;
    },

    resolveProjectFields: function(frm) {
        function resolveField(fieldname, label) {
            const value = frm.doc[fieldname];
            const df = frappe.meta.get_docfield('Project', fieldname);
            const isLink = !!(df && df.fieldtype === 'Link' && df.options);
            return {
                fieldname: fieldname,
                value: value || null,
                label: label,
                options: isLink ? df.options : null,
                isLink: isLink
            };
        }
        return {
            customer: resolveField('customer', 'Customer'),
            projectManager: resolveField('custom_project_manager', 'Project Manager'),
            department: resolveField('department', 'Department'),
            stage: resolveField('custom_current_stage', 'Stage')
        };
    },

    focusFieldFromCard: function(frm, fieldname) {
        const fld = (frm && fieldname) ? frm.get_field(fieldname) : null;
        if (!fld || (fld.df && fld.df.hidden) || !PSU.focusProjectField(frm, fieldname)) {
            frappe.show_alert({ message: 'This field is not available on the current form.', indicator: 'orange' });
            return false;
        }
        return true;
    },
    focusProjectField: function(frm, fieldname) {
        if (!frm || !fieldname) { return false; }
        try {
            const field = frm.get_field(fieldname);
            if (!field) { return false; }
            frm.scroll_to_field(fieldname);
            return true;
        } catch (e) {
            console.error('PSU: unable to focus field', fieldname, e);
            return false;
        }
    },

    // ============================================================
    // MODULE 03 -- DATA FETCHING
    // ============================================================

    fetchTasks: function(frm) {
        return frappe.db.get_list('Task', {
            filters: { project: frm.doc.name },
            fields: ['name', 'status', 'priority', 'exp_end_date', '_assign', 'project', 'is_group', 'docstatus'],
            limit: PSU.TASK_PAGE_LIMIT,
            order_by: 'modified desc'
        }).then(function(rows) {
            rows = rows || [];
            const rawCount = rows.length;
            const seen = new Set();
            const unique = [];
            rows.forEach(function(r) {
                if (r && r.name && !seen.has(r.name)) { seen.add(r.name); unique.push(r); }
            });
            const verified = unique.filter(function(r) { return r.project === frm.doc.name; });
            const notCancelled = verified.filter(function(r) { return r.docstatus !== 2; });
            const notGroup = notCancelled.filter(function(r) { return !r.is_group; });
            if (PSU.DEBUG === true) {
                console.log('PSU: Raw task count', rawCount, '/ Unique task count', unique.length, '/ Counted task records', notGroup.length);
            }
            return {
                tasks: notGroup,
                rawCount: rawCount,
                truncated: rawCount >= PSU.TASK_PAGE_LIMIT,
                permissionError: false,
                loadError: false
            };
        });
    },

    classifyTasks: function(tasks) {
        const today = frappe.datetime.get_today();
        const weekAhead = frappe.datetime.add_days(today, 7);
        const result = { openCount: 0, closedCount: 0, totalCount: 0, completionPct: 0, overdueCount: 0, dueSoonCount: 0, unassignedCount: 0, assignedCount: 0, highPriorityCount: 0 };
        tasks.forEach(function(t) {
            const isClosed = PSU.CLOSED_TASK_STATUSES.includes(t.status);
            result.totalCount++;
            if (isClosed) { result.closedCount++; return; }
            result.openCount++;
            const assignees = PSU.parseAssign(t._assign);
            if (assignees.length === 0) { result.unassignedCount++; } else { result.assignedCount++; }
            if (t.priority && ['High', 'Urgent'].includes(t.priority)) { result.highPriorityCount++; }
            if (t.exp_end_date) {
                if (t.exp_end_date < today) { result.overdueCount++; }
                else if (t.exp_end_date >= today && t.exp_end_date <= weekAhead) { result.dueSoonCount++; }
            }
        });
        result.completionPct = result.totalCount > 0 ? Math.round((result.closedCount / result.totalCount) * 100) : 0;
        return result;
    },

    parseAssign: function(assignField) {
        if (!assignField) return [];
        try {
            const parsed = JSON.parse(assignField);
            return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
        } catch (e) { return []; }
    },

    // ============================================================
    // MODULE 04 -- BUSINESS CALCULATIONS
    // ============================================================

    calcDescription: function(frm) {
        const raw = frm.doc.custom_project_description || frm.doc.notes || frm.doc.description || '';
        const text = PSU.stripHTML(raw);
        return { present: PSU.hasMeaningfulText(raw), text: text };
    },

    calcBOQ: function(frm) {
        const html = frm.doc.custom_boq || '';
        function parseStructured() {
            if (!html || PSU.stripHTML(html).length === 0) {
                return { status: 'Pending', rows: 0, validRows: 0, incompleteRows: 0, reason: 'No BOQ data entered yet.' };
            }
            let rows = 0, validRows = 0, incompleteRows = 0, qtyColIdentified = true;
            try {
                const tmp = document.createElement('div');
                tmp.innerHTML = html;
                const table = tmp.querySelector('table');
                if (!table) {
                    return { status: 'Validation Unavailable', rows: 0, validRows: 0, incompleteRows: 0, reason: 'No table structure found in BOQ content.' };
                }
                const headerCells = Array.from(table.querySelectorAll('tr:first-child th, tr:first-child td')).map(function(c) { return (c.textContent || '').trim().toLowerCase(); });
                let qtyColIndex = headerCells.findIndex(function(h) { return h.indexOf('qty') !== -1 || h.indexOf('quantity') !== -1; });
                if (qtyColIndex === -1) { qtyColIdentified = false; }
                const bodyRows = Array.from(table.querySelectorAll('tr')).slice(1);
                bodyRows.forEach(function(tr) {
                    const cells = Array.from(tr.querySelectorAll('td'));
                    if (cells.length === 0) return;
                    rows++;
                    if (!qtyColIdentified) { incompleteRows++; return; }
                    const qtyText = (cells[qtyColIndex] && cells[qtyColIndex].textContent || '').trim();
                    const qtyVal = parseFloat(qtyText);
                    if (qtyText.length > 0 && !isNaN(qtyVal) && qtyVal > 0) { validRows++; } else { incompleteRows++; }
                });
                if (!qtyColIdentified) {
                    return { status: 'Validation Unavailable', rows: rows, validRows: 0, incompleteRows: rows, reason: 'Quantity column could not be identified.' };
                }
                if (rows === 0) {
                    return { status: 'Pending', rows: 0, validRows: 0, incompleteRows: 0, reason: 'BOQ table has no data rows.' };
                }
                if (validRows === rows) {
                    return { status: 'Complete', rows: rows, validRows: validRows, incompleteRows: incompleteRows, reason: 'All ' + rows + ' BOQ rows have valid quantities.' };
                } else if (validRows > 0) {
                    return { status: 'Partially Complete', rows: rows, validRows: validRows, incompleteRows: incompleteRows, reason: incompleteRows + ' of ' + rows + ' rows are missing valid quantities.' };
                } else {
                    return { status: 'Incomplete', rows: rows, validRows: validRows, incompleteRows: incompleteRows, reason: 'None of the ' + rows + ' BOQ rows have valid quantities.' };
                }
            } catch (e) {
                return { status: 'Validation Unavailable', rows: 0, validRows: 0, incompleteRows: 0, reason: 'Unable to parse BOQ content.' };
            }
        }
        const structuredResult = parseStructured();
        const isStructuredValid = (structuredResult.status === 'Complete' || structuredResult.status === 'Partially Complete');
        if (isStructuredValid) {
            return Object.assign({}, structuredResult, { configured: true, structured: true, itemCount: structuredResult.validRows, analysisAvailable: true });
        }
        if (PSU.hasMeaningfulText(html)) {
            return { status: 'Configured (Unstructured)', configured: true, structured: false, rows: structuredResult.rows, validRows: structuredResult.validRows, incompleteRows: structuredResult.incompleteRows, itemCount: null, analysisAvailable: false, reason: 'BOQ content is available. Item-level analysis is unavailable because the BOQ is not stored in a structured table.' };
        }
        return Object.assign({}, structuredResult, { configured: false, structured: false, itemCount: 0, analysisAvailable: false });
    },

    timelineFields: function(frm) {
        const start = frm.doc.expected_start_date || null;
        const end = frm.doc.expected_end_date || null;
        return { start: start, end: end, hasBoth: !!(start && end) };
    },

    calcTimeline: function(frm, tf) {
        const today = frappe.datetime.get_today();
        if (!tf.hasBoth) {
            return { configured: false, invalid: false, daysRemaining: null, status: 'Timeline Not Configured', totalDuration: null, elapsedDuration: null, timelineProgress: null };
        }
        const totalDuration = frappe.datetime.get_diff(tf.end, tf.start);
        if (typeof totalDuration !== 'number' || isNaN(totalDuration) || totalDuration < 0) {
            return { configured: true, invalid: true, daysRemaining: null, status: 'Invalid Timeline', totalDuration: null, elapsedDuration: null, timelineProgress: null };
        }
        const daysRemaining = frappe.datetime.get_diff(tf.end, today);
        const elapsedDuration = frappe.datetime.get_diff(today, tf.start);
        let timelineProgress = null;
        if (totalDuration > 0) {
            timelineProgress = PSU.clampNum((elapsedDuration / totalDuration) * 100, 0, 100);
        } else {
            timelineProgress = today >= tf.end ? 100 : 0;
        }
        let status;
        if (daysRemaining < 0) { status = 'Overdue'; }
        else if (daysRemaining === 0) { status = 'Due Today'; }
        else { status = 'On Schedule'; }
        return { configured: true, invalid: false, daysRemaining: daysRemaining, status: status, totalDuration: totalDuration, elapsedDuration: elapsedDuration, timelineProgress: timelineProgress };
    },

    calcScheduleVariance: function(timeline, projectProgress, taskStats) {
        if (!timeline.configured) { return { variance: null, label: 'Timeline Not Configured', color: 'grey' }; }
        if (timeline.invalid) { return { variance: null, label: 'Invalid Timeline', color: 'grey' }; }
        if (taskStats.totalCount > 0 && taskStats.completionPct === 100) { return { variance: null, label: 'Completed', color: 'green' }; }
        if (timeline.status === 'Overdue') { return { variance: null, label: 'Overdue', color: 'red' }; }
        if (projectProgress === null || timeline.timelineProgress === null) { return { variance: null, label: 'Timeline Not Configured', color: 'grey' }; }
        const variance = projectProgress - timeline.timelineProgress;
        let label, color;
        if (variance >= 5) { label = 'Ahead'; color = 'green'; }
        else if (variance >= -5) { label = 'On Track'; color = 'green'; }
        else if (variance >= -15) { label = 'At Risk'; color = 'amber'; }
        else { label = 'Behind'; color = 'red'; }
        return { variance: variance, label: label, color: color };
    },

    calcReadiness: function(frm, descInfo, boqInfo, timeline, taskStats) {
        const components = [];
        let score = 0;
        if (descInfo.present) { components.push({ label: 'Project Description', met: true }); score += 25; }
        else { components.push({ label: 'Project Description', met: false }); }
        if (boqInfo.status === 'Complete' || (boqInfo.configured && !boqInfo.structured)) { components.push({ label: 'BOQ', met: true }); score += 25; }
        else if (boqInfo.status === 'Partially Complete') { components.push({ label: 'BOQ (Partial)', met: 'partial' }); score += 12.5; }
        else { components.push({ label: 'BOQ', met: false }); }
        const hasStart = !!frm.doc.expected_start_date;
        const hasEnd = !!frm.doc.expected_end_date;
        if (hasStart && hasEnd) { components.push({ label: 'Timeline', met: true }); score += 25; }
        else if (hasStart || hasEnd) { components.push({ label: 'Timeline (Partial)', met: 'partial' }); score += 12.5; }
        else { components.push({ label: 'Timeline', met: false }); }
        if (taskStats.totalCount >= 1) { components.push({ label: 'At Least 1 Task', met: true }); score += 25; }
        else { components.push({ label: 'At Least 1 Task', met: false }); }
        return { score: Math.round(score), components: components };
    },

    calcHealth: function(frm, taskStats, timeline, boqInfo, descInfo, projectProgress) {
        const scores = {};
        const unavailable = [];
        const unavailableReasons = {};
        if (taskStats.totalCount > 0) { scores.task_completion = taskStats.completionPct; } else { unavailable.push('task_completion'); unavailableReasons.task_completion = 'no tasks recorded'; }
        if (taskStats.openCount > 0) { scores.overdue_tasks = PSU.clampNum(100 - (taskStats.overdueCount / taskStats.openCount) * 100, 0, 100); }
        else if (taskStats.totalCount > 0) { scores.overdue_tasks = 100; }
        else { unavailable.push('overdue_tasks'); unavailableReasons.overdue_tasks = 'no tasks recorded'; }
        if (timeline.configured && !timeline.invalid) {
            if (timeline.status === 'Overdue') { scores.timeline_condition = 0; }
            else if (taskStats.totalCount > 0 && taskStats.completionPct === 100) { scores.timeline_condition = 100; }
            else if (timeline.timelineProgress !== null && projectProgress !== null) {
                const variance = projectProgress - timeline.timelineProgress;
                scores.timeline_condition = PSU.clampNum(100 - Math.abs(variance), 0, 100);
            } else { unavailable.push('timeline_condition'); unavailableReasons.timeline_condition = 'insufficient data'; }
        } else if (!timeline.configured) { unavailable.push('timeline_condition'); unavailableReasons.timeline_condition = 'timeline not configured'; }
        else { unavailable.push('timeline_condition'); unavailableReasons.timeline_condition = 'invalid timeline dates'; }
        if (projectProgress !== null) { scores.project_progress = projectProgress; } else { unavailable.push('project_progress'); unavailableReasons.project_progress = 'progress not set'; }
        const docParts = [];
        docParts.push(descInfo.present ? 100 : 0);
        if (boqInfo.status === 'Complete') { docParts.push(100); }
        else if (boqInfo.status === 'Partially Complete') { docParts.push(50); }
        else if (boqInfo.status === 'Configured (Unstructured)') { docParts.push(50); }
        else if (boqInfo.status === 'Incomplete' || boqInfo.status === 'Pending') { docParts.push(0); }
        if (docParts.length > 0) { scores.documentation = docParts.reduce(function(a, b) { return a + b; }, 0) / docParts.length; }
        else { unavailable.push('documentation'); unavailableReasons.documentation = 'insufficient data'; }
        const recencyDays = PSU.daysSince(frm.doc.modified);
        if (recencyDays !== null) {
            if (recencyDays <= 7) { scores.update_recency = 100; }
            else if (recencyDays <= 30) { scores.update_recency = 70; }
            else if (recencyDays <= 90) { scores.update_recency = 40; }
            else { scores.update_recency = 10; }
        } else { unavailable.push('update_recency'); unavailableReasons.update_recency = 'record modified date unavailable'; }
        const availableKeys = Object.keys(PSU.HEALTH_WEIGHTS).filter(function(k) { return scores.hasOwnProperty(k); });
        if (availableKeys.length === 0) { return { state: 'Unavailable', isProvisional: false, score: null, label: 'Unavailable', color: 'grey', unavailable: unavailable, unavailableReasons: unavailableReasons }; }
        const availableWeightTotal = availableKeys.reduce(function(sum, k) { return sum + PSU.HEALTH_WEIGHTS[k]; }, 0);
        let weighted = 0;
        availableKeys.forEach(function(k) { weighted += scores[k] * (PSU.HEALTH_WEIGHTS[k] / availableWeightTotal); });
        const finalScore = PSU.clampNum(weighted, 0, 100);
        let label, color;
        if (finalScore >= 80) { label = 'Healthy'; color = 'green'; }
        else if (finalScore >= 60) { label = 'Needs Attention'; color = 'amber'; }
        else { label = 'Critical'; color = 'red'; }
        if (unavailable.length > 0) { return { state: 'Provisional', isProvisional: true, score: finalScore, label: label, color: color, unavailable: unavailable, unavailableReasons: unavailableReasons }; }
        return { state: 'Complete', isProvisional: false, score: finalScore, label: label, color: color, unavailable: [], unavailableReasons: {} };
    },

    calcLatestUpdate: function(frm) {
        const updateText = PSU.stripHTML(frm.doc.custom_latest_update || '');
        const recordRecencyDays = PSU.daysSince(frm.doc.modified);
        return { text: updateText, present: updateText.length > 0, recordRecencyDays: recordRecencyDays };
    },

    calcRisks: function(ctx) {
        const risks = [];
        function add(severity, message) { risks.push({ severity: severity, message: message }); }
        if (ctx.taskStats.overdueCount > 0) { add('Critical', ctx.taskStats.overdueCount + ' open task(s) are overdue.'); }
        if (ctx.timeline.configured && !ctx.timeline.invalid && ctx.timeline.status === 'Overdue') { add('Critical', 'Project timeline end date has passed and the project is not yet complete.'); }
        if (ctx.timeline.invalid) { add('Warning', 'Timeline dates are invalid (end date is before start date).'); }
        if (ctx.scheduleVariance.label === 'Behind') { add('Critical', 'Project progress is significantly behind the expected timeline schedule.'); }
        else if (ctx.scheduleVariance.label === 'At Risk') { add('Warning', 'Project progress is trailing behind the expected timeline schedule.'); }
        if (ctx.taskStats.dueSoonCount > 0) { add('Warning', ctx.taskStats.dueSoonCount + ' open task(s) are due within the next 7 days.'); }
        if (ctx.taskStats.unassignedCount > 0) { add('Warning', ctx.taskStats.unassignedCount + ' open task(s) have no assignee.'); }
        if (ctx.taskStats.highPriorityCount > 0) { add('Warning', ctx.taskStats.highPriorityCount + ' open task(s) are marked High/Urgent priority.'); }
        if (ctx.taskStats.totalCount === 0) { add('Information', 'No tasks have been created for this project yet.'); }
        if (ctx.boqInfo.status === 'Incomplete') { add('Warning', 'BOQ has been started but contains no valid quantities.'); }
        else if (ctx.boqInfo.status === 'Partially Complete') { add('Information', 'BOQ is partially complete - some rows are missing valid quantities.'); }
        else if (ctx.boqInfo.status === 'Pending') { add('Information', 'BOQ has not been entered yet.'); }
        else if (ctx.boqInfo.status === 'Validation Unavailable') { add('Information', 'BOQ could not be automatically validated.'); }
        if (!ctx.timeline.configured) { add('Information', 'Project timeline dates have not been configured.'); }
        if (!ctx.descInfo.present) { add('Information', 'Project description has not been filled in.'); }
        if (!ctx.latestUpdate.present) { add('Information', 'No latest update has been posted for this project.'); }
        if (ctx.latestUpdate.recordRecencyDays !== null && ctx.latestUpdate.recordRecencyDays > 30) { add('Information', 'This project record has not been updated in ' + ctx.latestUpdate.recordRecencyDays + ' days.'); }
        if (ctx.truncated) { add('Warning', 'Task results limited to the first ' + PSU.TASK_PAGE_LIMIT + ' records - some metrics may be incomplete.'); }
        const seenMsgs = new Set();
        const deduped = risks.filter(function(r) { if (seenMsgs.has(r.message)) return false; seenMsgs.add(r.message); return true; });
        const severityOrder = { Critical: 0, Warning: 1, Information: 2 };
        deduped.sort(function(a, b) { return severityOrder[a.severity] - severityOrder[b.severity]; });
        return { all: deduped, top5: deduped.slice(0, 5), totalCount: deduped.length };
    },

        progressBarHTML: function(pct, color) {
        const displayPct = (pct === null || pct === undefined) ? 0 : Math.round(pct);
        const label = (pct === null || pct === undefined) ? '—' : displayPct + '%';
        return '<div class="psu-progress-track"><div class="psu-progress-fill psu-fill-' + color + '" style="width:' + displayPct + '%;"></div></div><span class="psu-progress-value">' + label + '</span>';
    },

    // ============================================================
    // MODULE 05 -- SETUP GOVERNANCE
    // ============================================================

    evaluateProjectSetup: function(frm, model) {
        const rf = PSU.resolveProjectFields(frm);
        const items = [];
        function addItem(opts) {
            items.push({
                key: opts.key,
                label: opts.label,
                state: opts.state,
                stateLabel: opts.stateLabel,
                critical: !!opts.critical,
                fieldname: opts.fieldname || null,
                value: opts.value !== undefined ? opts.value : null,
                message: opts.message || '',
                actionLabel: opts.actionLabel || ''
            });
        }

        addItem(frm.doc.customer ?
            { key: 'customer', label: 'Customer', critical: true, state: 'complete', stateLabel: 'Complete', fieldname: 'customer', value: frm.doc.customer } :
            { key: 'customer', label: 'Customer', critical: true, state: 'missing', stateLabel: 'Missing', fieldname: 'customer', message: 'Customer is not linked to this project.', actionLabel: 'Select Customer' });

        addItem(rf.projectManager.value ?
            { key: 'project_manager', label: 'Project Manager', critical: true, state: 'complete', stateLabel: 'Complete', fieldname: 'custom_project_manager', value: rf.projectManager.value } :
            { key: 'project_manager', label: 'Project Manager', critical: true, state: 'missing', stateLabel: 'Missing', fieldname: 'custom_project_manager', message: 'Project Manager is not assigned.', actionLabel: 'Add Project Manager' });

        addItem(frm.doc.department ?
            { key: 'department', label: 'Department', critical: false, state: 'complete', stateLabel: 'Complete', fieldname: 'department', value: frm.doc.department } :
            { key: 'department', label: 'Department', critical: false, state: 'missing', stateLabel: 'Missing', fieldname: 'department', message: 'Department is not set for this project.', actionLabel: 'Select Department' });

        addItem(rf.stage.value ?
            { key: 'project_stage', label: 'Project Stage', critical: false, state: 'complete', stateLabel: 'Complete', fieldname: 'custom_current_stage', value: rf.stage.value } :
            { key: 'project_stage', label: 'Project Stage', critical: false, state: 'missing', stateLabel: 'Missing', fieldname: 'custom_current_stage', message: 'Project Stage has not been selected.', actionLabel: 'Select Project Stage' });

        addItem(model.descInfo.present ?
            { key: 'description', label: 'Project Description', critical: true, state: 'complete', stateLabel: 'Complete', fieldname: 'custom_project_description', value: true } :
            { key: 'description', label: 'Project Description', critical: true, state: 'missing', stateLabel: 'Missing', fieldname: 'custom_project_description', message: 'Project Description is missing.', actionLabel: 'Add Description' });

        if (model.boqInfo.configured && model.boqInfo.structured) {
            addItem({ key: 'boq', label: 'BOQ', critical: true, state: 'complete', stateLabel: 'Complete', fieldname: 'custom_boq', value: true });
        } else if (model.boqInfo.status === 'Configured (Unstructured)') {
            addItem({ key: 'boq', label: 'BOQ', critical: true, state: 'partial', stateLabel: 'Partial \u2014 unstructured', fieldname: 'custom_boq', value: true, message: 'BOQ exists but is unstructured.', actionLabel: 'Structure BOQ' });
        } else {
            addItem({ key: 'boq', label: 'BOQ', critical: true, state: 'missing', stateLabel: 'Missing', fieldname: 'custom_boq', message: 'BOQ has not been entered.', actionLabel: 'Add BOQ' });
        }

        addItem(frm.doc.expected_start_date ?
            { key: 'expected_start_date', label: 'Expected Start Date', critical: true, state: 'complete', stateLabel: 'Complete', fieldname: 'expected_start_date', value: frm.doc.expected_start_date } :
            { key: 'expected_start_date', label: 'Expected Start Date', critical: true, state: 'missing', stateLabel: 'Missing', fieldname: 'expected_start_date', message: 'Expected Start Date is missing.', actionLabel: 'Configure Timeline' });

        addItem(frm.doc.expected_end_date ?
            { key: 'expected_end_date', label: 'Expected End Date', critical: true, state: 'complete', stateLabel: 'Complete', fieldname: 'expected_end_date', value: frm.doc.expected_end_date } :
            { key: 'expected_end_date', label: 'Expected End Date', critical: true, state: 'missing', stateLabel: 'Missing', fieldname: 'expected_end_date', message: 'Expected End Date is missing.', actionLabel: 'Configure Timeline' });

        addItem(model.taskStats.totalCount >= 1 ?
            { key: 'has_tasks', label: 'At Least One Task', critical: true, state: 'complete', stateLabel: 'Complete', value: model.taskStats.totalCount } :
            { key: 'has_tasks', label: 'At Least One Task', critical: true, state: 'missing', stateLabel: 'Missing', message: 'No tasks have been created for this project yet.', actionLabel: 'View Tasks' });

        const criticalItems = items.filter(function(it) { return it.critical; });
        const criticalMissing = criticalItems.filter(function(it) { return it.state === 'missing'; });
        const criticalPartial = criticalItems.filter(function(it) { return it.state === 'partial'; });
        const missingCount = items.filter(function(it) { return it.state === 'missing'; }).length;
        const partialCount = items.filter(function(it) { return it.state === 'partial'; }).length;

        const stageValue = rf.stage.value;
        const stageClassification = stageValue ? (PSU.STAGE_CLASSIFICATION[stageValue] || 'unknown') : null;
        const isExecutionStage = stageClassification === 'execution';

        let status, label, message;
        if (criticalMissing.length > 0) {
            status = 'incomplete';
            label = 'Setup Incomplete';
            message = criticalMissing.length + ' required setup item' + (criticalMissing.length === 1 ? ' is' : 's are') + ' missing before project execution.';
            if (stageClassification === 'planning') {
                message = 'Project setup is incomplete during the planning stage.';
            } else if (stageClassification === 'pre_execution') {
                message = 'Pre-execution preparation has started while setup information is incomplete.';
            } else if (stageClassification === 'execution') {
                message = 'Execution has started while required setup information is incomplete.';
            } else if (stageClassification === 'post_execution') {
                message = 'The project has reached handover while required setup information remains incomplete.';
            } else if (stageClassification === 'unknown') {
                message = 'Project setup is incomplete.';
            }
        } else if (criticalPartial.length > 0) {
            status = 'review';
            label = 'Setup Requires Review';
            const boqPartial = criticalPartial.some(function(it) { return it.key === 'boq'; });
            message = boqPartial ? 'Project setup is complete, but the BOQ requires structuring.' : (criticalPartial.length + ' setup item(s) require review before project execution.');
        } else {
            status = 'ready';
            label = 'Ready for Execution';
            message = 'All required setup items are complete.';
        }

        const attentionItems = [];
        function attn(group, text) { attentionItems.push({ group: group, text: text }); }
        if (!frm.doc.customer) { attn('warning', 'Customer is not linked to this project.'); }
        if (!rf.projectManager.value) { attn('warning', 'Project Manager is not assigned.'); }
        if (!frm.doc.department) { attn(isExecutionStage ? 'warning' : 'info', 'Department is not set for this project.'); }
        if (!rf.stage.value) { attn(isExecutionStage ? 'warning' : 'info', 'Project Stage has not been selected.'); }
        if (model.boqInfo.status === 'Configured (Unstructured)') { attn('info', 'BOQ exists but is unstructured.'); }

        return {
            status: status,
            label: label,
            message: message,
            items: items,
            missingCount: missingCount,
            partialCount: partialCount,
            criticalMissingCount: criticalMissing.length,
            criticalPartialCount: criticalPartial.length,
            isExecutionStage: isExecutionStage,
            attentionItems: attentionItems
        };
    },

    setupStateClass: function(state) {
        if (state === 'complete') { return 'psu-setup-complete'; }
        if (state === 'partial') { return 'psu-setup-partial'; }
        if (state === 'not_applicable') { return 'psu-setup-na'; }
        return 'psu-setup-missing';
    },

    buildSetupChecklistSection: function(frm, setup) {
        const statusClassMap = { ready: 'psu-setup-banner-ready', review: 'psu-setup-banner-review', incomplete: 'psu-setup-banner-incomplete' };
        const bannerClass = statusClassMap[setup.status] || 'psu-setup-banner-incomplete';
        const header = PSU.sectionHeader('list', 'Project Setup Checklist', 'Ownership, scope, timeline and BOQ readiness before execution');
        const banner = '<div class="psu-setup-banner ' + bannerClass + '"><span class="psu-setup-banner-label">' + PSU.esc(setup.label) + '</span><span class="psu-setup-banner-message">' + PSU.esc(setup.message) + '</span></div>';
        const kickoff = PSU.evaluateKickoffReadiness(setup);
        const kickoffClassMap = { ready: 'psu-kickoff-ready', corrections: 'psu-kickoff-corrections', not_ready: 'psu-kickoff-not-ready' };
        const kickoffClass = kickoffClassMap[kickoff.state] || 'psu-kickoff-not-ready';
        const kickoffHTML = '<div class="psu-kickoff-banner ' + kickoffClass + '"><div class="psu-kickoff-line"><span class="psu-kickoff-title">Kick-off Readiness:</span><span class="psu-kickoff-badge ' + kickoffClass + '">' + PSU.esc(kickoff.label) + '</span></div><div class="psu-kickoff-message">' + PSU.esc(kickoff.message) + '</div></div>';
        const rows = setup.items.map(function(it) {
            const stateCls = PSU.setupStateClass(it.state);
            const explanation = it.message ? PSU.esc(it.message) : '';
            let action = '';
            if (it.state === 'missing' || it.state === 'partial') {
                if (it.key === 'has_tasks') {
                    action = '<button type="button" class="psu-btn psu-btn-secondary psu-qa-btn psu-setup-action" data-action="open-tasks" aria-label="View tasks for this project">' + PSU.esc(it.actionLabel || 'View Tasks') + '</button>';
                } else if (it.fieldname) {
                    action = '<button type="button" class="psu-btn psu-btn-secondary psu-setup-action" data-fieldname="' + PSU.esc(it.fieldname) + '" aria-label="Go to ' + (it.state === 'missing' ? 'missing' : 'partially configured') + ' ' + PSU.esc(it.label) + ' field">' + PSU.esc(it.actionLabel || 'Open Field') + '</button>';
                }
            }
            return '<div class="psu-setup-row">' +
                '<div class="psu-setup-cell psu-setup-cell-label">' + PSU.esc(it.label) + '</div>' +
                '<div class="psu-setup-cell psu-setup-cell-status"><span class="psu-setup-pill ' + stateCls + '">' + PSU.esc(it.stateLabel) + '</span></div>' +
                '<div class="psu-setup-cell psu-setup-cell-explain">' + explanation + '</div>' +
                '<div class="psu-setup-cell psu-setup-cell-action">' + action + '</div>' +
                '</div>';
        }).join('');
        return '<div class="psu-card psu-card-setup">' + header + banner + kickoffHTML +
            '<div class="psu-setup-checklist" role="table" aria-label="Project setup checklist">' +
            '<div class="psu-setup-row psu-setup-row-head" role="row">' +
            '<div class="psu-setup-cell psu-setup-cell-label">Checklist Item</div>' +
            '<div class="psu-setup-cell psu-setup-cell-status">Status</div>' +
            '<div class="psu-setup-cell psu-setup-cell-explain">Explanation</div>' +
            '<div class="psu-setup-cell psu-setup-cell-action">Action</div>' +
            '</div>' + rows + '</div></div>';
    },

    boqTemplateHTML: function() {
        return '<table><thead><tr><th>Item</th><th>Description</th><th>Quantity</th><th>Remarks</th></tr></thead><tbody><tr><td></td><td></td><td></td><td></td></tr></tbody></table>';
    },

    renderBOQFieldGuidance: function(frm, boqInfo) {
        try {
            const field = frm.get_field('custom_boq');
            if (!field || !field.$wrapper) { return; }
            field.$wrapper.find('#psu-boq-guidance-msg').remove();
            field.$wrapper.find('#psu-boq-template-btn-wrap').remove();
            if (field.disabled) { return; }
            const guidance = $('<div id="psu-boq-guidance-msg" class="psu-boq-guidance">For item-level BOQ analysis, use a table with one item per row and a separate Quantity column. Free-text BOQ content is accepted but will be treated as unstructured.</div>');
            field.$wrapper.append(guidance);
            const canInsertTemplate = PSU.canShowBOQTemplateButton(frm, field);
            if (canInsertTemplate) {
                const $btnWrap = $('<div id="psu-boq-template-btn-wrap" class="psu-boq-template-wrap"></div>');
                const $btn = $('<button type="button" class="psu-btn psu-btn-secondary">Insert BOQ Template</button>');
                $btn.on('click', function() {
                    if (!PSU.canShowBOQTemplateButton(frm, frm.get_field('custom_boq'))) {
                        frappe.msgprint('This action is no longer available for the current document state.');
                        return;
                    }
                    frappe.confirm('Insert a blank structured BOQ template? This will not save the Project automatically.', function() {
                        const liveField = frm.get_field('custom_boq');
                        if (!PSU.canShowBOQTemplateButton(frm, liveField)) { return; }
                        const current = frm.doc.custom_boq;
                        if (PSU.hasMeaningfulText(current)) { return; }
                        frm.set_value('custom_boq', PSU.boqTemplateHTML()).then(function() {
                            frm.refresh_field('custom_boq');
                            frm.dirty();
                        });
                    });
                });
                $btnWrap.append($btn);
                field.$wrapper.append($btnWrap);
            }
        } catch (e) {
            console.error('PSU: unable to render BOQ guidance', e);
        }
    },

    canShowBOQTemplateButton: function(frm, field) {
        if (!frm || !frm.doc) { return false; }
        if (frm.doc.docstatus !== 0) { return false; }
        if (!field) { return false; }
        if (field.df && field.df.read_only) { return false; }
        if (field.disabled) { return false; }
        const hasWrite = !!(frm.perm && frm.perm[0] && frm.perm[0].write);
        if (!hasWrite) { return false; }
        if (PSU.hasMeaningfulText(frm.doc.custom_boq)) { return false; }
        return true;
    },

    evaluateKickoffReadiness: function(setup) {
        const criticalItems = (setup.items || []).filter(function(it) { return it.critical; });
        const missingItems = criticalItems.filter(function(it) { return it.state === 'missing'; });
        const partialItems = criticalItems.filter(function(it) { return it.state === 'partial'; });

        let state, label, message;
        if (missingItems.length > 0) {
            state = 'not_ready';
            label = 'Not Ready for Kick-off';
            const names = missingItems.map(function(it) { return it.label; }).join(', ');
            message = missingItems.length + ' critical item' + (missingItems.length === 1 ? ' must' : 's must') + ' be completed: ' + names + '.';
        } else if (partialItems.length > 0) {
            state = 'corrections';
            label = 'Ready After Corrections';
            const boqPartial = partialItems.some(function(it) { return it.key === 'boq'; });
            message = boqPartial ? 'The project may proceed after the BOQ is structured for item-level control.' : ('The project has all required setup information, but ' + partialItems.length + ' item(s) should be reviewed before execution.');
        } else {
            state = 'ready';
            label = 'Ready for Kick-off';
            message = 'All required setup information is present. The project is ready to begin execution.';
        }

        return {
            state: state,
            label: label,
            criticalMissingCount: missingItems.length,
            partialCount: partialItems.length,
            missingItems: missingItems.map(function(it) { return it.label; }),
            partialItems: partialItems.map(function(it) { return it.label; }),
            message: message
        };
    },

    // ============================================================
    // MODULE 06 -- UI COMPONENT BUILDERS
    // ============================================================

    statusChip: function(text, color) {
        return '<span class="psu-chip psu-chip-' + color + '">' + PSU.esc(text) + '</span>';
    },

    kpiColor: function(key, value) {
        switch (key) {
            case 'Open': return 'blue';
            case 'Completed': return 'green';
            case 'Overdue': return value > 0 ? 'red' : 'grey';
            case 'Due This Week': return value > 0 ? 'amber' : 'grey';
            case 'Unassigned': return value > 0 ? 'amber' : 'grey';
            case 'High Priority': return value > 0 ? 'red' : 'grey';
            default: return 'grey';
        }
    },

    iconHTML: function(name) {
        try { return frappe.utils.icon(name, 'sm'); } catch (e) { return ''; }
    },

    // === PKG10A / DEF-05 : Employee display-name resolution (presentation only) ===
        // Resolves the linked Employee name for display. The stored Project Manager
        // value and field type are never changed.
        EMP_NAME_CACHE: {},

        employeeDisplay: function(empId) {
            if (!empId) { return ''; }
            if (PSU.EMP_NAME_CACHE[empId]) { return PSU.EMP_NAME_CACHE[empId]; }
            try {
                const local = frappe.get_doc && frappe.get_doc('Employee', empId);
                if (local && local.employee_name) {
                    PSU.EMP_NAME_CACHE[empId] = local.employee_name;
                    return local.employee_name;
                }
            } catch (e) { /* fall back to raw id */ }
            return '';
        },

        resolveEmployeeNames: function($wrapper) {
            try {
                const $nodes = $wrapper.find('[data-psu-emp]');
                if (!$nodes.length) { return; }
                const apply = function() {
                    $nodes.each(function() {
                        const nm = PSU.EMP_NAME_CACHE[$(this).attr('data-psu-emp')];
                        if (nm) { $(this).text(nm); }
                    });
                };
                const ids = [];
                $nodes.each(function() {
                    const id = $(this).attr('data-psu-emp');
                    if (id && !PSU.EMP_NAME_CACHE[id] && ids.indexOf(id) === -1) { ids.push(id); }
                });
                if (!ids.length) { apply(); return; }
                let pending = ids.length;
                const done = function() { pending -= 1; if (pending <= 0) { apply(); } };
                ids.forEach(function(id) {
                    try {
                        Promise.resolve(frappe.db.get_value('Employee', id, 'employee_name')).then(function(r) {
                            if (r && r.message && r.message.employee_name) { PSU.EMP_NAME_CACHE[id] = r.message.employee_name; }
                            done();
                        }, done);
                    } catch (e) { done(); }
                });
            } catch (e) { /* presentation-only: never block the panel */ }
        },

        healthDisplay: function(health) {
        if (health.state === 'Unavailable') { return { text: 'Unavailable', color: 'grey' }; }
        if (health.isProvisional) { return { text: '~' + Math.round(health.score) + '% Provisional', color: 'amber' }; }
        return { text: Math.round(health.score) + '% ' + health.label, color: health.color };
    },

    healthBadgeHTML: function(health) {
        const d = PSU.healthDisplay(health);
        return PSU.statusChip(d.text, d.color);
    },

    collapsibleHeaderInner: function(icon, title, subtitle) {
        return '<span class="psu-card-title">' + PSU.iconHTML(icon) + '<span class="psu-card-title-text">' + PSU.esc(title) + '</span></span>' +
            '<span class="psu-card-subtitle">' + PSU.esc(subtitle) + '</span>';
    },

    wrapCollapsible: function(sectionKey, cardClass, icon, title, subtitle, bodyHtml, expanded) {
        const trigger = '<button type="button" class="psu-collapsible-trigger" data-psu-toggle="' + sectionKey + '" aria-expanded="' + (expanded ? 'true' : 'false') + '" aria-controls="psu-content-' + sectionKey + '">' +
            PSU.collapsibleHeaderInner(icon, title, subtitle) +
            '<span class="psu-chevron' + (expanded ? ' psu-chevron-open' : '') + '">' + PSU.iconHTML('chevron-down') + '</span>' +
            '</button>';
        return '<div class="psu-card ' + cardClass + ' psu-collapsible-card" data-psu-section="' + sectionKey + '">' +
            trigger +
            '<div class="psu-collapsible-content" id="psu-content-' + sectionKey + '"' + (expanded ? '' : ' style="display:none"') + '>' +
            bodyHtml +
            '</div>' +
            '</div>';
    },

    getSectionState: function(frm) {
        try {
            if (typeof localStorage === 'undefined' || !localStorage) { return {}; }
            const raw = localStorage.getItem('psu-section-state:' + frm.doc.name);
            return raw ? JSON.parse(raw) : {};
        } catch (e) { return {}; }
    },

    saveSectionState: function(frm, key, value) {
        try {
            if (typeof localStorage === 'undefined' || !localStorage) { return; }
            const raw = localStorage.getItem('psu-section-state:' + frm.doc.name);
            const state = raw ? JSON.parse(raw) : {};
            state[key] = value;
            localStorage.setItem('psu-section-state:' + frm.doc.name, JSON.stringify(state));
        } catch (e) { /* localStorage unavailable - ignore */ }
    },

    sectionHeader: function(icon, title, subtitle) {
        return '<div class="psu-card-header"><span class="psu-card-title">' + PSU.iconHTML(icon) + '<span class="psu-card-title-text">' + PSU.esc(title) + '</span></span><span class="psu-card-subtitle">' + PSU.esc(subtitle) + '</span></div>';
    },

    // ============================================================
    // MODULE 07 -- DASHBOARD SECTIONS
    // ============================================================

    computeAttentionItems: function(frm, taskStats, risks, setup) {
        const items = [];
        risks.all.forEach(function(r) {
            const group = r.severity === 'Critical' ? 'critical' : (r.severity === 'Warning' ? 'warning' : 'info');
            items.push({ group: group, text: r.message });
        });
        if (setup && setup.attentionItems) { setup.attentionItems.forEach(function(it) { items.push({ group: it.group, text: it.text }); }); }
        if (taskStats.unassignedCount > 0) { items.push({ group: 'warning', text: taskStats.unassignedCount + ' task(s) are currently unassigned.' }); }
        if (taskStats.highPriorityCount > 0) { items.push({ group: 'warning', text: taskStats.highPriorityCount + ' high-priority open task(s) require review.' }); }
        const seen = new Set();
        const deduped = items.filter(function(it) {
            if (seen.has(it.text)) { return false; }
            seen.add(it.text);
            return true;
        });
        const order = { critical: 0, warning: 1, info: 2 };
        deduped.sort(function(a, b) { return order[a.group] - order[b.group]; });
        return deduped;
    },

    buildExecutiveBanner: function(frm, taskStats, health, readiness, attentionItems, setup) {
        const criticalCount = attentionItems.filter(function(i) { return i.group === 'critical'; }).length;
        const warningCount = attentionItems.filter(function(i) { return i.group === 'warning'; }).length;
        const healthDisp = PSU.healthDisplay(health);
        let bannerClass, title, subtitle;
        // === PKG10A / DEF-04 : executive headline severity precedence ===
        // The headline must reflect the most severe applicable condition so that the
        // banner can never contradict the Health or Readiness classifications shown
        // elsewhere in the panel. Health and Readiness values are consumed as-is;
        // neither formula is modified.
        const healthCritical = (health.state !== 'Unavailable' && health.label === 'Critical');
        const setupNeedsReview = !!(setup && setup.status && setup.status !== 'ready');
        if (healthCritical || criticalCount > 0) {
            bannerClass = 'psu-banner-critical';
            title = 'Critical Attention Required';
            subtitle = healthCritical
                ? ('Project health is ' + Math.round(health.score) + '% (Critical).' + (criticalCount > 0 ? ' Critical risks also require immediate review.' : ' Immediate review is required.'))
                : 'One or more critical risks require immediate review.';
        } else if (setupNeedsReview) {
            bannerClass = 'psu-banner-warning';
            title = setup.label || 'Setup Requires Review';
            subtitle = setup.message || 'Required project setup information is incomplete.';
        } else if (warningCount > 0) {
            bannerClass = 'psu-banner-warning';
            title = 'Project Requires Attention';
            subtitle = 'Review overdue tasks and assignment gaps.';
        } else if (health.state === 'Unavailable') {
            bannerClass = 'psu-banner-grey';
            title = 'Status Unavailable';
            subtitle = 'Insufficient data to present a meaningful overall condition.';
        } else {
            bannerClass = 'psu-banner-ontrack';
            title = 'Project On Track';
            subtitle = 'No critical risks or attention items detected.';
        }
        const completionDisplay = taskStats.totalCount > 0 ? taskStats.completionPct + '%' : '—';
        const metrics = [
            { label: 'Completion', value: completionDisplay },
            { label: 'Project Health', value: PSU.esc(healthDisp.text) },
            { label: 'Readiness', value: readiness.score + '%' },
            { label: 'Critical Risks', value: String(criticalCount) },
            { label: 'Warnings', value: String(warningCount) }
        ].map(function(m) {
            return '<div class="psu-banner-metric"><span class="psu-banner-metric-value">' + m.value + '</span><span class="psu-banner-metric-label">' + PSU.esc(m.label) + '</span></div>';
        }).join('');
        return '<section class="psu-executive-banner ' + bannerClass + '" role="status">' +
            '<div class="psu-banner-main">' +
            '<div class="psu-banner-eyebrow">PROJECT STATUS</div>' +
            '<div class="psu-banner-title">' + PSU.esc(title) + '</div>' +
            '<div class="psu-banner-subtitle">' + PSU.esc(subtitle) + '</div>' +
            '</div>' +
            '<div class="psu-banner-metrics">' + metrics + '</div>' +
            '</section>';
    },

    buildExecutiveMetrics: function(taskStats, health) {
        const healthDisp = PSU.healthDisplay(health);
        const completionDisplay = taskStats.totalCount > 0 ? taskStats.completionPct + '%' : '—';
        const items = [
            { label: 'Completion', value: completionDisplay, color: PSU.progressColor(taskStats.completionPct) },
            { label: 'Total Tasks', value: String(taskStats.totalCount), color: 'grey' },
            { label: 'Overdue Tasks', value: String(taskStats.overdueCount), color: taskStats.overdueCount > 0 ? 'red' : 'grey' },
            { label: 'Project Health', value: PSU.esc(healthDisp.text), color: healthDisp.color }
        ];
        const cells = items.map(function(it) {
            return '<div class="psu-executive-metric"><span class="psu-executive-metric-value psu-text-' + it.color + '">' + it.value + '</span><span class="psu-executive-metric-label">' + PSU.esc(it.label) + '</span></div>';
        }).join('');
        return '<div class="psu-executive-metrics">' + cells + '</div>';
    },

    buildProjectTeam: function(frm) {
        const header = PSU.sectionHeader('users', 'Project Team', 'Project ownership at a glance');
        const candidates = [
            { label: 'Project Manager', fieldname: 'custom_project_manager', icon: 'user' },
            { label: 'Department', fieldname: 'department', icon: 'users' }
        ];
        const rows = [];
        candidates.forEach(function(c) {
            const val = frm.doc[c.fieldname];
            if (!val) { return; }
            const df = frappe.meta.get_docfield('Project', c.fieldname);
            // PKG10A / DEF-05: resolve Employee links to the Employee name for display.
            const isEmp = !!(df && df.fieldtype === 'Link' && df.options === 'Employee');
            const dispText = isEmp ? (PSU.employeeDisplay(val) || String(val)) : String(val);
            const empAttr = isEmp ? (' data-psu-emp="' + PSU.esc(val) + '"') : '';
            let valueHTML = '<span' + empAttr + '>' + PSU.esc(dispText) + '</span>';
            if (df && df.fieldtype === 'Link' && df.options) {
                const teamNavAttr = isEmp ? (' data-psu-focus-field="' + PSU.esc(c.fieldname) + '"') : (' data-psu-route-doctype="' + PSU.esc(df.options) + '" data-psu-route-name="' + PSU.esc(val) + '"');
                valueHTML = '<a href="#" class="psu-team-link"' + teamNavAttr + '><span' + empAttr + '>' + PSU.esc(dispText) + '</span></a>';
            }
            rows.push('<div class="psu-team-row">' + PSU.iconHTML(c.icon) + '<span class="psu-team-role">' + PSU.esc(c.label) + '</span><span class="psu-team-value">' + valueHTML + '</span></div>');
        });
        if (rows.length === 0) {
            return '<div class="psu-card psu-card-team">' + header +
                '<div class="psu-empty-state">' + PSU.iconHTML('user') + '<div class="psu-empty-title">No project ownership details are configured.</div></div>' +
                '</div>';
        }
        return '<div class="psu-card psu-card-team">' + header + '<div class="psu-team-list">' + rows.join('') + '</div></div>';
    },

    buildRecentActivity: function(frm, latestUpdate) {
        const header = PSU.sectionHeader('activity', 'Recent Activity', 'Latest known project activity');
        function recencyLabel(days) {
            if (days === null || days === undefined) { return null; }
            if (days <= 0) { return 'Today'; }
            if (days === 1) { return 'Yesterday'; }
            return days + ' days ago';
        }
        const recency = recencyLabel(latestUpdate.recordRecencyDays);
        const items = [];
        if (latestUpdate.present) {
            items.push({ when: recency || '—', text: 'Latest project update recorded' });
        }
        if (frm.doc.modified) {
            items.push({ when: recency || '—', text: 'Project record updated' + (frm.doc.modified_by ? ' by ' + PSU.esc(frm.doc.modified_by) : '') });
        }
        const visible = items.slice(0, 5);
        if (visible.length === 0) {
            return '<div class="psu-card psu-card-activity">' + header +
                '<div class="psu-empty-state">' + PSU.iconHTML('notification') + '<div class="psu-empty-title">Recent activity is not available from the current dashboard data.</div></div>' +
                '</div>';
        }
        const rows = visible.map(function(it) {
            return '<div class="psu-activity-row"><span class="psu-activity-when">' + PSU.esc(it.when) + '</span><span class="psu-activity-text">' + PSU.esc(it.text) + '</span></div>';
        }).join('');
        return '<div class="psu-card psu-card-activity">' + header + '<div class="psu-activity-list">' + rows + '</div></div>';
    },

    buildStickySummary: function(frm, health, readiness) {
        const customer = frm.doc.customer ? PSU.esc(frm.doc.customer) : '—';
        const stage = PSU.resolveProjectFields(frm).stage.value ? PSU.esc(PSU.resolveProjectFields(frm).stage.value) : (frm.doc.status ? PSU.esc(frm.doc.status) : '—');
        const progress = PSU.normalizeProjectProgress(frm.doc.percent_complete);
        const progressDisplay = progress === null ? '—' : Math.round(progress) + '%';
        const healthDisp = PSU.healthDisplay(health);
        return '<div class="psu-sticky-summary" data-psu-sticky="1">' +
            '<span class="psu-sticky-item"><span class="psu-sticky-label">Customer</span><span class="psu-sticky-value">' + customer + '</span></span>' +
            '<span class="psu-sticky-item"><span class="psu-sticky-label">Stage</span><span class="psu-sticky-value">' + stage + '</span></span>' +
            '<span class="psu-sticky-item"><span class="psu-sticky-label">Completion</span><span class="psu-sticky-value">' + progressDisplay + '</span></span>' +
            '<span class="psu-sticky-item"><span class="psu-sticky-label">Health</span><span class="psu-sticky-value">' + PSU.esc(healthDisp.text) + '</span></span>' +
            '<button type="button" class="psu-refresh-btn psu-sticky-refresh" data-action="psu-refresh" aria-label="Refresh dashboard">' + PSU.iconHTML('refresh') + '</button>' +
            '</div>';
    },

    buildHeaderSection: function(frm, lastRefreshed) {
        const status = frm.doc.status ? PSU.esc(frm.doc.status) : '—';
        const statusColor = frm.doc.status === 'Completed' ? 'green' : (frm.doc.status === 'Cancelled' ? 'red' : 'blue');
        return [
            '<div class="psu-header">',
            '<div class="psu-header-left">',
            '<div class="psu-header-title-row"><span class="psu-header-title">Project Command Centre</span>' + PSU.statusChip(status, statusColor) + '</div>',
            '<div class="psu-header-subtitle">Operational overview and project readiness</div>',
            '</div>',
            '<div class="psu-header-right">',
            '<span class="psu-last-refreshed">Last refreshed: ' + PSU.esc(lastRefreshed) + '</span>',
            '<button type="button" class="psu-refresh-btn" data-action="psu-refresh" title="Refresh dashboard">' + PSU.iconHTML('refresh') + '<span>Refresh</span></button>',
            '</div>',
            '</div>'
        ].join('');
    },

    buildSummarySection: function(frm, health, readiness) {
        const customer = frm.doc.customer ? PSU.esc(frm.doc.customer) : '—';
        const pmId = PSU.resolveProjectFields(frm).projectManager.value;
        // PKG10A / DEF-05: show Employee name where resolvable, raw id as fallback.
        const pm = pmId ? ('<span data-psu-emp="' + PSU.esc(pmId) + '">' + PSU.esc(PSU.employeeDisplay(pmId) || String(pmId)) + '</span>') : 'Not Assigned';
        const dept = frm.doc.department ? PSU.esc(frm.doc.department) : '—';
        const stage = PSU.resolveProjectFields(frm).stage.value ? PSU.esc(PSU.resolveProjectFields(frm).stage.value) : (frm.doc.status ? PSU.esc(frm.doc.status) : '—');
        const statusText = frm.doc.status ? PSU.esc(frm.doc.status) : '—';
        const statusColor = frm.doc.status === 'Completed' ? 'green' : (frm.doc.status === 'Cancelled' ? 'red' : (frm.doc.status === 'On hold' ? 'amber' : 'blue'));
        const progress = PSU.normalizeProjectProgress(frm.doc.percent_complete);
        const progressDisplay = progress === null ? '—' : Math.round(progress) + '%';
        const progressColorKey = PSU.progressColor(progress);
        const healthDisp = PSU.healthDisplay(health);
        const readinessColor = PSU.progressColor(readiness.score);

        function fieldRoute(fieldname) {
            const val = frm.doc[fieldname];
            if (!val) { return null; }
            const df = frappe.meta.get_docfield('Project', fieldname);
            if (!df || df.fieldtype !== 'Link' || !df.options) { return null; }
            return { doctype: df.options, name: val };
        }

        function card(opts) {
            const route = opts.route || null;
            const scrollTarget = opts.scroll || null;
            const focusField = opts.focusField || null;
            const clickable = !!(route || scrollTarget || focusField);
            const attrs = [];
            if (route) {
                attrs.push('data-psu-route-doctype="' + PSU.esc(route.doctype) + '"');
                attrs.push('data-psu-route-name="' + PSU.esc(route.name) + '"');
            }
            if (scrollTarget) { attrs.push('data-psu-scroll-target="' + PSU.esc(scrollTarget) + '"'); }
            if (focusField) { attrs.push('data-psu-focus-field="' + PSU.esc(focusField) + '"'); }
            const secondaryHTML = opts.secondary ? '<span class="psu-summary-secondary">' + opts.secondary + '</span>' : '';
            const valueClass = 'psu-summary-value' + (opts.large ? ' psu-summary-value-lg' : '');
            if (clickable) { attrs.push('tabindex="0"'); attrs.push('role="button"'); }
            return '<div class="psu-summary-card psu-accent-' + opts.accent + (clickable ? ' is-clickable' : '') + '" ' + attrs.join(' ') + '>' +
                '<span class="psu-summary-label">' + PSU.iconHTML(opts.icon) + PSU.esc(opts.label) + '</span>' +
                '<span class="' + valueClass + '">' + opts.value + '</span>' +
                secondaryHTML +
                '</div>';
        }

        const row1 = '<div class="psu-summary-grid psu-summary-grid-primary">' +
            card({ icon: 'building', accent: 'blue', label: 'Customer', value: customer, route: fieldRoute('customer') }) +
            card({ icon: 'user', accent: 'violet', label: 'Project Manager', value: pm, focusField: 'custom_project_manager' }) +
            card({ icon: 'flag', accent: 'orange', label: 'Stage', value: stage, scroll: 'status' }) +
            '</div>';

        const row2 = '<div class="psu-summary-grid psu-summary-grid-secondary">' +
            card({ icon: 'chart', accent: progressColorKey, label: 'Progress', value: '<span class="psu-text-' + progressColorKey + '">' + progressDisplay + '</span>', large: true, scroll: 'task' }) +
            card({ icon: 'heart', accent: healthDisp.color, label: 'Project Health', value: '<span class="psu-text-' + healthDisp.color + '">' + PSU.esc(healthDisp.text) + '</span>', large: true, scroll: 'health' }) +
            card({ icon: 'check', accent: readinessColor, label: 'Overall Readiness', value: '<span class="psu-text-' + readinessColor + '">' + readiness.score + '%</span>', large: true, scroll: 'readiness' }) +
            card({ icon: 'activity', accent: statusColor, label: 'Project Status', value: PSU.statusChip(statusText, statusColor) }) +
            '</div>';

        return row1 + row2;
    },

    buildTaskDashboard: function(taskStats, truncated, expanded) {
        const rows = [
            ['Open', taskStats.openCount], ['Completed', taskStats.closedCount], ['Total', taskStats.totalCount], ['Completion', taskStats.completionPct + '%'],
            ['Overdue', taskStats.overdueCount], ['Due This Week', taskStats.dueSoonCount], ['Assigned', taskStats.assignedCount], ['Unassigned', taskStats.unassignedCount], ['High Priority', taskStats.highPriorityCount]
        ];
        const cells = rows.map(function(r) {
            const rawVal = (typeof r[1] === 'string') ? parseInt(r[1], 10) : r[1];
            const color = PSU.kpiColor(r[0], rawVal);
            return '<div class="psu-kpi"><span class="psu-kpi-value psu-text-' + color + '">' + PSU.esc(String(r[1])) + '</span><span class="psu-kpi-label">' + PSU.esc(r[0]) + '</span></div>';
        }).join('');
        const progColor = PSU.progressColor(taskStats.completionPct);
        const truncNotice = truncated ? '<div class="psu-notice psu-notice-amber">Task results limited to the first ' + PSU.TASK_PAGE_LIMIT + ' records.</div>' : '';
        const body = '<div class="psu-kpi-grid">' + cells + '</div>' +
            '<div class="psu-completion-row">' + PSU.progressBarHTML(taskStats.completionPct, progColor) + '</div>' +
            truncNotice;
        return PSU.wrapCollapsible('tasks', 'psu-card-task', 'list', 'Tasks', 'Operational task status', body, expanded);
    },

    buildTimelineSection: function(frm, timeline, scheduleVariance, expanded) {
        if (!timeline.configured) {
            const body0 = '<div class="psu-empty-state">' + PSU.iconHTML('calendar') + '<div class="psu-empty-title">Timeline not configured</div><div class="psu-empty-desc">Add expected start and end dates to enable schedule tracking.</div></div>';
            return PSU.wrapCollapsible('timeline', 'psu-card-timeline', 'calendar', 'Timeline', 'Schedule position and delivery status', body0, expanded);
        }
        if (timeline.invalid) {
            const body1 = '<div class="psu-empty-state">' + PSU.iconHTML('calendar') + '<div class="psu-empty-title">Invalid Timeline</div><div class="psu-empty-desc">End date is before the start date.</div></div>';
            return PSU.wrapCollapsible('timeline', 'psu-card-timeline', 'calendar', 'Timeline', 'Schedule position and delivery status', body1, expanded);
        }
        const start = PSU.esc(frappe.datetime.str_to_user(frm.doc.expected_start_date));
        const end = PSU.esc(frappe.datetime.str_to_user(frm.doc.expected_end_date));
        const elapsed = timeline.elapsedDuration !== null ? Math.max(0, timeline.elapsedDuration) : null;
        const remaining = timeline.daysRemaining;
        const remainingText = remaining < 0 ? Math.abs(remaining) + ' days overdue' : remaining + ' days remaining';
        const varianceText = scheduleVariance.variance === null ? scheduleVariance.label : (scheduleVariance.variance > 0 ? '+' : '') + scheduleVariance.variance.toFixed(1) + '%';
        const statusColor = timeline.status === 'Overdue' ? 'red' : (timeline.status === 'Due Today' ? 'amber' : 'blue');
        const grid = [
            ['Start Date', start], ['End Date', end],
            ['Total Duration', timeline.totalDuration === null ? '—' : timeline.totalDuration + ' d'],
            ['Elapsed Days', elapsed === null ? '—' : elapsed + ' d'], ['Remaining Days', PSU.esc(remainingText)]
        ].map(function(r) {
            return '<div class="psu-kpi psu-kpi-sm"><span class="psu-kpi-value-sm">' + r[1] + '</span><span class="psu-kpi-label">' + PSU.esc(r[0]) + '</span></div>';
        }).join('');
        const body = '<div class="psu-kpi-grid psu-kpi-grid-sm">' + grid + '</div>' +
            '<div class="psu-timeline-progress">' + PSU.progressBarHTML(timeline.timelineProgress, PSU.progressColor(timeline.timelineProgress)) + '</div>' +
            '<div class="psu-timeline-footer"><span class="psu-label-inline">Schedule Variance</span>' + PSU.statusChip(varianceText, scheduleVariance.color) + '<span class="psu-label-inline psu-ml">Status</span>' + PSU.statusChip(timeline.status, statusColor) + '</div>';
        return PSU.wrapCollapsible('timeline', 'psu-card-timeline', 'calendar', 'Timeline', 'Schedule position and delivery status', body, expanded);
    },

    buildBOQSection: function(boqInfo, expanded) {
        const colorMap = { 'Complete': 'green', 'Partially Complete': 'amber', 'Incomplete': 'red', 'Pending': 'grey', 'Validation Unavailable': 'grey' };
        const color = colorMap[boqInfo.status] || 'grey';
        const addBtn = '<div class="psu-actions-secondary-row"><button type="button" class="psu-btn psu-btn-secondary psu-qa-btn" data-action="add-boq">Add BOQ</button></div>';
        if (boqInfo.status === 'Pending' && boqInfo.rows === 0) {
            const body0 = '<div class="psu-empty-state">' + PSU.iconHTML('file') + '<div class="psu-empty-title">No BOQ entries available</div><div class="psu-empty-desc">Add bill of quantities to track cost estimation.</div></div>' + addBtn;
            return PSU.wrapCollapsible('boq', 'psu-card-boq', 'small-file', 'Bill of Quantities', 'Cost estimation completeness', body0, expanded);
        }
        const grid = [
            ['Rows', boqInfo.rows], ['Valid', boqInfo.validRows], ['Incomplete', boqInfo.incompleteRows]
        ].map(function(r) {
            return '<div class="psu-kpi psu-kpi-sm"><span class="psu-kpi-value-sm">' + r[1] + '</span><span class="psu-kpi-label">' + PSU.esc(r[0]) + '</span></div>';
        }).join('');
        const body = '<div class="psu-kpi-grid psu-kpi-grid-sm">' + grid + '</div>' +
            '<div class="psu-boq-status-row">' + PSU.statusChip(boqInfo.status, color) + '<span class="psu-subtext">' + PSU.esc(boqInfo.reason) + '</span></div>' +
            addBtn;
        return PSU.wrapCollapsible('boq', 'psu-card-boq', 'small-file', 'Bill of Quantities', 'Cost estimation completeness', body, expanded);
    },

    buildReadinessSection: function(readiness, expanded) {
        function statusText(met) {
            if (met === true) { return 'Configured'; }
            if (met === 'partial') { return 'Partially configured'; }
            return 'Not configured';
        }
        const items = readiness.components.map(function(c) {
            const icon = c.met === true ? '✓' : (c.met === 'partial' ? '½' : '✗');
            const cls = c.met === true ? 'psu-check-green' : 'psu-check-amber';
            return '<div class="psu-readiness-item ' + cls + '"><span class="psu-check-icon">' + icon + '</span><span class="psu-readiness-item-body"><span class="psu-readiness-item-label">' + PSU.esc(c.label) + '</span><span class="psu-readiness-item-status">' + statusText(c.met) + '</span></span></div>';
        }).join('');
        const color = PSU.progressColor(readiness.score);
        const body = '<div class="psu-readiness-score-row">' + PSU.progressBarHTML(readiness.score, color) + '</div>' +
            '<div class="psu-readiness-list">' + items + '</div>';
        return PSU.wrapCollapsible('readiness', 'psu-card-readiness', 'check', 'Overall Readiness', 'Project setup completeness', body, expanded);
    },

    buildHealthSection: function(health, expanded) {
        if (health.state === 'Unavailable') {
            const missingLabels = health.unavailable.map(function(k) { return PSU.HEALTH_COMPONENT_LABELS[k] || k; });
            const body0 = '<div class="psu-empty-state"><div class="psu-empty-title">Unavailable</div><div class="psu-empty-desc">Insufficient verified data (' + PSU.esc(missingLabels.join(', ')) + ').</div></div>';
            return PSU.wrapCollapsible('health', 'psu-card-health', 'heart', 'Project Health', 'Overall project condition', body0, expanded);
        }
        const d = PSU.healthDisplay(health);
        const RING_COLORS = { green: '#12b76a', amber: '#f79009', red: '#f04438', blue: '#2563eb', grey: '#98a2b3' };
        const ringColor = RING_COLORS[d.color] || '#98a2b3';
        const ringPct = Math.max(0, Math.min(100, Math.round(health.score)));
        let noteHTML = '';
        if (health.isProvisional) {
            const totalComponents = Object.keys(PSU.HEALTH_WEIGHTS).length;
            const availableComponents = totalComponents - health.unavailable.length;
            const unscoredText = health.unavailable.map(function(k) {
                const label = PSU.HEALTH_COMPONENT_LABELS[k] || k;
                const reason = (health.unavailableReasons && health.unavailableReasons[k]) ? ' (' + health.unavailableReasons[k] + ')' : '';
                return label + reason;
            }).join(', ');
            noteHTML = '<div class="psu-info-panel">Based on ' + availableComponents + ' of ' + totalComponents + ' Health Components<br>Estimated from available components only<br>Unscored: ' + PSU.esc(unscoredText) + '</div>';
        }
        const body = '<div class="psu-health-main-row">' +
            '<div class="psu-health-ring" style="--psu-ring-color:' + ringColor + '; --psu-ring-pct:' + ringPct + ';"><div class="psu-health-ring-inner"><span class="psu-health-ring-value">' + ringPct + '%</span></div></div>' +
            '<div class="psu-health-score-row">' + PSU.statusChip(d.text, d.color) + '</div>' +
            '</div>' +
            noteHTML;
        return PSU.wrapCollapsible('health', 'psu-card-health', 'heart', 'Project Health', 'Overall project condition', body, expanded);
    },

    buildLatestUpdateSection: function(latestUpdate, frm, expanded) {
        const modifiedBy = (frm && frm.doc.modified_by) ? PSU.esc(frm.doc.modified_by) : '—';
        const recencyText = latestUpdate.recordRecencyDays === null ? '—' : latestUpdate.recordRecencyDays + ' day(s) ago';
        if (!latestUpdate.present) {
            const body0 = '<div class="psu-empty-state">' + PSU.iconHTML('notification') + '<div class="psu-empty-title">No project update has been recorded.</div></div>' +
                '<div class="psu-update-meta">Record Updated: ' + PSU.esc(recencyText) + ' by ' + modifiedBy + '</div>';
            return PSU.wrapCollapsible('latest-update', 'psu-card-update', 'edit', 'Latest Project Update', 'Recent project activity', body0, expanded);
        }
        const body = '<div class="psu-update-text">' + PSU.esc(latestUpdate.text) + '</div>' +
            '<div class="psu-update-meta">Record Updated: ' + PSU.esc(recencyText) + ' by ' + modifiedBy + '</div>';
        return PSU.wrapCollapsible('latest-update', 'psu-card-update', 'edit', 'Latest Project Update', 'Recent project activity', body, expanded);
    },

    buildRisksSection: function(risks, expanded) {
        if (risks.all.length === 0) {
            const body0 = '<div class="psu-empty-state"><div class="psu-empty-title">No risks detected.</div></div>';
            return PSU.wrapCollapsible('risks', 'psu-card-risks', 'warning', 'Risks', 'Current project risks', body0, expanded);
        }
        const items = risks.top5.map(function(r) {
            const cls = r.severity === 'Critical' ? 'red' : (r.severity === 'Warning' ? 'amber' : 'blue');
            return '<div class="psu-risk-row">' + PSU.statusChip(r.severity, cls) + '<span class="psu-risk-msg">' + PSU.esc(r.message) + '</span></div>';
        }).join('');
        const moreNotice = risks.totalCount > 5 ? '<div class="psu-subtext">Showing 5 of ' + risks.totalCount + ' risks</div>' : '';
        const body = '<div class="psu-risk-list">' + items + '</div>' + moreNotice;
        return PSU.wrapCollapsible('risks', 'psu-card-risks', 'warning', 'Risks', 'Current project risks', body, expanded);
    },

    buildManagementAttentionSection: function(attentionItems) {
        const header = PSU.sectionHeader('warning', 'Management Attention', 'Exceptions and items that may need review');
        if (attentionItems.length === 0) {
            return '<div class="psu-card psu-card-attention">' + header +
                '<div class="psu-attention-ok">' + PSU.iconHTML('check') + '<span>No immediate management attention required.</span></div>' +
                '</div>';
        }
        const groups = [
            { key: 'critical', label: 'Critical', cls: 'psu-attention-critical' },
            { key: 'warning', label: 'Warnings', cls: '' },
            { key: 'info', label: 'Information', cls: 'psu-attention-info' }
        ];
        const groupsHTML = groups.map(function(g) {
            const groupItems = attentionItems.filter(function(it) { return it.group === g.key; });
            if (groupItems.length === 0) { return ''; }
            const visible = groupItems.slice(0, 6);
            const rows = visible.map(function(it) {
                return '<div class="psu-attention-item' + (g.cls ? ' ' + g.cls : '') + '">' + PSU.iconHTML('warning') + '<span class="psu-attention-msg">' + PSU.esc(it.text) + '</span></div>';
            }).join('');
            const moreNotice = groupItems.length > 6 ? '<div class="psu-subtext psu-attention-more">+' + (groupItems.length - 6) + ' more item(s) - see Risks section for full details.</div>' : '';
            return '<div class="psu-attention-group"><div class="psu-attention-group-title psu-attention-group-' + g.key + '">' + PSU.esc(g.label) + '</div><div class="psu-attention-list">' + rows + '</div>' + moreNotice + '</div>';
        }).join('');
        return '<div class="psu-card psu-card-attention">' + header + groupsHTML + '</div>';
    },

    buildQuickActions: function(expanded) {
        function qaBtn(cls, action, icon, title, help) {
            return '<button type="button" class="psu-btn ' + cls + ' psu-qa-btn" data-action="' + action + '">' + PSU.iconHTML(icon) + '<span class="psu-qa-text"><span class="psu-qa-title">' + title + '</span><span class="psu-qa-help">' + help + '</span></span></button>';
        }
        const body = '<div class="psu-actions-toolbar">' +
            qaBtn('psu-btn-primary', 'open-tasks', 'list', 'Open Tasks', 'View and manage project tasks') +
            qaBtn('psu-btn-secondary', 'update-progress', 'refresh', 'Update Progress', 'Edit the percent complete field') +
            qaBtn('psu-btn-secondary', 'add-boq', 'file', 'Add BOQ', 'Add bill of quantities entries') +
            qaBtn('psu-btn-secondary', 'latest-update', 'edit', 'Latest Update', 'Post a project status note') +
            '</div>';
        return PSU.wrapCollapsible('quick-actions', 'psu-card-actions', 'tools', 'Quick Actions', 'Common project shortcuts', body, expanded);
    },

    buildHTML: function(s) {
        return [
            '<div class="psu-dashboard">',
            s.header,
            s.sticky,
            s.banner,
            '<div class="psu-full">' + s.execMetrics + '</div>',
            '<div class="psu-summary-wrap">' + s.summary + '</div>',
            '<div class="psu-full">' + s.setup + '</div>',
            '<div class="psu-row psu-row-2col">' + s.team + s.activity + '</div>',
            '<div class="psu-full">' + s.attention + '</div>',
            '<div class="psu-row psu-row-60-40">' + s.task + s.timeline + '</div>',
            '<div class="psu-row psu-row-40-60">' + s.boq + s.health + '</div>',
            '<div class="psu-full">' + s.readiness + '</div>',
            '<div class="psu-row psu-row-2col">' + s.update + s.risks + '</div>',
            '<div class="psu-full">' + s.actions + '</div>',
            '</div>'
        ].join('');
    },

    buildDashboard: function(frm, taskData, renderId) {
        const wrapperField = 'custom_project_status_update';
        const $wrapper = frm.fields_dict[wrapperField].$wrapper;
        if (taskData.permissionError) { $wrapper.html('<div class="psu-dashboard"><div class="psu-notice psu-notice-grey">Unable to load task data due to insufficient permissions.</div></div>'); return; }
        if (taskData.loadError) { $wrapper.html('<div class="psu-dashboard"><div class="psu-notice psu-notice-red">An error occurred while loading the Project Command Centre.</div></div>'); return; }
        const taskStats = PSU.classifyTasks(taskData.tasks);
        const descInfo = PSU.calcDescription(frm);
        const boqInfo = PSU.calcBOQ(frm);
        const tf = PSU.timelineFields(frm);
        const timeline = PSU.calcTimeline(frm, tf);
        const projectProgress = PSU.normalizeProjectProgress(frm.doc.percent_complete);
        const scheduleVariance = PSU.calcScheduleVariance(timeline, projectProgress, taskStats);
        const readiness = PSU.calcReadiness(frm, descInfo, boqInfo, timeline, taskStats);
        const latestUpdate = PSU.calcLatestUpdate(frm);
        const health = PSU.calcHealth(frm, taskStats, timeline, boqInfo, descInfo, projectProgress);
        const risks = PSU.calcRisks({ taskStats: taskStats, timeline: timeline, scheduleVariance: scheduleVariance, boqInfo: boqInfo, descInfo: descInfo, latestUpdate: latestUpdate, truncated: taskData.truncated });
        const lastRefreshed = new Date().toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
        const setup = PSU.evaluateProjectSetup(frm, { descInfo: descInfo, boqInfo: boqInfo, taskStats: taskStats });
        const attentionItems = PSU.computeAttentionItems(frm, taskStats, risks, setup);
        const sectionState = PSU.getSectionState(frm);
        function isExpanded(key, def) { return sectionState.hasOwnProperty(key) ? !!sectionState[key] : def; }
        const html = PSU.buildHTML({
            header: PSU.buildHeaderSection(frm, lastRefreshed),
            sticky: PSU.buildStickySummary(frm, health, readiness),
            banner: PSU.buildExecutiveBanner(frm, taskStats, health, readiness, attentionItems, setup),
            execMetrics: PSU.buildExecutiveMetrics(taskStats, health),
            summary: PSU.buildSummarySection(frm, health, readiness),
            setup: PSU.buildSetupChecklistSection(frm, setup),
            team: PSU.buildProjectTeam(frm),
            activity: PSU.buildRecentActivity(frm, latestUpdate),
            attention: PSU.buildManagementAttentionSection(attentionItems),
            task: PSU.buildTaskDashboard(taskStats, taskData.truncated, isExpanded('tasks', true)),
            timeline: PSU.buildTimelineSection(frm, timeline, scheduleVariance, isExpanded('timeline', true)),
            boq: PSU.buildBOQSection(boqInfo, isExpanded('boq', false)),
            health: PSU.buildHealthSection(health, isExpanded('health', true)),
            readiness: PSU.buildReadinessSection(readiness, isExpanded('readiness', false)),
            update: PSU.buildLatestUpdateSection(latestUpdate, frm, isExpanded('latest-update', false)),
            risks: PSU.buildRisksSection(risks, isExpanded('risks', true)),
            actions: PSU.buildQuickActions(isExpanded('quick-actions', false))
        });
        $wrapper.html(html);
        PSU.bindActions(frm, $wrapper);
        PSU.fixWidth(frm);
        PSU.renderBOQFieldGuidance(frm, boqInfo);
    },

    // ============================================================
    // MODULE 08 -- EVENT BINDING
    // ============================================================

    bindActions: function(frm, $wrapper) {
        PSU.resolveEmployeeNames($wrapper); // PKG10A / DEF-05
        $wrapper.off('click.psu-setup-action').on('click.psu-setup-action', '.psu-setup-action', function() {
            const fieldname = $(this).data('fieldname');
            if (fieldname) { PSU.focusProjectField(frm, String(fieldname)); }
        });
        $wrapper.off('click.psu-quick-actions').on('click.psu-quick-actions', '.psu-qa-btn', function() {
            const action = $(this).data('action');
            if (action === 'open-tasks') { frappe.set_route('List', 'Task', { project: frm.doc.name }); }
            else if (action === 'update-progress') { frm.scroll_to_field('percent_complete'); }
            else if (action === 'add-boq') { frm.scroll_to_field('custom_boq'); }
            else if (action === 'latest-update') { frm.scroll_to_field('custom_latest_update'); }
        });
        $wrapper.off('click.psu-summary-nav').on('click.psu-summary-nav', '.psu-summary-card.is-clickable', function() {
            const $el = $(this);
            const doctype = $el.attr('data-psu-route-doctype');
            const name = $el.attr('data-psu-route-name');
            const scrollTarget = $el.attr('data-psu-scroll-target');
            const focusField = $el.attr('data-psu-focus-field');
            if (focusField) { PSU.focusFieldFromCard(frm, focusField); return; }
            if (doctype && name) { frappe.set_route('Form', doctype, name); return; }
            if (scrollTarget === 'status') { frm.scroll_to_field('status'); return; }
            const map = { task: '.psu-card-task', health: '.psu-card-health', readiness: '.psu-card-readiness' };
            if (map[scrollTarget]) {
                const $target = $wrapper.find(map[scrollTarget]);
                if ($target.length) { $target[0].scrollIntoView({ behavior: 'smooth', block: 'start' }); }
            }
        });
        $wrapper.off('keydown.psu-summary-nav').on('keydown.psu-summary-nav', '.psu-summary-card.is-clickable', function(e) {
            if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
                e.preventDefault();
                $(this).trigger('click');
            }
        });
        $wrapper.off('click.psu-team-nav').on('click.psu-team-nav', '.psu-team-link', function(e) {
            e.preventDefault();
            const $el = $(this);
            const doctype = $el.attr('data-psu-route-doctype');
            const name = $el.attr('data-psu-route-name');
            const focusField = $el.attr('data-psu-focus-field');
            if (focusField) { PSU.focusFieldFromCard(frm, focusField); return; }
            if (doctype && name) { frappe.set_route('Form', doctype, name); }
        });
        $wrapper.off('click.psu-collapsible').on('click.psu-collapsible', '.psu-collapsible-trigger', function() {
            const $btn = $(this);
            const key = $btn.attr('data-psu-toggle');
            const isExpandedNow = $btn.attr('aria-expanded') === 'true';
            const next = !isExpandedNow;
            $btn.attr('aria-expanded', next ? 'true' : 'false');
            $btn.find('.psu-chevron').toggleClass('psu-chevron-open', next);
            const $content = $wrapper.find('#psu-content-' + key);
            $content.css('display', next ? '' : 'none');
            PSU.saveSectionState(frm, key, next);
        });
        $wrapper.off('click.psu-refresh').on('click.psu-refresh', '.psu-refresh-btn', function() {
            PSU.render(frm);
        });
        const $stickyEl = $wrapper.find('.psu-sticky-summary');
        if ($stickyEl.length) {
            const summaryAnchorEl = $wrapper.find('.psu-summary-wrap')[0];
            if (window.__psuStickyScrollHandler) {
                document.removeEventListener('scroll', window.__psuStickyScrollHandler, true);
            }
            window.__psuStickyScrollHandler = function() {
                if (!summaryAnchorEl) { return; }
                const rect = summaryAnchorEl.getBoundingClientRect();
                $stickyEl.toggleClass('psu-sticky-visible', rect.bottom < 0);
            };
            document.addEventListener('scroll', window.__psuStickyScrollHandler, true);
        }
    },

    // ============================================================
    // MODULE 09 -- FORM LIFECYCLE
    // ============================================================

    _renderId: 0,

    render: function(frm) {
        if (!frm.doc || frm.doc.__islocal) return;
        const myRenderId = ++PSU._renderId;
        const wrapperField = 'custom_project_status_update';
        if (!frm.fields_dict[wrapperField]) return;
        PSU.injectStyles();
        frm.fields_dict[wrapperField].$wrapper.html('<div class="psu-loading">Loading Project Command Centre...</div>');
        PSU.fixWidth(frm);
        PSU.fetchTasks(frm).then(function(taskData) {
            if (myRenderId !== PSU._renderId) return;
            PSU.buildDashboard(frm, taskData, myRenderId);
        }).catch(function(err) {
            if (myRenderId !== PSU._renderId) return;
            if (PSU.isPermissionError(err)) {
                PSU.buildDashboard(frm, { tasks: [], permissionError: true }, myRenderId);
            } else {
                console.error('PSU: Unexpected error while fetching tasks', err);
                PSU.buildDashboard(frm, { tasks: [], loadError: true }, myRenderId);
            }
        });
    },

    injectStyles: function() {
        const styleTag = document.getElementById('psu-styles');
        if (styleTag) { styleTag.remove(); }
        const css = [
            '.psu-dashboard { display: flex; flex-direction: column; gap: 12px; padding: 12px; background: #f7f8fa; border-radius: 10px; font-size: 12px; color: #1f2937; }',
            '.psu-header { display: flex; align-items: flex-start; justify-content: space-between; padding: 0 2px 10px 2px; border-bottom: 1px solid #e5e7eb; margin-bottom: 2px; }',
            '.psu-header-title-row { display: flex; align-items: center; gap: 8px; }',
            '.psu-header-title { font-size: 17px; font-weight: 600; color: #111827; }',
            '.psu-header-subtitle { font-size: 12px; color: #6b7280; margin-top: 2px; }',
            '.psu-header-right { font-size: 11px; color: #9ca3af; white-space: nowrap; }',
            '.psu-summary-strip-wrap { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); padding: 12px 16px; }',
            '.psu-summary-strip { display: grid; grid-template-columns: repeat(6, 1fr); }',
            '.psu-tile { display: flex; flex-direction: column; gap: 3px; padding: 0 16px; border-left: 1px solid #eef0f2; }',
            '.psu-tile:first-child { border-left: none; padding-left: 0; }',
            '.psu-tile-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; color: #9ca3af; }',
            '.psu-tile-value { font-size: 13px; font-weight: 600; color: #111827; }',
            '.psu-muted { color: #9ca3af; font-weight: 400; font-style: italic; }',
            '.psu-row { display: grid; gap: 12px; }',
            '.psu-row-60-40 { grid-template-columns: 3fr 2fr; }',
            '.psu-row-40-60 { grid-template-columns: 2fr 3fr; }',
            '.psu-row-2col { grid-template-columns: 1fr 1fr; }',
            '.psu-full { display: block; }',
            '.psu-card { background: #ffffff; border: 1px solid #cbd3df; border-radius: 10px; box-shadow: 0 1px 2px rgba(16,24,40,0.05), 0 2px 6px rgba(16,24,40,0.04); padding: 18px 20px; display: flex; flex-direction: column; gap: 10px; }',
            '.psu-card-header { display: flex; flex-direction: column; gap: 1px; padding-bottom: 10px; margin-bottom: 12px; border-bottom: 1px solid #d3dae5; }',
            '.psu-card-title { font-size: 14px; font-weight: 700; color: #172033; display: inline-flex; align-items: center; gap: 6px; }',
            '.psu-card-subtitle { font-size: 11px; color: #9ca3af; }',
            '.psu-kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(84px, 1fr)); gap: 10px 12px; }',
            '.psu-kpi-grid-sm { grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); }',
            '.psu-kpi { display: flex; flex-direction: column; gap: 2px; min-width: 0; padding: 10px 12px; border: 1px solid #cbd3df; border-radius: 9px; background: #fafbfc; }',
            '.psu-kpi-value { font-size: 24px; font-weight: 700; line-height: 1.15; }',
            '.psu-kpi-value-sm { font-size: 16px; font-weight: 600; color: #111827; }',
            '.psu-kpi-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; color: #9ca3af; }',
            '.psu-text-blue { color: #2563eb; }',
            '.psu-text-green { color: #16a34a; }',
            '.psu-text-red { color: #dc2626; }',
            '.psu-text-amber { color: #b45309; }',
            '.psu-text-grey { color: #374151; }',
            '.psu-completion-row, .psu-timeline-progress { display: flex; align-items: center; gap: 8px; margin-top: 2px; }',
            '.psu-progress-track { flex: 1; background: #eef0f2; border-radius: 999px; height: 8px; overflow: hidden; }',
            '.psu-progress-fill { height: 100%; border-radius: 999px; }',
            '.psu-fill-green { background: #16a34a; }',
            '.psu-fill-amber { background: #d97706; }',
            '.psu-fill-red { background: #dc2626; }',
            '.psu-fill-blue { background: #2563eb; }',
            '.psu-fill-grey { background: #9ca3af; }',
            '.psu-progress-value { font-size: 11px; font-weight: 600; color: #6b7280; min-width: 32px; text-align: right; }',
            '.psu-notice { padding: 6px 10px; border-radius: 6px; font-size: 11px; }',
            '.psu-notice-green { background: #ecfdf3; color: #15803d; }',
            '.psu-notice-amber { background: #fffbeb; color: #b45309; }',
            '.psu-notice-red { background: #fef2f2; color: #b91c1c; }',
            '.psu-notice-grey { background: #f3f4f6; color: #6b7280; }',
            '.psu-empty-state { padding: 13px 14px; display: flex; flex-direction: column; align-items: flex-start; gap: 4px; border: 1px dashed #b8c1ce; border-radius: 9px; background: #fafbfc; }',
            '.psu-empty-state .icon { width: 20px; height: 20px; color: #9ca3af; margin-bottom: 2px; }',
            '.psu-empty-title { font-size: 12px; font-weight: 600; color: #6b7280; }',
            '.psu-empty-desc { font-size: 11px; color: #9ca3af; margin-top: 2px; }',
            '.psu-timeline-footer { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-top: 2px; }',
            '.psu-label-inline { font-size: 10px; text-transform: uppercase; color: #9ca3af; font-weight: 600; }',
            '.psu-ml { margin-left: 10px; }',
            '.psu-boq-status-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }',
            '.psu-subtext { font-size: 11px; color: #9ca3af; overflow-wrap: break-word; }',
            '.psu-actions-secondary-row { margin-top: 2px; }',
            '.psu-readiness-top { display: flex; align-items: center; gap: 14px; }',
            '.psu-readiness-top .psu-card-title { white-space: nowrap; }',
            '.psu-readiness-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; margin-top: 4px; }',
            '.psu-readiness-item { font-size: 12px; display: flex; align-items: flex-start; gap: 8px; color: #374151; padding: 10px 12px; border: 1px solid #cbd3df; border-radius: 9px; background: #fafbfc; }',
            '.psu-check-icon { font-weight: 700; }',
            '.psu-check-green .psu-check-icon { color: #16a34a; }',
            '.psu-check-amber .psu-check-icon { color: #d97706; }',
            '.psu-check-red .psu-check-icon { color: #dc2626; }',
            '.psu-health-score-row { display: flex; align-items: center; }',
            '.psu-info-panel { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; border-radius: 8px; padding: 8px 10px; font-size: 11px; line-height: 1.6; }',
            '.psu-update-text { font-size: 12px; color: #1f2937; line-height: 1.5; max-height: 110px; overflow-y: auto; overflow-wrap: break-word; }',
            '.psu-update-meta { font-size: 11px; color: #9ca3af; }',
            '.psu-risk-list { display: flex; flex-direction: column; }',
            '.psu-risk-row { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f3f4f6; font-size: 12px; }',
            '.psu-risk-row:last-child { border-bottom: none; }',
            '.psu-risk-msg { color: #374151; flex: 1; min-width: 0; overflow-wrap: break-word; }',
            '.psu-actions-toolbar { display: flex; gap: 10px; flex-wrap: wrap; }',
            '.psu-btn { font-size: 12px; font-weight: 500; padding: 8px 14px; border-radius: 8px; cursor: pointer; min-height: 36px; display: inline-flex; align-items: center; gap: 8px; border: 1px solid #c4ccd8; transition: background-color 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease; }',
            '.psu-btn .icon { width: 14px; height: 14px; }',
            '.psu-btn-primary { background: #2563eb; border: 1px solid #2563eb; color: #ffffff; }',
            '.psu-btn-primary:hover { background: #1d4ed8; }',
            '.psu-btn-secondary { background: #ffffff; border: 1px solid #d1d5db; color: #374151; }',
            '.psu-btn-secondary:hover { background: #f9fafb; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }',
            '.psu-chip { display: inline-flex; align-items: center; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 600; white-space: nowrap; }',
            '.psu-chip-green { background: #ecfdf3; color: #067647; border: 1px solid #abefc6; }',
            '.psu-chip-amber { background: #fffaeb; color: #b54708; border: 1px solid #fedf89; }',
            '.psu-chip-red { background: #fef3f2; color: #b42318; border: 1px solid #fecdca; }',
            '.psu-chip-blue { background: #eff8ff; color: #175cd3; border: 1px solid #b2ddff; }',
            '.psu-chip-grey { background: #f2f4f7; color: #475467; border: 1px solid #d0d5dd; }',
            '.psu-loading { padding: 14px; color: #9ca3af; font-size: 12px; }',
            '@media (max-width: 1100px) { .psu-summary-strip { grid-template-columns: repeat(3, 1fr); row-gap: 10px; } .psu-tile:nth-child(4) { border-left: none; padding-left: 0; } .psu-summary-grid { grid-template-columns: repeat(2, minmax(0,1fr)); } }',
            '@media (max-width: 900px) { .psu-row-60-40, .psu-row-40-60, .psu-row-2col { grid-template-columns: 1fr; } }',
            '@media (max-width: 640px) { .psu-summary-strip { grid-template-columns: repeat(2, 1fr); } .psu-tile:nth-child(odd) { border-left: none; padding-left: 0; } .psu-header { flex-direction: column; gap: 6px; } .psu-actions-toolbar { flex-direction: column; } .psu-btn { width: 100%; justify-content: center; } .psu-summary-grid { grid-template-columns: 1fr; } .psu-header-right { flex-direction: column; align-items: flex-start; gap: 6px; width: 100%; } .psu-refresh-btn { width: 100%; justify-content: center; } }',
            '.psu-summary-wrap { display: flex; flex-direction: column; gap: 12px; }',
            '.psu-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }',
            '.psu-summary-grid-primary { grid-template-columns: repeat(3, minmax(0, 1fr)); }',
            '.psu-summary-card { position: relative; min-width: 0; background: #ffffff; border-top: 1px solid #cbd3df; border-right: 1px solid #cbd3df; border-bottom: 1px solid #cbd3df; border-left: 4px solid #98a2b3; border-radius: 10px; box-shadow: 0 1px 2px rgba(16,24,40,0.05), 0 2px 6px rgba(16,24,40,0.04); padding: 14px 16px; display: flex; flex-direction: column; gap: 4px; }',
            '.psu-summary-card.is-clickable { cursor: pointer; transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease; }',
            '.psu-summary-card.is-clickable:hover { transform: translateY(-1px); border-color: #98a6bb; box-shadow: 0 2px 4px rgba(16,24,40,0.07), 0 5px 12px rgba(16,24,40,0.06); }',
            '.psu-summary-label { display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #667085; }',
            '.psu-summary-label .icon { width: 12px; height: 12px; color: #98a2b3; }',
            '.psu-summary-value { font-size: 17px; font-weight: 700; line-height: 1.35; color: #172033; overflow-wrap: break-word; }',
            '.psu-summary-value-lg { font-size: 22px; font-weight: 700; }',
            '.psu-summary-secondary { font-size: 11px; color: #98a2b3; margin-top: 1px; }',
            '.psu-accent-blue { border-left-color: #2563eb; }',
            '.psu-accent-violet { border-left-color: #7c3aed; }',
            '.psu-accent-teal { border-left-color: #0d9488; }',
            '.psu-accent-orange { border-left-color: #ea580c; }',
            '.psu-accent-green { border-left-color: #12b76a; }',
            '.psu-accent-red { border-left-color: #f04438; }',
            '.psu-accent-amber { border-left-color: #f79009; }',
            '.psu-accent-grey { border-left-color: #98a2b3; }',
            '.psu-card-title .icon { width: 15px; height: 15px; color: #667085; }',
            '.psu-attention-list { display: flex; flex-direction: column; gap: 8px; }',
            '.psu-attention-item { display: flex; align-items: flex-start; gap: 10px; padding: 11px 13px; border: 1px solid #e4c76b; border-radius: 8px; background: #fffcf0; font-size: 12px; color: #5c4a03; }',
            '.psu-attention-item .icon { width: 14px; height: 14px; color: #b54708; flex: none; margin-top: 1px; }',
            '.psu-attention-item.psu-attention-critical { border-color: #fecdca; background: #fef3f2; color: #7a271a; }',
            '.psu-attention-item.psu-attention-critical .icon { color: #b42318; }',
            '.psu-attention-msg { flex: 1; min-width: 0; overflow-wrap: break-word; }',
            '.psu-attention-ok { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border: 1px solid #abefc6; border-radius: 8px; background: #ecfdf3; color: #067647; font-size: 12px; }',
            '.psu-attention-ok .icon { width: 14px; height: 14px; color: #067647; }',
            '.psu-attention-more { margin-top: 2px; }',
            '.psu-readiness-score-row { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }',
            '.psu-readiness-item-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }',
            '.psu-readiness-item-label { font-weight: 600; color: #172033; }',
            '.psu-readiness-item-status { font-size: 11px; color: #667085; }',
            '.psu-readiness-item.psu-check-green { border-color: #abefc6; background: #ecfdf3; }',
            '.psu-readiness-item.psu-check-amber { border-color: #fedf89; background: #fffaeb; }',
            '.psu-health-main-row { display: flex; align-items: center; gap: 14px; }',
            '.psu-health-ring { width: 60px; height: 60px; border-radius: 50%; background: conic-gradient(var(--psu-ring-color) calc(var(--psu-ring-pct) * 1%), #eef0f2 0); display: flex; align-items: center; justify-content: center; flex: none; }',
            '.psu-health-ring-inner { width: 44px; height: 44px; border-radius: 50%; background: #ffffff; display: flex; align-items: center; justify-content: center; }',
            '.psu-health-ring-value { font-size: 12px; font-weight: 700; color: #172033; }',
            '.psu-header-right { display: flex; align-items: center; gap: 10px; }',
            '.psu-last-refreshed { font-size: 11px; color: #9ca3af; white-space: nowrap; }',
            '.psu-refresh-btn { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; color: #374151; background: #ffffff; border: 1px solid #c4ccd8; border-radius: 6px; padding: 4px 9px; cursor: pointer; }',
            '.psu-refresh-btn:hover { background: #f9fafb; }',
            '.psu-refresh-btn .icon { width: 12px; height: 12px; }',
            '.psu-qa-text { display: flex; flex-direction: column; align-items: flex-start; gap: 1px; }',
            '.psu-qa-title { font-size: 12px; font-weight: 600; }',
            '.psu-qa-help { font-size: 10px; font-weight: 400; opacity: 0.8; }',
            '.psu-executive-banner { display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; padding:14px 18px; border:1px solid #cbd3df; border-radius:10px; background:#ffffff; box-shadow:0 1px 2px rgba(16,24,40,0.05), 0 2px 6px rgba(16,24,40,0.04); }',
            '.psu-banner-eyebrow { font-size:11px; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:#667085; }',
            '.psu-banner-title { font-size:18px; font-weight:750; color:#172033; margin-top:2px; }',
            '.psu-banner-subtitle { font-size:12px; color:#667085; margin-top:2px; }',
            '.psu-banner-metrics { display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:12px; }',
            '.psu-banner-metric { display:flex; flex-direction:column; gap:2px; min-width:64px; }',
            '.psu-banner-metric-value { font-size:18px; font-weight:750; color:#172033; }',
            '.psu-banner-metric-label { font-size:10px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; color:#667085; }',
            '.psu-banner-ontrack { border-left:4px solid #12b76a; }',
            '.psu-banner-warning { border-left:4px solid #f79009; }',
            '.psu-banner-critical { border-left:4px solid #f04438; }',
            '.psu-banner-grey { border-left:4px solid #98a2b3; }',
            '.psu-executive-metrics { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; }',
            '.psu-executive-metric { padding:16px; border:1px solid #cbd3df; border-radius:10px; background:#ffffff; box-shadow:0 1px 2px rgba(16,24,40,0.05), 0 2px 6px rgba(16,24,40,0.04); display:flex; flex-direction:column; gap:4px; min-width:0; }',
            '.psu-executive-metric-value { font-size:28px; font-weight:760; line-height:1; }',
            '.psu-executive-metric-label { font-size:11px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; color:#667085; margin-top:4px; }',
            '.psu-collapsible-trigger { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; width:100%; padding:0 0 10px 0; margin-bottom:12px; border:none; border-bottom:1px solid #d3dae5; background:transparent; cursor:pointer; text-align:left; font:inherit; color:inherit; }',
            '.psu-collapsible-trigger:hover { opacity:0.9; }',
            '.psu-chevron { display:inline-flex; align-items:center; justify-content:center; transition:transform 160ms ease; flex:none; margin-top:2px; }',
            '.psu-chevron-open { transform:rotate(180deg); }',
            '.psu-attention-group { display:flex; flex-direction:column; gap:6px; margin-bottom:10px; }',
            '.psu-attention-group:last-child { margin-bottom:0; }',
            '.psu-attention-group-title { font-size:11px; font-weight:700; letter-spacing:0.05em; text-transform:uppercase; }',
            '.psu-attention-group-critical { color:#b42318; }',
            '.psu-attention-group-warning { color:#b54708; }',
            '.psu-attention-group-info { color:#175cd3; }',
            '.psu-attention-item.psu-attention-info { border-color:#b2ddff; background:#eff8ff; color:#173a63; }',
            '.psu-team-list { display:flex; flex-direction:column; gap:8px; }',
            '.psu-team-row { display:flex; align-items:center; gap:10px; padding:8px 10px; border:1px solid #e4e7ec; border-radius:8px; background:#fafbfc; }',
            '.psu-team-role { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.04em; color:#667085; min-width:120px; }',
            '.psu-team-value { font-size:13px; font-weight:600; color:#172033; overflow-wrap:break-word; min-width:0; }',
            '.psu-team-link { color:#2563eb; text-decoration:none; }',
            '.psu-team-link:hover { text-decoration:underline; }',
            '.psu-activity-list { display:flex; flex-direction:column; gap:8px; }',
            '.psu-activity-row { display:flex; gap:10px; padding:8px 10px; border-radius:8px; background:#fafbfc; }',
            '.psu-activity-row:nth-child(odd) { background:#f2f4f7; }',
            '.psu-activity-when { font-size:11px; font-weight:700; color:#667085; min-width:80px; flex:none; }',
            '.psu-activity-text { font-size:12px; color:#172033; overflow-wrap:break-word; min-width:0; }',
            '.psu-sticky-summary { display:none; position:sticky; top:8px; z-index:20; align-items:center; gap:16px; padding:8px 14px; border:1px solid #cbd3df; border-radius:9px; background:#ffffff; box-shadow:0 2px 6px rgba(16,24,40,0.08); font-size:12px; }',
            '.psu-sticky-summary.psu-sticky-visible { display:flex; }',
            '.psu-sticky-item { display:flex; align-items:center; gap:6px; }',
            '.psu-sticky-label { font-weight:700; color:#667085; text-transform:uppercase; font-size:10px; letter-spacing:0.04em; }',
            '.psu-sticky-value { font-weight:700; color:#172033; }',
            '.psu-sticky-refresh { margin-left:auto; padding:4px 8px; }',
            '.psu-dashboard button:focus-visible, .psu-dashboard [role=\'button\']:focus-visible { outline:3px solid rgba(47,111,237,0.30); outline-offset:2px; }',
            '.psu-setup-banner { display:flex; flex-direction:column; gap:4px; padding:12px 14px; border-radius:8px; margin:0 0 12px 0; border-left:4px solid #98a2b3; background:#f7f8fa; }',
            '.psu-setup-banner-label { font-size:14px; font-weight:700; color:#1f2937; }',
            '.psu-setup-banner-message { font-size:12px; color:#4b5563; }',
            '.psu-setup-banner-ready { border-left-color:#12b76a; background:#ecfdf3; }',
            '.psu-setup-banner-review { border-left-color:#f79009; background:#fffaeb; }',
            '.psu-setup-banner-incomplete { border-left-color:#f04438; background:#fef3f2; }',
            '.psu-kickoff-banner { display:flex; flex-direction:column; gap:4px; padding:10px 14px; border-radius:8px; margin:0 0 12px 0; border-left:4px solid #98a2b3; background:#f7f8fa; }',
            '.psu-kickoff-line { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }',
            '.psu-kickoff-title { font-size:12px; font-weight:700; color:#1f2937; text-transform:uppercase; letter-spacing:0.02em; }',
            '.psu-kickoff-badge { font-size:12px; font-weight:700; padding:2px 10px; border-radius:999px; background:#eef0f2; color:#1f2937; }',
            '.psu-kickoff-message { font-size:12px; color:#4b5563; }',
            '.psu-kickoff-ready { border-left-color:#12b76a; background:#ecfdf3; }',
            '.psu-kickoff-ready .psu-kickoff-badge { background:#d1fadf; color:#027a48; }',
            '.psu-kickoff-corrections { border-left-color:#f79009; background:#fffaeb; }',
            '.psu-kickoff-corrections .psu-kickoff-badge { background:#fef0c7; color:#b54708; }',
            '.psu-kickoff-not-ready { border-left-color:#f04438; background:#fef3f2; }',
            '.psu-kickoff-not-ready .psu-kickoff-badge { background:#fee4e2; color:#b42318; }',
            '@media (max-width:600px) { .psu-kickoff-line { flex-direction:column; align-items:flex-start; } }',
            '.psu-setup-checklist { display:flex; flex-direction:column; border:1px solid #e5e7eb; border-radius:8px; overflow:hidden; }',
            '.psu-setup-row { display:grid; grid-template-columns:180px 130px 1fr 160px; gap:10px; padding:10px 12px; border-bottom:1px solid #eef0f3; align-items:center; }',
            '.psu-setup-row:last-child { border-bottom:none; }',
            '.psu-setup-row-head { background:#f7f8fa; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.03em; color:#667085; }',
            '.psu-setup-cell { font-size:12px; color:#1f2937; overflow-wrap:break-word; min-width:0; }',
            '.psu-setup-cell-label { font-weight:600; }',
            '.psu-setup-cell-explain { color:#4b5563; }',
            '.psu-setup-pill { display:inline-block; padding:3px 10px; border-radius:999px; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.02em; }',
            '.psu-setup-complete { background:#ecfdf3; color:#12b76a; }',
            '.psu-setup-partial { background:#fffaeb; color:#b54708; }',
            '.psu-setup-missing { background:#fef3f2; color:#f04438; }',
            '.psu-setup-na { background:#f2f4f7; color:#667085; }',
            '.psu-boq-guidance { margin-top:8px; padding:8px 10px; border:1px dashed #d0d5dd; border-radius:6px; background:#f9fafb; font-size:11px; color:#4b5563; }',
            '.psu-boq-template-wrap { margin-top:8px; }',
            '@media (max-width: 900px) { .psu-setup-row { grid-template-columns:1fr; gap:4px; padding:12px; } .psu-setup-row-head { display:none; } }',
            '.psu-summary-card, .psu-attention-item, .psu-collapsible-trigger, .psu-refresh-btn, .psu-qa-btn, .psu-progress-fill { transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease, width 300ms ease; }',
            '@media (prefers-reduced-motion: reduce) { .psu-dashboard * { scroll-behavior:auto !important; transition:none !important; animation:none !important; } }',
            '@media (max-width: 1100px) { .psu-executive-metrics { grid-template-columns:repeat(2, minmax(0,1fr)); } .psu-banner-metrics { grid-template-columns:repeat(2, minmax(0,1fr)); } }',
            '@media (max-width: 640px) { .psu-executive-metrics, .psu-banner-metrics { grid-template-columns:1fr; } .psu-executive-banner { flex-direction:column; align-items:flex-start; } .psu-sticky-summary { position:static; flex-wrap:wrap; } .psu-team-role { min-width:0; } }',
        ].join('');
        $('<style>').attr('id', 'psu-styles').html(css).appendTo('head');
    }

};

// ============================================================
// MODULE 10 -- INTERNAL TEST HARNESS (development use only)
// Activate manually via PSU.tests.runAll() in the browser console.
// Uses mock objects only. Never reads or writes real ERPNext records.
// ============================================================

PSU.tests = {
    _results: null,

    mockKickoffSetup: function(overrides) {
        const base = {
            customer: 'complete', project_manager: 'complete', description: 'complete',
            boq: 'complete', expected_start_date: 'complete', expected_end_date: 'complete',
            has_tasks: 'complete'
        };
        const merged = Object.assign({}, base, overrides || {});
        const criticalKeys = ['customer', 'project_manager', 'description', 'boq', 'expected_start_date', 'expected_end_date', 'has_tasks'];
        const items = criticalKeys.map(function(key) {
            return { key: key, label: key, critical: true, state: merged[key], stateLabel: merged[key] };
        });
        return { items: items };
    },

    runMeaningfulTextTests: function(failures) {
        let passed = 0, total = 0;
        const cases = [
            { input: '', expected: false },
            { input: '   ', expected: false },
            { input: '<p><br></p>', expected: false },
            { input: '&nbsp;', expected: false },
            { input: '<p>Camera installation scope</p>', expected: true }
        ];
        cases.forEach(function(c) {
            total++;
            const actual = PSU.hasMeaningfulText(c.input);
            if (actual === c.expected) { passed++; }
            else { failures.push('Meaningful text -- input ' + JSON.stringify(c.input) + ' expected ' + c.expected + ', received ' + actual); }
        });
        return { passed: passed, total: total };
    },

    runBOQStateTests: function(failures) {
        let passed = 0, total = 0;

        total++;
        const structuredHTML = '<table><thead><tr><th>Item</th><th>Description</th><th>Quantity</th><th>Remarks</th></tr></thead><tbody><tr><td>Camera</td><td>Dome camera</td><td>10</td><td></td></tr></tbody></table>';
        const structuredResult = PSU.calcBOQ({ doc: { custom_boq: structuredHTML } });
        if (structuredResult.configured === true && structuredResult.structured === true) { passed++; }
        else { failures.push('BOQ state -- structured configured expected configured&&structured true, received ' + JSON.stringify(structuredResult)); }

        total++;
        const unstructuredResult = PSU.calcBOQ({ doc: { custom_boq: '<p>Camera x10, cable 50m</p>' } });
        if (unstructuredResult.status === 'Configured (Unstructured)' && unstructuredResult.configured === true && unstructuredResult.structured === false) { passed++; }
        else { failures.push('BOQ state -- unstructured meaningful expected Configured (Unstructured), received ' + JSON.stringify(unstructuredResult)); }

        total++;
        const emptyResult = PSU.calcBOQ({ doc: { custom_boq: '' } });
        if (emptyResult.configured === false && emptyResult.structured === false) { passed++; }
        else { failures.push('BOQ state -- empty expected configured&&structured false, received ' + JSON.stringify(emptyResult)); }

        return { passed: passed, total: total };
    },

    runKickoffTests: function(failures) {
        let passed = 0, total = 0;
        const cases = [
            { label: 'Fully configured', overrides: {}, expected: 'ready' },
            { label: 'Unstructured BOQ only', overrides: { boq: 'partial' }, expected: 'corrections' },
            { label: 'Project Manager missing', overrides: { project_manager: 'missing' }, expected: 'not_ready' },
            { label: 'Dates missing', overrides: { expected_start_date: 'missing' }, expected: 'not_ready' },
            { label: 'No tasks', overrides: { has_tasks: 'missing' }, expected: 'not_ready' }
        ];
        cases.forEach(function(c) {
            total++;
            const setup = PSU.tests.mockKickoffSetup(c.overrides);
            const result = PSU.evaluateKickoffReadiness(setup);
            if (result.state === c.expected) { passed++; }
            else { failures.push('Kick-off readiness -- ' + c.label + ' expected "' + c.expected + '", received "' + result.state + '"'); }
        });
        return { passed: passed, total: total };
    },

    runStageClassificationTests: function(failures) {
        let passed = 0, total = 0;
        const cases = [
            { input: 'Planning', expected: 'planning' },
            { input: 'Material', expected: 'pre_execution' },
            { input: 'Installation', expected: 'execution' },
            { input: 'Testing', expected: 'execution' },
            { input: 'Handover', expected: 'post_execution' },
            { input: 'SomeUnknownStage', expected: undefined }
        ];
        cases.forEach(function(c) {
            total++;
            const actual = PSU.STAGE_CLASSIFICATION[c.input];
            if (actual === c.expected) { passed++; }
            else { failures.push('Stage classification -- ' + c.input + ' expected ' + c.expected + ', received ' + actual); }
        });
        return { passed: passed, total: total };
    },

    runBOQTemplateGuardTests: function(failures) {
        let passed = 0, total = 0;
        const cases = [
            { label: 'draft and editable', frm: { doc: { docstatus: 0, custom_boq: '' }, perm: [{ write: 1 }] }, field: { df: {}, disabled: false }, expected: true },
            { label: 'submitted document', frm: { doc: { docstatus: 1, custom_boq: '' }, perm: [{ write: 1 }] }, field: { df: {}, disabled: false }, expected: false },
            { label: 'existing BOQ', frm: { doc: { docstatus: 0, custom_boq: '<p>Existing scope</p>' }, perm: [{ write: 1 }] }, field: { df: {}, disabled: false }, expected: false },
            { label: 'read-only field', frm: { doc: { docstatus: 0, custom_boq: '' }, perm: [{ write: 1 }] }, field: { df: { read_only: 1 }, disabled: false }, expected: false },
            { label: 'no write permission', frm: { doc: { docstatus: 0, custom_boq: '' }, perm: [{ write: 0 }] }, field: { df: {}, disabled: false }, expected: false }
        ];
        cases.forEach(function(c) {
            total++;
            const actual = PSU.canShowBOQTemplateButton(c.frm, c.field);
            if (actual === c.expected) { passed++; }
            else { failures.push('BOQ template guard -- ' + c.label + ' expected ' + c.expected + ', received ' + actual); }
        });
        return { passed: passed, total: total };
    },

    runAll: function() {
        const failures = [];
        const results = [
            PSU.tests.runMeaningfulTextTests(failures),
            PSU.tests.runBOQStateTests(failures),
            PSU.tests.runKickoffTests(failures),
            PSU.tests.runStageClassificationTests(failures),
            PSU.tests.runBOQTemplateGuardTests(failures)
        ];
        const passed = results.reduce(function(sum, r) { return sum + r.passed; }, 0);
        const total = results.reduce(function(sum, r) { return sum + r.total; }, 0);
        const failed = total - passed;
        const summary = { passed: passed, failed: failed, total: total, failures: failures };
        PSU.tests._results = summary;
        console.log('PSU Tests: ' + passed + ' passed, ' + failed + ' failed');
        if (failed > 0) {
            failures.forEach(function(f) { console.log(f); });
        }
        return summary;
    }
};

// ============================================================
// NAMESPACE COMPATIBILITY ALIASES
// Additive only. Every existing PSU.functionName(...) call site
// continues to work unchanged. These groupings provide the
// PSU.utils / PSU.data / PSU.calc / PSU.governance / PSU.ui /
// PSU.events namespaces requested for V4.0 without moving or
// retyping any protected function body.
// ============================================================

PSU.utils = {
    fixWidth: PSU.fixWidth,
    isPermissionError: PSU.isPermissionError,
    esc: PSU.esc,
    stripHTML: PSU.stripHTML,
    clampNum: PSU.clampNum,
    daysSince: PSU.daysSince,
    normalizeProjectProgress: PSU.normalizeProjectProgress,
    progressColor: PSU.progressColor,
    hasMeaningfulText: PSU.hasMeaningfulText,
    resolveProjectFields: PSU.resolveProjectFields,
    focusProjectField: PSU.focusProjectField
};

PSU.data = {
    fetchTasks: PSU.fetchTasks,
    classifyTasks: PSU.classifyTasks,
    parseAssign: PSU.parseAssign
};

PSU.calc = {
    description: PSU.calcDescription,
    boq: PSU.calcBOQ,
    timeline: PSU.calcTimeline,
    scheduleVariance: PSU.calcScheduleVariance,
    readiness: PSU.calcReadiness,
    health: PSU.calcHealth,
    latestUpdate: PSU.calcLatestUpdate,
    risks: PSU.calcRisks
};

PSU.governance = {
    evaluateProjectSetup: PSU.evaluateProjectSetup,
    setupStateClass: PSU.setupStateClass,
    buildSetupChecklistSection: PSU.buildSetupChecklistSection,
    boqTemplateHTML: PSU.boqTemplateHTML,
    renderBOQFieldGuidance: PSU.renderBOQFieldGuidance,
    canShowBOQTemplateButton: PSU.canShowBOQTemplateButton,
    evaluateKickoffReadiness: PSU.evaluateKickoffReadiness
};

PSU.ui = {
    statusChip: PSU.statusChip,
    kpiColor: PSU.kpiColor,
    iconHTML: PSU.iconHTML,
    healthDisplay: PSU.healthDisplay,
    healthBadgeHTML: PSU.healthBadgeHTML,
    collapsibleHeaderInner: PSU.collapsibleHeaderInner,
    wrapCollapsible: PSU.wrapCollapsible,
    getSectionState: PSU.getSectionState,
    saveSectionState: PSU.saveSectionState,
    sectionHeader: PSU.sectionHeader
};

PSU.events = {
    bindActions: PSU.bindActions
};

// ============================================================
// MODULE 10B -- SECURE DEVELOPER TOOLS EXPOSURE (V4.0 Hardening)
// Exposes PSU.tests.runAll only, only when PSU.DEBUG === true and
// the current user has the System Manager role. Never exposes the
// full PSU object, form objects, mutation helpers or task-fetch
// functions. Removes the global entry point when DEBUG is false.
// Call only after PSU.tests has been defined (it has been, above).
// ============================================================

PSU.exposeDeveloperTools = function () {
    const isSystemManager =
        frappe.user &&
        typeof frappe.user.has_role === "function" &&
        frappe.user.has_role("System Manager");

    if (PSU.DEBUG === true && isSystemManager && PSU.tests) {
        window.PSUProjectCommandCentreTests = Object.freeze({
            runAll: PSU.tests.runAll
        });
    } else if (window.PSUProjectCommandCentreTests) {
        delete window.PSUProjectCommandCentreTests;
    }
};