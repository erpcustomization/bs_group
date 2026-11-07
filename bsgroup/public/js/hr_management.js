/* HR Management: navigation and review, with all actions in native HRMS forms. */
window.bsHRManagement = async function (parent) {
    const root = $(parent).empty().addClass('hrm-host');
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    const descriptions = {
        employees: 'Employee records and employment details', onboarding: 'Joining tasks and onboarding checklists',
        attendance: 'Recorded check-ins and check-outs for today', leave: 'Open applications awaiting review',
        policies: 'Organization documents, rules and policies', warnings: 'Confidential warning reviews and responses',
        exit: 'Exit feedback and interview records', offboarding: 'Separation tasks and handover checklists',
        requests: 'Letters, document updates and HR enquiries'
    };
    const symbols = {employees:'users',onboarding:'add',attendance:'clock',leave:'calendar',policies:'file',warnings:'shield',exit:'message',offboarding:'exit',requests:'inbox'};
    const paths = {
        users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8m6 10v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
        add:'M12 5v14M5 12h14',clock:'M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
        calendar:'M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2',
        file:'M14 2H4v20h16V8l-6-6v6h6M8 12h8m-8 4h8',shield:'M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6L12 2M12 7v6m0 3v1',
        message:'M21 3H3v14h5l4 4 4-4h5V3M7 7h10M7 11h6',exit:'M9 3H3v18h6m6-14 5 5-5 5M7 12h13',inbox:'M4 3h16l2 12v6H2v-6L4 3M2 15h6l2 3h4l2-3h6'
    };
    const icon = key => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[key] || paths.file}"/></svg>`;
    if (!document.getElementById('hrm-styles')) $('<style id="hrm-styles">').text(`
      .hrm-host{color:#193047}.hrm-layout{display:grid;grid-template-columns:190px minmax(0,1fr);gap:20px}
      .hrm-nav{display:flex;flex-direction:column;gap:4px}.hrm-nav button{display:flex;align-items:center;gap:10px;text-align:left;background:transparent;border:0;border-radius:9px;padding:11px 12px;color:#526579;font-size:13px;cursor:pointer}
      .hrm-nav button.active{background:#e5f2f0;color:#126d66;font-weight:650}.hrm-nav button:hover{background:#eef2f5}.hrm-host svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;flex-shrink:0}
      .hrm-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:20px}.hrm-top h2{font-size:22px;letter-spacing:-.5px;margin:0 0 5px}.hrm-muted{font-size:12px;color:#728295}.hrm-actions{display:flex;gap:8px;flex-wrap:wrap}
      .hrm-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:22px}.hrm-kpi{background:white;border:1px solid #dfe7ed;border-radius:13px;padding:18px;text-align:left;cursor:pointer;color:#193047}.hrm-kpi span{font-size:12px;color:#627587;display:block}.hrm-kpi strong{font-size:29px;display:block;line-height:1.4;font-weight:650}.hrm-kpi small{font-size:11px;color:#758697}
      .hrm-panel{background:#fff;border:1px solid #dfe7ed;border-radius:13px;overflow:hidden;margin-bottom:16px}.hrm-panel-head{padding:18px 20px;border-bottom:1px solid #edf1f4;display:flex;justify-content:space-between;align-items:center;gap:12px}.hrm-panel-head h3{font-size:15px;margin:0}.hrm-table-wrap{overflow-x:auto}.hrm-table{width:100%;font-size:12px;border-collapse:collapse}.hrm-table th{text-align:left;font-size:11px;color:#748596;font-weight:600;background:#fafbfd}.hrm-table th,.hrm-table td{padding:12px 18px;border-bottom:1px solid #edf1f4}.hrm-table td:first-child{max-width:330px}.hrm-table a{font-weight:600;color:#215b79}.hrm-tag{display:inline-block;background:#edf3f7;padding:4px 8px;border-radius:6px;font-size:11px;white-space:nowrap}.hrm-empty{padding:30px 20px;color:#738496;font-size:13px}.hrm-modules{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.hrm-module{background:#fff;border:1px solid #dfe7ed;border-radius:12px;padding:16px;text-align:left;cursor:pointer;color:#193047}.hrm-module strong{display:block;font-size:13px;margin:10px 0 5px}.hrm-module small{font-size:11px;color:#748596}.hrm-foot{margin-top:18px;font-size:11px;color:#748596}.hrm-host button:focus-visible{outline:3px solid #8cc9c0;outline-offset:2px}
      @media(max-width:1050px){.hrm-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.hrm-modules{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.hrm-layout{grid-template-columns:1fr}.hrm-nav{flex-direction:row;overflow:auto}.hrm-nav button{white-space:nowrap}.hrm-top{align-items:flex-start}.hrm-modules{grid-template-columns:1fr}.hrm-kpi{padding:12px}}
    `).appendTo(document.head);
    root.html('<div class="hrd-loading">Loading HR Management…</div>');
    let data, selected='dashboard';
    const openList = section => {
        frappe.route_options = section.filters || {};
        frappe.set_route('List',section.doctype);
    };
    function table(section) {
        const box=$('<section class="hrm-panel">');
        const head=$('<div class="hrm-panel-head">').appendTo(box);
        $('<h3>').text(section.label).appendTo(head);
        if (!section.available) {
            $('<div class="hrm-empty">').text(section.reason).appendTo(box);
            return box;
        }
        const actions=$('<div class="hrm-actions">').appendTo(head);
        $('<button class="btn btn-default btn-sm">').text(__('View all')).on('click',()=>openList(section)).appendTo(actions);
        if(section.can_create && !['attendance','leave'].includes(section.key)) $('<button class="btn btn-primary btn-sm">').text(__('New')).on('click',()=>frappe.new_doc(section.doctype)).appendTo(actions);
        if (!section.rows.length) { $('<div class="hrm-empty">').text(section.key==='leave'?'No open leave applications awaiting review.':'No matching records.').appendTo(box); return box; }
        const body=section.rows.map(row=>{
            const title=row[section.title_field] || row.name;
            const status=row[section.status_field] || ['Draft','Submitted','Cancelled'][row.docstatus] || '—';
            const detail=row.time || (row.from_date ? `${row.from_date} – ${row.to_date}` : row.company || row.employee || '');
            const url='/desk/'+frappe.router.slug(section.doctype)+'/'+encodeURIComponent(row.name);
            return `<tr><td><a href="${esc(url)}">${esc(title)}</a><div class="hrm-muted">${esc(row.name)}</div></td><td><span class="hrm-tag">${esc(status)}</span></td><td>${esc(detail)}</td><td>${esc(frappe.datetime.str_to_user(row.modified))}</td></tr>`;
        }).join('');
        box.append(`<div class="hrm-table-wrap"><table class="hrm-table"><thead><tr><th>Record</th><th>Status</th><th>${section.key==='attendance'?'Check-in / out time':section.key==='leave'?'Leave dates':'Details'}</th><th>Updated</th></tr></thead><tbody>${body}</tbody></table></div>`);
        return box;
    }
    function render() {
        root.empty();
        const layout=$('<div class="hrm-layout">').appendTo(root);
        const nav=$('<nav class="hrm-nav" aria-label="HR Management sections">').appendTo(layout);
        [{key:'dashboard',label:'Dashboard'},...data.sections].forEach(s=>{
            $('<button type="button">').toggleClass('active',s.key===selected).attr('aria-current',s.key===selected?'page':null)
                .html(icon(symbols[s.key]||'inbox')+`<span>${esc(s.label)}</span>`).on('click',()=>{selected=s.key;render();}).appendTo(nav);
        });
        const main=$('<div class="hrm-main">').appendTo(layout);
        const section=data.sections.find(s=>s.key===selected);
        const top=$('<div class="hrm-top">').appendTo(main);
        $('<div>').html(`<h2>${esc(section?.label || 'People & operations')}</h2><div class="hrm-muted">${esc(section?descriptions[selected]:'Live HRMS records · '+data.date)}</div>`).appendTo(top);
        $('<button class="btn btn-default btn-sm">').text('Refresh').on('click',load).appendTo(top);
        if(section) {
            if(['warnings','requests'].includes(section.key)) $('<p class="hrm-muted">').text('Confidential administrator register. Saving a record does not issue a warning, notify an employee or change employment status.').appendTo(main);
            main.append(table(section));
        } else {
            const cards=$('<div class="hrm-kpis">').appendTo(main);
            const labels={employees:['Active employees','Active profiles'],leave:['Leave approvals','Open applications'],onboarding:['Onboarding','Non-cancelled records'],offboarding:['Offboarding','Non-cancelled records']};
            Object.entries(labels).forEach(([key,[label,foot]])=>{
                const s=data.sections.find(x=>x.key===key);
                $('<button class="hrm-kpi">').html(`<span>${esc(label)}</span><strong>${s.available?esc(s.count):'—'}</strong><small>${esc(s.available?foot:s.reason)}</small>`).on('click',()=>{selected=key;render();}).appendTo(cards);
            });
            main.append(table(data.sections.find(s=>s.key==='leave')));
            const modules=$('<div class="hrm-modules">').appendTo(main);
            data.sections.filter(s=>s.key!=='leave').forEach(s=>{
                $('<button class="hrm-module">').html(`${icon(symbols[s.key])}<strong>${esc(s.label)}</strong><small>${esc(s.available?descriptions[s.key]:s.reason)}</small>`).on('click',()=>{selected=s.key;render();}).appendTo(modules);
            });
        }
        if(data.setup_pending && data.can_setup) {
            $('<button class="btn btn-default btn-sm">').text('Set up confidential registers').on('click',async function(){
                $(this).prop('disabled',true);
                try {await frappe.call({method:'bsgroup.hr_management.setup_registers',type:'POST',freeze:true});await load();}
                finally {$(this).prop('disabled',false);}
            }).appendTo(main);
        }
        $('<p class="hrm-foot">').text('Only records allowed by your existing HRMS access are shown. Open a record to use its existing approval process.').appendTo(main);
    }
    async function load() {
        try {const r=await frappe.call({method:'bsgroup.hr_management.overview'});data=r.message;render();}
        catch(e) {root.html('<div class="hrm-empty">HR Management could not load. Please refresh or contact your administrator.</div>');}
    }
    await load();
};
