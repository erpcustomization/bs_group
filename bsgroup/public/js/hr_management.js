/* HR Management: navigation and review, with all actions in native HRMS forms. */
window.bsHRManagement = async function (parent) {
    const root = $(parent).empty().addClass('hrm-host');
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    const descriptions = {
        organization: 'Reporting relationships recorded in HRMS',
        employees: 'Employee records and employment details', onboarding: 'Joining tasks and onboarding checklists',
        attendance: 'Monthly employee calendar, recorded punches and leave decisions', leave: 'Open applications awaiting review',
        policies: 'Organization documents, rules and policies', warnings: 'Confidential warning reviews and responses',
        exit: 'Exit feedback and interview records', offboarding: 'Separation tasks and handover checklists',
        requests: 'Letters, document updates and HR enquiries'
    };
    const symbols = {organization:'users',employees:'users',onboarding:'add',attendance:'clock',leave:'calendar',policies:'file',warnings:'shield',exit:'message',offboarding:'exit',requests:'inbox'};
    const paths = {
        users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8m6 10v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
        add:'M12 5v14M5 12h14',clock:'M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
        calendar:'M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2',
        file:'M14 2H4v20h16V8l-6-6v6h6M8 12h8m-8 4h8',shield:'M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6L12 2M12 7v6m0 3v1',
        message:'M21 3H3v14h5l4 4 4-4h5V3M7 7h10M7 11h6',exit:'M9 3H3v18h6m6-14 5 5-5 5M7 12h13',inbox:'M4 3h16l2 12v6H2v-6L4 3M2 15h6l2 3h4l2-3h6'
    };
    const icon = key => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${paths[key] || paths.file}"/></svg>`;
    if (!document.getElementById('hrm-styles')) $('<style id="hrm-styles">').text(`
      .hrm-host{color:#193047}.hrm-layout{display:block}
      .hrm-org{padding:18px}.hrm-org ul{list-style:none;padding:0;margin:0}.hrm-org ul ul{margin:8px 0 12px 18px;padding-left:18px;border-left:1px solid #d9e5eb}.hrm-org li{margin:8px 0}.hrm-person{padding:12px 14px;border:1px solid #dfe7ed;border-radius:10px;background:#fafcfd;display:flex;align-items:center;gap:12px;flex-wrap:wrap}.hrm-person a{font-size:13px;font-weight:650;color:#215b79}.hrm-person .hrm-muted{margin-top:3px}.hrm-avatar{width:34px;height:34px;border-radius:10px;background:#e4f0ed;color:#24716b;display:grid;place-items:center;font-weight:650}.hrm-org summary{cursor:pointer;list-style:none}.hrm-org summary::-webkit-details-marker{display:none}.hrm-org summary .hrm-person:after{content:'−';margin-left:auto;color:#728295}.hrm-org details:not([open])>summary .hrm-person:after{content:'+'}.hrm-org-note{font-size:11px;color:#906519;margin-top:4px}
      .hrm-nav{display:flex;flex-direction:column;gap:4px}.hrm-nav button{display:flex;align-items:center;gap:10px;text-align:left;background:transparent;border:0;border-radius:9px;padding:11px 12px;color:#526579;font-size:13px;cursor:pointer}
      .hrm-nav button.active{background:#e5f2f0;color:#126d66;font-weight:650}.hrm-nav button:hover{background:#eef2f5}.hrm-host svg{width:19px;height:19px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round;flex-shrink:0}
      .hrm-top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:20px}.hrm-top h2{font-size:22px;letter-spacing:-.5px;margin:0 0 5px}.hrm-muted{font-size:12px;color:#728295}.hrm-actions{display:flex;gap:8px;flex-wrap:wrap}
      .hrm-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:22px}.hrm-kpi{background:white;border:1px solid #dfe7ed;border-radius:13px;padding:18px;text-align:left;cursor:pointer;color:#193047}.hrm-kpi span{font-size:12px;color:#627587;display:block}.hrm-kpi strong{font-size:29px;display:block;line-height:1.4;font-weight:650}.hrm-kpi small{font-size:11px;color:#758697}
      .hrm-panel{background:#fff;border:1px solid #dfe7ed;border-radius:13px;overflow:hidden;margin-bottom:16px}.hrm-panel-head{padding:18px 20px;border-bottom:1px solid #edf1f4;display:flex;justify-content:space-between;align-items:center;gap:12px}.hrm-panel-head h3{font-size:15px;margin:0}.hrm-table-wrap{overflow-x:auto}.hrm-table{width:100%;font-size:12px;border-collapse:collapse}.hrm-table th{text-align:left;font-size:11px;color:#748596;font-weight:600;background:#fafbfd}.hrm-table th,.hrm-table td{padding:12px 18px;border-bottom:1px solid #edf1f4}.hrm-table td:first-child{max-width:330px}.hrm-table a{font-weight:600;color:#215b79}.hrm-tag{display:inline-block;background:#edf3f7;padding:4px 8px;border-radius:6px;font-size:11px;white-space:nowrap}.hrm-empty{padding:30px 20px;color:#738496;font-size:13px}.hrm-modules{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.hrm-module{background:#fff;border:1px solid #dfe7ed;border-radius:12px;padding:16px;text-align:left;cursor:pointer;color:#193047}.hrm-module strong{display:block;font-size:13px;margin:10px 0 5px}.hrm-module small{font-size:11px;color:#748596}.hrm-foot{margin-top:18px;font-size:11px;color:#748596}.hrm-host button:focus-visible{outline:3px solid #8cc9c0;outline-offset:2px}
      @media(max-width:1050px){.hrm-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.hrm-modules{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.hrm-layout{grid-template-columns:1fr}.hrm-nav{flex-direction:row;overflow:auto}.hrm-nav button{white-space:nowrap}.hrm-top{align-items:flex-start}.hrm-modules{grid-template-columns:1fr}.hrm-kpi{padding:12px}}
    `).appendTo(document.head);
    root.html('<div class="hrd-loading">Loading HR Management…</div>');
    let data, selected=new URLSearchParams(location.search).get('hr_section') || 'dashboard';
    window.bsHRSelectSection = key => {
        const valid=['dashboard','organization',...(data?.sections || []).map(s=>s.key)];
        selected=valid.includes(key)?key:'dashboard';
        if(data && root[0].isConnected)render();
    };
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
    async function organization(main) {
        const panel=$('<section class="hrm-panel"><div class="hrm-empty">Loading organization structure…</div></section>').appendTo(main);
        try {
            const response=await frappe.call({method:'bsgroup.hr_management.organization'});
            if(!panel[0].isConnected) return;
            const employees=response.message.employees || [];
            panel.empty();
            $('<div class="hrm-panel-head">').html(`<h3>Organization Structure</h3><span class="hrm-muted">${employees.length} active employees in your view</span>`).appendTo(panel);
            if(!employees.length) {$('<div class="hrm-empty">').text('No active employee profiles are available in your view.').appendTo(panel);return;}
            const byId=new Map(employees.map(e=>[e.name,e])), children=new Map(), shown=new Set();
            employees.forEach(e=>{if(e.reports_to && byId.has(e.reports_to)){if(!children.has(e.reports_to))children.set(e.reports_to,[]);children.get(e.reports_to).push(e);}});
            const chart=$('<div class="hrm-org">').appendTo(panel), tree=$('<ul aria-label="Employee reporting structure">').appendTo(chart);
            function node(employee,list,review=false) {
                if(shown.has(employee.name))return;
                shown.add(employee.name);
                const reports=(children.get(employee.name)||[]).filter(e=>!shown.has(e.name));
                const li=$('<li>').appendTo(list);
                const holder=reports.length?$('<summary>').appendTo($('<details open>').appendTo(li)):li;
                const card=$('<div class="hrm-person">').appendTo(holder);
                $('<span class="hrm-avatar" aria-hidden="true">').text((employee.employee_name||employee.name).split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase()).appendTo(card);
                const text=$('<div>').appendTo(card);
                $('<a>').attr('href','/desk/employee/'+encodeURIComponent(employee.name)).text(employee.employee_name||employee.name).on('click',e=>e.stopPropagation()).appendTo(text);
                $('<div class="hrm-muted">').text([employee.designation,employee.department,employee.company].filter(Boolean).join(' · ')).appendTo(text);
                let note=review?'Reporting relationships need HR review.':employee.manager_outside_view?'Reporting manager is outside this active employee view.':!employee.reports_to?'No reporting manager recorded.':'';
                if(note)$('<div class="hrm-org-note">').text(note).appendTo(text);
                if(reports.length){$('<span class="hrm-tag">').text(`${reports.length} direct report${reports.length===1?'':'s'}`).appendTo(card);const sub=$('<ul>').appendTo(holder.parent());reports.forEach(e=>node(e,sub));}
            }
            employees.filter(e=>!e.reports_to).forEach(e=>node(e,tree));
            // Cyclic or otherwise inconsistent relationships remain visible, never recurse forever.
            employees.filter(e=>!shown.has(e.name)).forEach(e=>node(e,tree,true));
            $('<p class="hrm-foot">').text('Select a manager to expand or collapse their team. Missing reporting lines are shown as recorded; no relationships have been assumed.').appendTo(chart);
        } catch(e) {if(panel[0].isConnected)panel.html('<div class="hrm-empty">Organization structure is unavailable. Check your Employee access or try Refresh.</div>');}
    }
    function render() {
        root.empty();
        const layout=$('<div class="hrm-layout">').appendTo(root);
        const main=$('<div class="hrm-main">').appendTo(layout);
        const section=selected==='organization'?{key:'organization',label:'Organization Structure'}:data.sections.find(s=>s.key===selected);
        const top=$('<div class="hrm-top">').appendTo(main);
        $('<div>').html(`<h2>${esc(section?.label || 'People & operations')}</h2><div class="hrm-muted">${esc(section?descriptions[selected]:'Live HRMS records · '+data.date)}</div>`).appendTo(top);
        $('<button class="btn btn-default btn-sm">').text('Refresh').on('click',load).appendTo(top);
        if(selected==='organization') {
            organization(main);
        } else if(selected==='attendance') {
            window.bsHRAttendance(main);
        } else if(section) {
            if(['warnings','requests'].includes(section.key)) $('<p class="hrm-muted">').text('Confidential administrator register. Saving a record does not issue a warning, notify an employee or change employment status.').appendTo(main);
            main.append(table(section));
        } else {
            const cards=$('<div class="hrm-kpis">').appendTo(main);
            const labels={employees:['Active employees','Active profiles'],leave:['Leave approvals','Open applications'],onboarding:['Onboarding','Non-cancelled records'],offboarding:['Offboarding','Non-cancelled records']};
            Object.entries(labels).forEach(([key,[label,foot]])=>{
                const s=data.sections.find(x=>x.key===key);
                $('<button class="hrm-kpi">').html(`<span>${esc(label)}</span><strong>${s.available?esc(s.count):'—'}</strong><small>${esc(s.available?foot:s.reason)}</small>`).on('click',()=>frappe.set_route('hr-dashboard',{hr_section:key})).appendTo(cards);
            });
            main.append(table(data.sections.find(s=>s.key==='leave')));
            const modules=$('<div class="hrm-modules">').appendTo(main);
            data.sections.filter(s=>s.key!=='leave').forEach(s=>{
                $('<button class="hrm-module">').html(`${icon(symbols[s.key])}<strong>${esc(s.label)}</strong><small>${esc(s.available?descriptions[s.key]:s.reason)}</small>`).on('click',()=>frappe.set_route('hr-dashboard',{hr_section:s.key})).appendTo(modules);
            });
        }
        if(data.can_setup) {
            const admin=$('<div class="hrm-actions">').appendTo(main);
            $('<button class="btn btn-default btn-sm">').text('Review Muskan access').on('click',async()=>{
                const r=await frappe.call({method:'bsgroup.hr_management.muskan_access_review'});
                const a=r.message;
                frappe.msgprint({title:'BS HR access review',message:`<p><b>${esc(a.full_name)}</b> · ${esc(a.user)}</p><p>Existing roles: ${esc(a.roles.join(', '))}</p><table class="hrm-table"><tr><th>Section</th><th>Read</th><th>Edit</th><th>Create</th></tr>${a.current.map(x=>`<tr><td>${esc(x.doctype)}</td><td>${x.read?'Yes':'No'}</td><td>${x.write?'Yes':'No'}</td><td>${x.create?'Yes':'No'}</td></tr>`).join('')}</table><p>Prepared addition: BS HR Management — read, create and edit Warnings, HR Requests and Organization Documents; read policy categories. No System Manager, deletion, sharing or approval bypass rights will be added.</p><p>Access changes await confirmation.</p>`,wide:true,primary_action:{label:'Apply access',action:()=>{
                    frappe.confirm('Grant Muskan read, create and edit access to Organization Documents, HR Warnings and HR Service Requests, plus read access to policy categories? Existing company restrictions and approvals remain in force.',async()=>{
                        await frappe.call({method:'bsgroup.hr_management.grant_muskan_access',type:'POST',freeze:true});
                        frappe.msgprint('BS HR access has been added to Muskan. Her existing roles were preserved.');
                    });
                }}});
            }).appendTo(admin);
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
