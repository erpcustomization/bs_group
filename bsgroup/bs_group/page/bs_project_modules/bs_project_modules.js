frappe.pages['bs-project-modules'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('Project Modules'),single_column:true});
    const host = $('<div class="bspm">').appendTo(page.main);
    const modules = {supply:'BS Supply Projects',elv:'BS ELV Projects',infra:'BS Infra Projects','3cx':'BS 3CX Projects'};
    const sections = {dashboard:'Dashboard',projects:'Projects',amc:'AMC'};
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    let key='supply', section='dashboard', version=0;
    let selectedStatus='Not completed', searchText='', searchTimer;
    const filters=$('<div class="bspm-nav" style="align-items:center">').insertBefore(host);
    const search=$('<input type="search" class="form-control input-sm" aria-label="Search projects and AMC" placeholder="Search ID, project or customer" style="width:280px;max-width:100%">').appendTo(filters);
    const status=$('<select class="form-control input-sm" aria-label="Project status filter" style="width:200px">').appendTo(filters);
    for(const value of ['Not completed','All','Open','On hold','Completed','Cancelled']) $('<option>').val(value).text(value==='Not completed'?'Status: Not completed':value==='All'?'Status: All':value).appendTo(status);
    status.on('change',()=>{selectedStatus=status.val();render();});
    search.on('input search',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{searchText=search.val().trim();render();},350);});
    search.on('keydown',e=>{if(e.key==='Enter'){e.preventDefault();clearTimeout(searchTimer);searchText=search.val().trim();render();}});
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
        if (['tasks','timesheets','scheduler','expenses','advances','labor'].includes(section)) section='projects';
        if (!modules[key] || !sections[section]) {host.text(__('Choose a valid project module.'));return;}
        const current=++version;
        page.set_title(modules[key]);
        host.html('<p class="text-muted">Loading project module…</p>');
        const {message:data}=await frappe.call({method:'bsgroup.project_modules.overview',args:{module:key,section,status:selectedStatus,search:searchText}});
        if(current!==version)return;
        host.empty();
        const moduleNav=$('<nav class="bspm-nav" aria-label="Project modules">').appendTo(host);
        for(const [id,title] of Object.entries(modules)) $('<button type="button">').text(title).toggleClass('active',id===key).on('click',()=>navigate(id,'dashboard')).appendTo(moduleNav);
        const hero=$('<section class="bspm-hero">').appendTo(host);
        $('<h2>').text(data.title).appendTo(hero);
        $('<div class="bspm-note">').text('Open a project to manage its plan, tasks, timesheets, scheduler, expenses, advances and labour approvals from one screen.').appendTo(hero);
        const actions=$('<div class="bspm-actions">').appendTo(hero);
        if(data.can_create) $('<button class="btn btn-primary btn-sm">').text(__('New Project')).on('click',()=>frappe.new_doc('Project',{[data.field]:1})).appendTo(actions);
        $('<button class="btn btn-default btn-sm">').text(__('Choose Existing Project')).on('click',()=>frappe.set_route('List','Project')).appendTo(actions);
        const nav=$('<nav class="bspm-nav" aria-label="Module sections">').appendTo(host);
        for(const [id,title] of Object.entries(sections)) $('<button type="button">').text(title).toggleClass('active',id===section).on('click',()=>navigate(key,id)).appendTo(nav);
        if(section==='dashboard') {
            const stats=$('<div class="bspm-stats">').appendTo(host);
            const counts=[['Projects',data.projects.length],['AMC',data.amcs.length],['Open projects',data.projects.filter(p=>p.status==='Open').length],['Needs classification',data.unclassified.length]];
            for(const [label,value] of counts) $('<div class="bspm-stat">').html(`<span>${esc(label)}</span><strong>${value}</strong>`).appendTo(stats);
        }
        function draw(rows, amc=false) {
            const table=$('<div class="bspm-table">').appendTo(host);
            if(!rows.length) {table.html('<div class="bspm-empty">No matching accessible records.</div>');return;}
            table.html(`<table><thead><tr><th>${amc?'AMC / Maintenance':'Project'}</th><th>Customer</th><th>Status</th><th>${amc?'Contract start':'Start'}</th><th>${amc?'Renewal / End':'Expected end'}</th><th>Category</th></tr></thead><tbody>${rows.map(p=>`<tr><td><a href="/desk/project/${encodeURIComponent(p.name)}">${esc(p.project_name)}</a><div class="bspm-note">${esc(p.name)} · ${esc(p.company)}</div></td><td>${esc(p.customer||'—')}</td><td>${esc(p.status)}</td><td>${esc(p.expected_start_date||'—')}</td><td>${esc(p.expected_end_date||'—')}</td><td>${esc(p.categories.map(k=>modules[k]).join(', ')||'Unclassified')}<div class="bspm-note" style="${p.review_required?'color:#916000':''}">${esc(p.classification)}</div></td></tr>`).join('')}</tbody></table>`);
        }
        $('<p class="bspm-note">').text(section==='amc'?'AMC and maintenance contracts only. Projects appear in the Projects section.':'Projects only. AMC and maintenance contracts appear in the AMC section.').appendTo(host);
        draw(section==='amc'?data.amcs:data.projects,section==='amc');
        if(data.unclassified.length) {
            const review=$('<details class="bspm-hero" style="margin-top:18px">').appendTo(host);
            $('<summary>').text(`Needs classification — ${data.unclassified.length} ${section==='amc'?'AMC contracts':'projects'} across all categories`).appendTo(review);
            $('<p class="bspm-note">').text('These records have no saved category and no clear category in their title/type. An authorized project editor can open each record and select its categories in Details.').appendTo(review);
            $('<div>').html(data.unclassified.map(p=>`<p><a href="/desk/project/${encodeURIComponent(p.name)}">${esc(p.project_name)}</a> · ${esc(p.name)} · ${p.is_amc?'AMC':'Project'} · ${esc(p.status)}</p>`).join('')).appendTo(review);
        }

    }
    wrapper.bs_project_module_refresh=render;
};
frappe.pages['bs-project-modules'].on_page_show=wrapper=>wrapper.bs_project_module_refresh?.();
