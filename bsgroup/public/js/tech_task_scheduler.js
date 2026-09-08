frappe.ui.form.on("Tech Task Scheduler", {
    refresh: function (frm) {
        frm.remove_custom_button("Generate Scheduler Execution");

        var rows = frm.doc.tech_task_scheduler_list || [];
        var has_rows = rows.length > 0;

        if (
            !frm.is_new() &&
            frm.doc.docstatus === 1 &&
            has_rows &&
            frappe.model.can_create("Scheduler Execution")
        ) {
            frm.add_custom_button("Generate Scheduler Execution", function () {
                show_scheduler_row_selector(frm);
            });
        }
    }
});

function show_scheduler_row_selector(frm) {
    var rows = frm.doc.tech_task_scheduler_list || [];

    if (!rows || rows.length === 0) {
        frappe.msgprint(__("No scheduler rows are available."));
        return;
    }

    // A scheduler row may only ever have one Scheduler Execution. That rule is enforced by
    // the unique index on Scheduler Execution.scheduler_row and re-checked server side.
    // Look up what already exists so already-generated rows render as non-selectable
    // instead of letting the user pick one and hit a server error on Generate.
    frappe.call({
        method: "frappe.client.get_list",
        args: {
            doctype: "Scheduler Execution",
            filters: { scheduler: frm.doc.name },
            fields: ["name", "scheduler_row"],
            limit_page_length: 0
        },
        freeze: true,
        freeze_message: __("Checking existing executions..."),
        callback: function (res) {
            var generated = {};
            (res && res.message ? res.message : []).forEach(function (e) {
                if (e.scheduler_row) {
                    generated[e.scheduler_row] = e.name;
                }
            });
            render_scheduler_row_selector(frm, rows, generated);
        }
    });
}

function render_scheduler_row_selector(frm, rows, generated) {
    var selected_index = null;

    function build_cards_html() {
        var html = "";
        rows.forEach(function (row, idx) {
            var date_val = frappe.utils.escape_html(frappe.datetime.str_to_user(row.date) || "");
            var resource_val = frappe.utils.escape_html(row.resource || "");
            var category_val = frappe.utils.escape_html(row.category || "");
            var category_name_val = frappe.utils.escape_html(row.category_name || "");
            var full_activity = frappe.utils.escape_html(row.activity_details || "");
            var short_activity = full_activity.length > 160 ? (full_activity.slice(0, 160) + "...") : full_activity;

            var existing_execution = generated ? generated[row.name] : null;

            if (existing_execution) {
                html +=
                    '<div class="scheduler-row-card is-generated" data-row-index="' + idx + '" title="' + full_activity + '" ' +
                    'style="padding:10px 12px;border:1px dashed var(--border-color);border-radius:6px;margin-bottom:8px;cursor:not-allowed;opacity:0.6;">' +
                    '<div><b>' + date_val + '</b> &mdash; ' + resource_val + '</div>' +
                    '<div class="text-muted">' + category_val + (category_name_val ? (" &middot; " + category_name_val) : "") + '</div>' +
                    '<div class="text-muted" style="margin-top:2px;">' + short_activity + '</div>' +
                    '<div class=\"text-muted\" style=\"margin-top:4px;\"><b>' + __("Already generated:") + '</b> ' + frappe.utils.escape_html(existing_execution) + '</div>' +
                    '</div>';
                return;
            }

            html +=
                '<div class="scheduler-row-card" data-row-index="' + idx + '" title="' + full_activity + '" ' +
                'style="padding:10px 12px;border:1px solid var(--border-color);border-radius:6px;margin-bottom:8px;cursor:pointer;">' +
                '<div><b>' + date_val + '</b> &mdash; ' + resource_val + '</div>' +
                '<div class="text-muted">' + category_val + (category_name_val ? (" &middot; " + category_name_val) : "") + '</div>' +
                '<div class="text-muted" style="margin-top:2px;">' + short_activity + '</div>' +
                '</div>';
        });
        return html;
    }

    var dialog = new frappe.ui.Dialog({
        title: __("Select Row to Generate Execution"),
        fields: [
            {
                fieldname: "row_selector_html",
                fieldtype: "HTML"
            }
        ],
        primary_action_label: __("Generate"),
        primary_action: function () {
            if (selected_index === null || selected_index === undefined) {
                frappe.msgprint(__("Please select one scheduler row."));
                return;
            }

            var chosen_row = rows[selected_index];

            dialog.disable_primary_action();

            frappe.call({
                method: "bsgroup.bs_group.doctype.tech_task_scheduler.tech_task_scheduler.generate_scheduler_execution",
                args: {
                    scheduler: frm.doc.name,
                    scheduler_row: chosen_row.name
                },
                freeze: true,
                freeze_message: __("Generating Scheduler Execution..."),
                callback: function (r) {
                    if (r && r.message && r.message.execution_name) {
                        dialog.hide();
                        frappe.show_alert({
                            message: r.message.message,
                            indicator: "green"
                        });
                        frappe.set_route("Form", "Scheduler Execution", r.message.execution_name);
                    } else {
                        dialog.enable_primary_action();
                    }
                },
                error: function () {
                    dialog.enable_primary_action();
                }
            });
        }
    });

    dialog.fields_dict.row_selector_html.$wrapper.html(build_cards_html());

    dialog.fields_dict.row_selector_html.$wrapper.on("click", ".scheduler-row-card:not(.is-generated)", function () {
        dialog.fields_dict.row_selector_html.$wrapper
            .find(".scheduler-row-card:not(.is-generated)")
            .css({ "border-color": "var(--border-color)", "background-color": "transparent" });

        $(this).css({ "border-color": "var(--primary-color)", "background-color": "var(--control-bg)" });

        selected_index = parseInt($(this).attr("data-row-index"), 10);
    });

    dialog.show();
}

