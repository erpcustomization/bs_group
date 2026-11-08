frappe.pages['bs-project-modules'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('Project Modules'),single_column:true});
    const host = $('<div class="bspm">').appendTo(page.main);
    const modules = {supply:'BS Supply Projects',elv:'BS ELV Projects',infra:'BS Infra Projects','3cx':'BS 3CX Projects'};
    const sections = {dashboard:'Dashboard',projects:'Projects',tasks:'Tasks',timesheets:'Timesheets',scheduler:'Tech Task Scheduler',expenses:'Expenses',advances:'Advance',labor:'Labour Approval'};
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    let key='supply', section='dashboard', version=0;
    if (!document.getElementById('bspm-style')) $('<style id="bspm-style">').text(`
      .bspm{padding:16px 4px;color:var(--text-color,#193047)}.bspm-nav{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
      .bspm-nav button{border:1px solid #dce5ec;border-radius:8px;padding:8px 12px;background:var(--card-bg,#fff);font-size:12px}
      .bspm-nav button.active{background:#173957;color:#fff;border-color:#173957}.bspm-hero{padding:24px;border:1px solid #dce5ec;border-radius:14px;background:var(--card-bg,#fff);margin-bottom:16px}
      .bspm-hero h2{font-size:22px;margin:0 0 8px}.bspm-note{color:var(--text-muted,#687a8b);font-size:12px;line-height:1.7}
      .bspm-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.bspm-stat{border:1px solid #dce5ec;background:var(--card-bg,#fff);border-radius:12px;padding:16px}.bspm-stat strong{display:block;font-size:25px;color:#173957}
      .bspm-table{border:1px solid #dce5ec;border-radius:12px;overflow:auto;background:var(--card-bg,#fff)}.bspm-table table{width:100%;margin:0}.bspm-table th,.bspm-table td{padding:13px;border-bottom:1px solid #edf1f4;font-size:12px}.bspm-empty{padding:30px;text-align:center}.bspm-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
      @media(max-width:700px){.bspm-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
    `).appendTo(document.head);
    function navigate(module,view) {
        frappe.set_route('bs-project-modules',{bs_module:module,bs_section:view});
    }
    async function render() {
        const params = new URLSearchParams(location.search);
        const options = frappe.route_options || {};
        key = options.bs_module || params.get('bs_module') || key;
        section = options.bs_section || params.get('bs_section') || section;
        delete options.bs_module; delete options.bs_section;
        if (!modules[key] || !sections[section]) {host.text(__('Choose a valid project module.'));return;}
        const current=++version;
        page.set_title(modules[key]);
        host.html('<p class="text-muted">Loading project module…</p>');
        const {message:data}=await frappe.call({method:'bsgroup.project_modules.overview',args:{module:key,section}});
        if(current!==version)return;
        host.empty();
        const moduleNav=$('<nav class="bspm-nav" aria-label="Project modules">').appendTo(host);
        for(const [id,title] of Object.entries(modules)) $('<button type="button">').text(title).toggleClass('active',id===key).on('click',()=>navigate(id,'dashboard')).appendTo(moduleNav);
        const hero=$('<section class="bspm-hero">').appendTo(host);
        $('<h2>').text(data.title).appendTo(hero);
        $('<div class="bspm-note">').text('Projects can belong to more than one module. Your existing project templates, workflows and access apply.').appendTo(hero);
        const actions=$('<div class="bspm-actions">').appendTo(hero);
        if(data.can_create) $('<button class="btn btn-primary btn-sm">').text(__('New Project')).on('click',()=>frappe.new_doc('Project',{[data.field]:1})).appendTo(actions);
        $('<button class="btn btn-default btn-sm">').text(__('Choose Existing Project')).on('click',()=>frappe.set_route('List','Project')).appendTo(actions);
        const nav=$('<nav class="bspm-nav" aria-label="Module sections">').appendTo(host);
        for(const [id,title] of Object.entries(sections)) $('<button type="button">').text(title).toggleClass('active',id===section).on('click',()=>navigate(key,id)).appendTo(nav);
        if(section==='dashboard') {
            const stats=$('<div class="bspm-stats">').appendTo(host);
            const counts=[['Projects',data.projects.length],['Open',data.projects.filter(p=>p.status==='Open').length],['On hold',data.projects.filter(p=>p.status==='On hold').length],['Completed',data.projects.filter(p=>p.status==='Completed').length]];
            for(const [label,value] of counts) $('<div class="bspm-stat">').html(`<span>${esc(label)}</span><strong>${value}</strong>`).appendTo(stats);
        }
        const table=$('<div class="bspm-table">').appendTo(host);
        if(!data.projects.length) {
            table.html('<div class="bspm-empty"><strong>No projects assigned to this module yet.</strong><p class="bspm-note">Open an existing project, choose Project Modules, select the relevant modules and save. A single project can be selected in several modules.</p></div>');
        } else if(section==='dashboard'||section==='projects') {
            table.html(`<table><thead><tr><th>Project</th><th>Status</th><th>Project Type</th><th>Progress</th></tr></thead><tbody>${data.projects.map(p=>`<tr><td><a href="/desk/project/${encodeURIComponent(p.name)}">${esc(p.project_name)}</a><div class="bspm-note">${esc(p.name)} · ${esc(p.company)}</div></td><td>${esc(p.status)}</td><td>${esc(p.project_type)}</td><td>${Number(p.percent_complete||0).toFixed(0)}%</td></tr>`).join('')}</tbody></table>`);
        } else if(!data.available) {
            table.html('<div class="bspm-empty">This section is restricted by your existing access.</div>');
        } else {
            const route=data.doctype.toLowerCase().replaceAll(' ','-');
            table.html(data.rows.length ? `<table><thead><tr><th>Record</th><th>Details</th><th>Status</th><th>Updated</th></tr></thead><tbody>${data.rows.map(row=>`<tr><td><a href="/desk/${route}/${encodeURIComponent(row.name)}">${esc(row.name)}</a></td><td>${esc(row.subject||row.employee_name||row.task||row.project||row.custom_project||row.reference||'—')}</td><td>${esc(row.workflow_state||row.status||['Draft','Submitted','Cancelled'][row.docstatus])}</td><td>${esc(frappe.datetime.str_to_user(row.modified))}</td></tr>`).join('')}</tbody></table>` : '<div class="bspm-empty">No matching records to show.</div>');
            $('<p class="bspm-note">').text('Latest 100 accessible records linked to projects in this module. Open a project to create requests using its existing controls.').appendTo(host);
        }
    }
    wrapper.bs_project_module_refresh=render;
};
frappe.pages['bs-project-modules'].on_page_show=wrapper=>wrapper.bs_project_module_refresh?.();