frappe.ui.form.on('Tech Task Scheduler', {
    refresh(frm) {
        render_tts_dashboard(frm);
    },
    after_save(frm) {
        render_tts_dashboard(frm);
    }
});

function render_tts_dashboard(frm) {
    // Remove existing panel if already rendered
    $('#tts-dashboard-panel').remove();

    const rows = frm.doc.tech_task_scheduler_list || [];
    if (!rows.length) return;

    // --- Compute KPIs ---
    const total = rows.length;
    const prjCount = rows.filter(r => r.category === 'Project').length;
    const tckCount = rows.filter(r => r.category === 'HD Ticket').length;
    const scheduled = rows.filter(r => r.status === 'Scheduled').length;
    const completed = rows.filter(r => r.status === 'Completed').length;

    // Resource task count
    const resMap = {};
    rows.forEach(r => {
        if (r.resource) {
            const name = r.resource.split('@')[0];
            resMap[name] = (resMap[name] || 0) + 1;
        }
    });
    const resourceCount = Object.keys(resMap).length;
    const overCap = Object.values(resMap).filter(v => v > 1).length;
    const maxTasks = Math.max(...Object.values(resMap), 1);

    // Format date DD/MM
    function fmtDate(d) {
        if (!d) return '—';
        const p = d.split('-');
        return p.length === 3 ? p[2] + '/' + p[1] : d;
    }
    const dateVal = rows[0] && rows[0].date ? fmtDate(rows[0].date) : '—';

    // --- Resource bars HTML ---
    const resEntries = Object.entries(resMap);
    const resBarHtml = resEntries.map(([name, count]) => {
        const pct = Math.round((count / Math.max(maxTasks, 2)) * 100);
        const isOver = count > 1;
        const fillClass = isOver ? 'fr' : 'fb';
        const numColor = isOver ? '#dc2626' : '#2563eb';
        const label = isOver ? count + '×' : count;
        return `<div class="ur">
            <div class="un">${name}</div>
            <div class="ub"><div class="uf ${fillClass}" style="width:${pct}%"></div></div>
            <div class="up" style="color:${numColor};">${label}</div>
        </div>`;
    }).join('');

    const warnNames = resEntries.filter(([,v]) => v > 1).map(([k]) => k);
    const warnHtml = warnNames.length
        ? `<div class="warn">⚠️ ${warnNames.join(', ')} assigned ${warnNames.length > 1 ? 'multiple tasks' : '2 tasks'} today</div>`
        : '';

    // --- Activity notes ---
    const actRows = rows.filter(r => r.activity_details);
    const actColors = ['#10b981','#3b82f6','#8b5cf6','#f59e0b','#ef4444','#06b6d4'];
    const actHtml = actRows.length
        ? actRows.map((r, i) => {
            const res = r.resource ? r.resource.split('@')[0] : '?';
            const col = actColors[i % actColors.length];
            return `<div class="ai">
                <div class="ad" style="background:${col};"></div>
                <div class="at"><span class="ab">${res}</span> – ${r.activity_details}</div>
            </div>`;
        }).join('')
        : '<div style="font-size:11px;color:#94a3b8;font-style:italic;">No activity notes</div>';

    // --- Full HTML (KPI strip + 3 bottom panels only, NO table) ---
    const html = `
<style>
#tts-dp *{box-sizing:border-box;margin:0;padding:0;}
#tts-dp{font-family:Segoe UI,system-ui,sans-serif;margin-top:14px;}

/* KPI strip */
#tts-dp .ks{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;}
#tts-dp .kp{flex:1;min-width:75px;background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:8px;padding:7px 10px;display:flex;align-items:center;gap:7px;box-shadow:0 1px 2px #0000000a;}
#tts-dp .ki{font-size:15px;}
#tts-dp .kv{font-size:16px;font-weight:700;line-height:1;}
#tts-dp .kl{font-size:8px;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;margin-top:2px;}
#tts-dp .cb{color:#2563eb;}#tts-dp .cg{color:#059669;}
#tts-dp .ca{color:#d97706;}#tts-dp .cp{color:#7c3aed;}#tts-dp .cr{color:#dc2626;}

/* Bottom panels row */
#tts-dp .brow{display:flex;gap:10px;flex-wrap:wrap;}
#tts-dp .bcard{background:#fff;border:1.5px solid #e2e8f0;border-radius:9px;padding:11px 13px;box-shadow:0 1px 4px #0000000d;flex:1;min-width:200px;}
#tts-dp .btitle{font-size:9.5px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.5px;margin-bottom:9px;}

/* Resource bars */
#tts-dp .rrows{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px;}
#tts-dp .ur{display:flex;align-items:center;gap:6px;}
#tts-dp .un{font-size:11px;color:#334155;font-weight:600;width:56px;flex-shrink:0;}
#tts-dp .ub{flex:1;height:7px;background:#f1f5f9;border-radius:4px;overflow:hidden;border:1px solid #e2e8f0;}
#tts-dp .uf{height:100%;border-radius:4px;}
#tts-dp .fb{background:linear-gradient(90deg,#3b82f6,#60a5fa);}
#tts-dp .fg{background:linear-gradient(90deg,#10b981,#34d399);}
#tts-dp .fp{background:linear-gradient(90deg,#8b5cf6,#a78bfa);}
#tts-dp .fa{background:linear-gradient(90deg,#f59e0b,#fbbf24);}
#tts-dp .fr{background:linear-gradient(90deg,#ef4444,#f87171);}
#tts-dp .up{font-size:11px;font-weight:700;width:22px;text-align:right;}
#tts-dp .warn{background:#fef3c7;border:1px solid #fde68a;border-radius:6px;padding:6px 9px;font-size:10px;color:#92400e;font-weight:600;margin-top:8px;}

/* Summary */
#tts-dp .sr{display:flex;justify-content:space-between;align-items:center;padding:4.5px 0;border-bottom:1px solid #f1f5f9;}
#tts-dp .sr:last-child{border-bottom:none;}
#tts-dp .sl{font-size:11px;color:#64748b;}
#tts-dp .sv{font-size:12px;font-weight:700;color:#1e293b;}

/* Activity notes */
#tts-dp .ai{display:flex;gap:7px;align-items:flex-start;margin-bottom:7px;}
#tts-dp .ai:last-child{margin-bottom:0;}
#tts-dp .ad{width:8px;height:8px;border-radius:50%;margin-top:3px;flex-shrink:0;}
#tts-dp .at{font-size:11.5px;color:#475569;line-height:1.4;}
#tts-dp .ab{color:#1e293b;font-weight:700;}
</style>

<div id="tts-dp">
  <!-- KPI STRIP -->
  <div class="ks">
    <div class="kp"><span class="ki">📋</span><div><div class="kv cb">${total}</div><div class="kl">Total Rows</div></div></div>
    <div class="kp"><span class="ki">📁</span><div><div class="kv cg">${prjCount}</div><div class="kl">Prj Tasks</div></div></div>
    <div class="kp"><span class="ki">🎫</span><div><div class="kv ca">${tckCount}</div><div class="kl">Tck Tasks</div></div></div>
    <div class="kp"><span class="ki">👷</span><div><div class="kv cp">${resourceCount}</div><div class="kl">Resources</div></div></div>
    <div class="kp"><span class="ki">✅</span><div><div class="kv cg">${scheduled}</div><div class="kl">Scheduled</div></div></div>
    <div class="kp"><span class="ki">🏁</span><div><div class="kv cb">${completed}</div><div class="kl">Completed</div></div></div>
    <div class="kp"><span class="ki">⚠️</span><div><div class="kv cr">${overCap}</div><div class="kl">Over-cap</div></div></div>
    <div class="kp"><span class="ki">📅</span><div><div class="kv cb">${dateVal}</div><div class="kl">Date</div></div></div>
  </div>

  <!-- BOTTOM 3 PANELS -->
  <div class="brow">

    <!-- Resource Load -->
    <div class="bcard" style="flex:2;">
      <div class="btitle">📊 Resource Load — Today</div>
      <div class="rrows">${resBarHtml}</div>
      ${warnHtml}
    </div>

    <!-- Summary -->
    <div class="bcard" style="flex:1.2;">
      <div class="btitle">📌 Summary</div>
      <div class="sr"><span class="sl">🔵 Prj Tasks</span><span class="sv" style="color:#2563eb;">${prjCount}</span></div>
      <div class="sr"><span class="sl">🟡 Tck Tasks</span><span class="sv" style="color:#d97706;">${tckCount}</span></div>
      <div class="sr"><span class="sl">👷 Resources</span><span class="sv">${resourceCount}</span></div>
      <div class="sr"><span class="sl">✅ Scheduled</span><span class="sv" style="color:#059669;">${scheduled}</span></div>
      <div class="sr"><span class="sl">🏁 Completed</span><span class="sv">${completed}</span></div>
      <div class="sr"><span class="sl">📅 Date</span><span class="sv">${dateVal}</span></div>
    </div>

    <!-- Activity Notes -->
    <div class="bcard" style="flex:1.5;">
      <div class="btitle">📝 Activity Notes</div>
      ${actHtml}
    </div>

  </div>
</div>
    `;

    // Inject AFTER the child table wrapper — does not touch or replace the existing table
    const $wrapper = frm.fields_dict['tech_task_scheduler_list'].$wrapper;
    const $panel = $('<div id="tts-dashboard-panel"></div>').html(html);
    $wrapper.after($panel);
}

frappe.ui.form.on('Tech Task Scheduler', {
    refresh: function(frm) {
        frm.add_custom_button('Send to Individuals (Teams)', function() {
            var rows = frm.doc.tech_task_scheduler_list || [];

            if (!rows.length) {
                frappe.msgprint('No tasks found.');
                return;
            }

            // *** TEST MODE: all messages go to mohan@bitssecureit.com ***
            var TEST_EMAIL = 'mohan@bitssecureit.com';

            var TEAMS_WEBHOOK = 'https://defaulteb49f6d13216449db98436db356acc.9e.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/da85548761934aa78636e18344c79fc6/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=XdJe3NZPpZhpeZ3-TkUNJm5vaBRfG69MKirgndDWlMI';

            // Group rows by resource email
            var resourceMap = {};
            rows.forEach(function(row) {
                var res = row.resource || 'Unknown';
                if (!resourceMap[res]) resourceMap[res] = [];
                resourceMap[res].push(row);
            });

            // Fetch project names and task names
            frappe.call({
                method: 'frappe.client.get_list',
                args: { doctype: 'Project', fields: ['name', 'project_name'], limit_page_length: 500 },
                callback: function(pr) {
                    var pNames = {};
                    (pr.message || []).forEach(function(p) { pNames[p.name] = p.project_name; });

                    frappe.call({
                        method: 'frappe.client.get_list',
                        args: { doctype: 'Task', fields: ['name', 'subject'], limit_page_length: 500 },
                        callback: function(tr) {
                            var tNames = {};
                            (tr.message || []).forEach(function(t) { tNames[t.name] = t.subject; });

                            var resources = Object.keys(resourceMap);

                            // Build combined preview
                            var previewHTML = '';
                            resources.forEach(function(email) {
                                previewHTML += buildPreviewBlock(resourceMap[email], email, pNames, tNames);
                                previewHTML += '<hr style="margin:16px 0;border:0;border-top:2px dashed #ccc">';
                            });

                            // Show preview dialog
                            var d = new frappe.ui.Dialog({
                                title: '[TEST] Preview — Sending all to ' + TEST_EMAIL,
                                fields: [{
                                    fieldtype: 'HTML',
                                    options: '<div style="max-height:450px;overflow-y:auto;padding:10px">' + previewHTML + '</div>'
                                }],
                                primary_action_label: 'Send Now',
                                primary_action: function() {
                                    d.hide();
                                    var sentCount = 0, failedCount = 0, completedCount = 0;

                                    resources.forEach(function(email) {
                                        if (!email || email === 'Unknown') {
                                            failedCount++; completedCount++; checkDone(); return;
                                        }

                                        var msg = buildMessage(resourceMap[email], email, pNames, tNames);

                                        fetch(TEAMS_WEBHOOK, {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ message: msg, allocated_to: email })
                                        })
                                        .then(function(res) {
                                            if (res.ok) { sentCount++; } else { failedCount++; }
                                            completedCount++;
                                            checkDone();
                                        })
                                        .catch(function() {
                                            failedCount++; completedCount++; checkDone();
                                        });
                                    });

                                    function checkDone() {
                                        if (completedCount === resources.length) {
                                            if (failedCount === 0) {
                                                frappe.show_alert({ message: 'TEST: Sent ' + sentCount + ' messages to ' + TEST_EMAIL, indicator: 'green' });
                                            } else {
                                                frappe.msgprint('Sent: ' + sentCount + ' | Failed: ' + failedCount);
                                            }
                                        }
                                    }
                                },
                                secondary_action_label: 'Cancel',
                                secondary_action: function() { d.hide(); }
                            });
                            d.show();
                        }
                    });
                }
            });
        }, 'Send via Teams');

        // Build the HTML message body for one person
        function buildMessage(personRows, email, pNames, tNames) {
            var name = email.replace('@bitssecureit.com', '');
            var cap = name.charAt(0).toUpperCase() + name.slice(1);
            var today = (function(){var d=personRows.map(function(r){return r&&r.date?r.date:null;}).filter(Boolean);var uniq={};d.forEach(function(x){uniq[x]=1;});var arr=Object.keys(uniq).sort();if(!arr.length){return new Date().toLocaleDateString('en-GB',{weekday:'long'})+', '+new Date().toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'});}var a=new Date(arr[0]),b=new Date(arr[arr.length-1]);var fDay=function(x){return x.toLocaleDateString('en-GB',{day:'2-digit'});};var fMon=function(x){return x.toLocaleDateString('en-GB',{month:'short'});};var fYr=function(x){return x.toLocaleDateString('en-GB',{year:'numeric'});};var fWd=function(x){return x.toLocaleDateString('en-GB',{weekday:'long'});};if(arr.length===1){return fWd(a)+', '+fDay(a)+' '+fMon(a)+' '+fYr(a);}var n=personRows.length,suffix=' ('+n+' task'+(n>1?'s':'')+')';if(fYr(a)===fYr(b)&&fMon(a)===fMon(b)){return fDay(a)+'–'+fDay(b)+' '+fMon(a)+' '+fYr(a)+suffix;}if(fYr(a)===fYr(b)){return fDay(a)+' '+fMon(a)+' → '+fDay(b)+' '+fMon(b)+' '+fYr(a)+suffix;}return fDay(a)+' '+fMon(a)+' '+fYr(a)+' → '+fDay(b)+' '+fMon(b)+' '+fYr(b)+suffix;})();
            var isSingleDate = (function(){var __d={};personRows.forEach(function(r){if(r&&r.date)__d[r.date]=1;});return Object.keys(__d).length<=1;})();
            var lines = ['<b>📋 ' + cap + ' Schedule — ' + today + '</b>', ''];

            personRows.forEach(function(row) {
                var projId   = row.category_name || '';
                var taskId   = row.task || '';
                var activity = row.activity_details || '';
                var catType  = row.category || '';

                var proj = projId ? (pNames[projId] || projId) : (catType || '');
                var task = taskId ? (tNames[taskId] || taskId) : '';

                var rowDateStr = (!isSingleDate && row && row.date) ? (new Date(row.date).toLocaleDateString('en-GB',{weekday:'long'}) + ', ' + new Date(row.date).toLocaleDateString('en-GB',{day:'2-digit',month:'short'})) : '';
            var blockParts = [];
            if (rowDateStr) blockParts.push('🗓 <b>' + rowDateStr + '</b>');
            if (proj) blockParts.push('🔵 <b>Project:</b> ' + proj);
            if (task) blockParts.push('🎯 <b>Task:</b> ' + task);
            if (activity) blockParts.push('📝 <b>Activity:</b> ' + activity);
            if (blockParts.length) lines.push(blockParts.join('<br>'));
            });

            var title = lines[0]; var blocks = lines.slice(2); return title + '<br><br>' + blocks.join('<br>──────────────<br>');
        }

        // Build preview block for dialog
        function buildPreviewBlock(personRows, email, pNames, tNames) {
            var name = email.replace('@bitssecureit.com', '');
            var cap = name.charAt(0).toUpperCase() + name.slice(1);
            var today = (function(){var d=personRows.map(function(r){return r&&r.date?r.date:null;}).filter(Boolean);var uniq={};d.forEach(function(x){uniq[x]=1;});var arr=Object.keys(uniq).sort();if(!arr.length){return new Date().toLocaleDateString('en-GB',{weekday:'long'})+', '+new Date().toLocaleDateString('en-GB',{day:'2-digit',month:'short',year:'numeric'});}var a=new Date(arr[0]),b=new Date(arr[arr.length-1]);var fDay=function(x){return x.toLocaleDateString('en-GB',{day:'2-digit'});};var fMon=function(x){return x.toLocaleDateString('en-GB',{month:'short'});};var fYr=function(x){return x.toLocaleDateString('en-GB',{year:'numeric'});};var fWd=function(x){return x.toLocaleDateString('en-GB',{weekday:'long'});};if(arr.length===1){return fWd(a)+', '+fDay(a)+' '+fMon(a)+' '+fYr(a);}var n=personRows.length,suffix=' ('+n+' task'+(n>1?'s':'')+')';if(fYr(a)===fYr(b)&&fMon(a)===fMon(b)){return fDay(a)+'–'+fDay(b)+' '+fMon(a)+' '+fYr(a)+suffix;}if(fYr(a)===fYr(b)){return fDay(a)+' '+fMon(a)+' → '+fDay(b)+' '+fMon(b)+' '+fYr(a)+suffix;}return fDay(a)+' '+fMon(a)+' '+fYr(a)+' → '+fDay(b)+' '+fMon(b)+' '+fYr(b)+suffix;})();

            var html = '<div style="margin-bottom:6px;font-weight:bold;color:#555">To: ' + name + ' (' + email + ')</div>';
            html += '<div style="font-size:13px;background:#f9f9f9;padding:10px;border-radius:4px">';
            var isSingleDate = (function(){var __d={};personRows.forEach(function(r){if(r&&r.date)__d[r.date]=1;});return Object.keys(__d).length<=1;})();
            html += '<b>📋 ' + cap + ' Schedule — ' + today + '</b><br><br>';

            var _rowBlocks = [];
        personRows.forEach(function(row) {
                var projId   = row.category_name || '';
                var taskId   = row.task || '';
                var activity = row.activity_details || '';
                var catType  = row.category || '';

                var proj = projId ? (pNames[projId] || projId) : (catType || '');
                var task = taskId ? (tNames[taskId] || taskId) : '';

                var rowDateStr = (!isSingleDate && row && row.date) ? (new Date(row.date).toLocaleDateString('en-GB',{weekday:'long'}) + ', ' + new Date(row.date).toLocaleDateString('en-GB',{day:'2-digit',month:'short'})) : '';
            var blockParts = [];
            if (rowDateStr) blockParts.push('🗓 <b>' + rowDateStr + '</b>');
            if (proj) blockParts.push('🔵 <b>Project:</b> ' + proj);
            if (task) blockParts.push('🎯 <b>Task:</b> ' + task);
            if (activity) blockParts.push('📝 <b>Activity:</b> ' + activity);
            if (blockParts.length) _rowBlocks.push(blockParts.join('<br>'));
            });

            html += _rowBlocks.join('──────────────<br>');
        html += '</div>';
            return html;
        }
    }
});

frappe.ui.form.on('Tech Task Scheduler', {
  refresh: function(frm) {

    frm.add_custom_button('Send to Projects Team Group', function() {
      var rows = frm.doc.tech_task_scheduler_list || [];

      if (!rows.length) {
        frappe.msgprint('No tasks found.');
        return;
      }

      var TEAMS_WEBHOOK = 'https://defaulteb49f6d13216449db98436db356acc.9e.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/a20c9a3f0e09400abcadcedbd0911459/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=l6E8L4H-S1c_Vv6qTW4hbfA6ay6XL-wHJpJM3TduYBc';

      var resourceMap = {};
      rows.forEach(function(row) {
        var res = row.resource || 'Unknown';
        if (!resourceMap[res]) resourceMap[res] = [];
        resourceMap[res].push(row);
      });

      frappe.call({
        method: 'frappe.client.get_list',
        args: { doctype: 'Project', fields: ['name', 'project_name'], limit_page_length: 500 },
        callback: function(pr) {
          var pNames = {};
          (pr.message || []).forEach(function(p) { pNames[p.name] = p.project_name; });

          frappe.call({
            method: 'frappe.client.get_list',
            args: { doctype: 'Task', fields: ['name', 'subject'], limit_page_length: 500 },
            callback: function(tr) {
              var tNames = {};
              (tr.message || []).forEach(function(t) { tNames[t.name] = t.subject; });

              var resources = Object.keys(resourceMap);

              // Build ONE combined message for the group channel
              var combinedMessage = buildGroupMessage(rows, resources, resourceMap, pNames, tNames);

              // Build preview HTML
              var previewHTML = buildGroupPreviewHTML(rows, resources, resourceMap, pNames, tNames);

              var d = new frappe.ui.Dialog({
                title: 'Preview — Send to Projects Team Group',
                fields: [{
                  fieldtype: 'HTML',
                  options: '<div style="max-height:450px;overflow-y:auto;padding:10px">' + previewHTML + '</div>'
                }],
                primary_action_label: 'Send Now',
                primary_action: function() {
                  d.hide();
                  fetch(TEAMS_WEBHOOK, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: combinedMessage })
                  })
                  .then(function(res) {
                    if (res.ok) {
                      frappe.show_alert({ message: 'Schedule sent to Projects Team Group!', indicator: 'green' });
                    } else {
                      frappe.msgprint('Failed to send. Status: ' + res.status);
                    }
                  })
                  .catch(function(err) {
                    frappe.msgprint('Error: ' + err.message);
                  });
                },
                secondary_action_label: 'Cancel',
                secondary_action: function() { d.hide(); }
              });
              d.show();
            }
          });
        }
      });
    }, 'Send via Teams');

    function getDateLabel(personRows) {
      var d = personRows.map(function(r) { return r && r.date ? r.date : null; }).filter(Boolean);
      var uniq = {};
      d.forEach(function(x) { uniq[x] = 1; });
      var arr = Object.keys(uniq).sort();
      if (!arr.length) {
        return new Date().toLocaleDateString('en-GB', { weekday: 'long' }) + ', ' +
               new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
      }
      var a = new Date(arr[0]);
      if (arr.length === 1) {
        return a.toLocaleDateString('en-GB', { weekday: 'long' }) + ', ' +
               a.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
      }
      var b = new Date(arr[arr.length - 1]);
      return a.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) + ' – ' +
             b.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    }

    function buildGroupMessage(rows, resources, resourceMap, pNames, tNames) {
      // Get the date from the first row
      var dateLabel = getDateLabel(rows);

      var lines = ['<b>📋 Team Schedule — ' + dateLabel + '</b>', ''];

      resources.forEach(function(email) {
        if (!email || email === 'Unknown') return;
        var name = email.replace('@bitssecureit.com', '');
        var cap = name.charAt(0).toUpperCase() + name.slice(1);
        var personRows = resourceMap[email];

        lines.push('<b>👤 ' + cap + '</b>');

        personRows.forEach(function(row) {
          var projId = row.category_name || '';
          var taskId = row.task || '';
          var activity = row.activity_details || '';
          var catType = row.category || '';
          var proj = projId ? (pNames[projId] || projId) : (catType || '');
          var task = taskId ? (tNames[taskId] || taskId) : '';

          var blockParts = [];
          if (proj) blockParts.push('🔵 <b>Project:</b> ' + proj);
          if (task) blockParts.push('🎯 <b>Task:</b> ' + task);
          if (activity) blockParts.push('📝 <b>Activity:</b> ' + activity);
          if (blockParts.length) lines.push(blockParts.join('<br>'));
        });

        lines.push('──────────────');
      });

      return lines.join('<br>');
    }

    function buildGroupPreviewHTML(rows, resources, resourceMap, pNames, tNames) {
      var dateLabel = getDateLabel(rows);
      var html = '<div style="font-size:14px;font-weight:bold;margin-bottom:12px">📋 Team Schedule — ' + dateLabel + '</div>';

      resources.forEach(function(email) {
        if (!email || email === 'Unknown') return;
        var name = email.replace('@bitssecureit.com', '');
        var cap = name.charAt(0).toUpperCase() + name.slice(1);
        var personRows = resourceMap[email];

        html += '<div style="margin-bottom:6px;font-weight:bold;color:#444">👤 ' + cap + ' (' + email + ')</div>';
        html += '<div style="font-size:13px;background:#f9f9f9;padding:8px;border-radius:4px;margin-bottom:10px">';

        personRows.forEach(function(row) {
          var projId = row.category_name || '';
          var taskId = row.task || '';
          var activity = row.activity_details || '';
          var catType = row.category || '';
          var proj = projId ? (pNames[projId] || projId) : (catType || '');
          var task = taskId ? (tNames[taskId] || taskId) : '';

          var parts = [];
          if (proj) parts.push('🔵 <b>Project:</b> ' + proj);
          if (task) parts.push('🎯 <b>Task:</b> ' + task);
          if (activity) parts.push('📝 <b>Activity:</b> ' + activity);
          if (parts.length) html += parts.join('<br>') + '<br>';
        });

        html += '</div>';
      });

      return html;
    }
  }
});
