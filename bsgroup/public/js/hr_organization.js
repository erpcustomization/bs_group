/* Editable organization flow. All employee changes use the native HR permission boundary. */
window.bsHROrganization = async function (main) {
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    const panel = $('<section class="hrm-panel org-flow-panel">').appendTo(main);
    const styleId = 'bs-org-flow-style';
    if (!document.getElementById(styleId)) $('<style>').attr('id', styleId).text(`
      .org-tools{padding:16px 20px;display:flex;gap:9px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #e5edf1}
      .org-tools input{min-width:180px;max-width:240px}.org-tools select{max-width:260px}.org-summary{padding:14px 20px;display:flex;gap:18px;flex-wrap:wrap;color:#647789;font-size:12px}.org-summary b{color:#18384b;font-size:16px;margin-right:5px}
      .org-canvas{overflow:auto;max-height:720px;padding:28px 22px;background-color:#f9fbfd;background-image:radial-gradient(#dce5eb .7px,transparent .7px);background-size:18px 18px;min-height:200px}
      .org-forest,.org-branch{list-style:none!important;margin:0!important;padding:0!important;display:flex;flex-direction:row;align-items:flex-start;gap:0;width:max-content}
      .org-forest{gap:32px}.org-node{display:flex;flex-direction:column;align-items:center;position:relative;padding:0 12px!important;margin:0!important}
      .org-branch{padding-top:36px!important;position:relative}.org-branch:before{content:'';position:absolute;left:50%;top:0;height:18px;border-left:1.5px solid #99b5c6}
      .org-branch>.org-node:before{content:'';position:absolute;left:0;right:0;top:-18px;border-top:1.5px solid #99b5c6}
      .org-branch>.org-node:first-child:before{left:50%}.org-branch>.org-node:last-child:before{right:50%}.org-branch>.org-node:only-child:before{display:none}
      .org-branch>.org-node:after{content:'';position:absolute;left:50%;top:-18px;height:18px;border-left:1.5px solid #99b5c6}
      .org-card{width:224px;min-height:190px;flex:0 0 auto;background:#fff;border:1px solid #d9e5ec;border-top:3px solid #16887e;border-radius:12px;padding:14px;box-shadow:0 3px 12px #18384b08;position:relative;text-align:left}
      .org-card.org-leader{border-top-color:#234a6c;background:#f2f7fc}.org-card.org-match{outline:3px solid #efc36c;outline-offset:2px}.org-card-header{display:flex;gap:10px;align-items:center}.org-initials{width:33px;height:33px;flex-shrink:0;display:grid;place-items:center;border-radius:10px;background:#e8f3f1;color:#186c65;font-size:12px;font-weight:700}
      .org-card a{font-size:13px;font-weight:650;color:#173b56;line-height:1.35}.org-role{font-size:11px;color:#63788a;margin:9px 0 6px;line-height:1.5}.org-team{font-size:10px;display:inline-block;border-radius:5px;padding:3px 6px;background:#edf3f7;color:#4c667a}.org-controls{display:flex;align-items:center;gap:8px;margin-top:10px;padding-top:9px;border-top:1px solid #edf2f5;flex-wrap:wrap}.org-controls button{font-size:11px!important;padding:3px 7px!important}.org-note{font-size:11px;color:#8b691f;margin-top:7px}.org-footer{padding:14px 20px;border-top:1px solid #e5edf1;font-size:11px;color:#718493}.org-team-links{display:flex;flex-wrap:wrap;gap:7px;padding:0 20px 14px}.org-team-links a{font-size:11px;color:#476278;background:#eff4f7;padding:5px 9px;border-radius:6px}.org-empty{padding:24px;color:#6d8091}
    `).appendTo(document.head);
    let state, search='', focus='', collapsed=new Set(), firstLoad=true, zoom=100;
    async function edit(person, remove=false) {
        const r=await frappe.call({method:'bsgroup.hr_org.employee_details',args:{employee:person.name}});
        const d=r.message;
        if(remove) {
            frappe.confirm(`Remove ${esc(d.employee_name)}’s reporting line? They will remain an active employee, with their team and attendance history preserved. Their own direct reports will remain attached.`, async()=>{
                await frappe.call({method:'bsgroup.hr_org.save_employee',type:'POST',freeze:true,args:{employee:d.name,modified:d.modified,values:{reports_to:null}}});
                frappe.show_alert({message:'Reporting line removed',indicator:'green'});await load();
            });
            return;
        }
        const dialog=new frappe.ui.Dialog({title:'Edit employee & team',fields:[
            {fieldtype:'HTML',options:`<p class="text-muted">${esc(d.employee_name)} · ${esc(d.company)}<br>Saving updates the official HR employee profile.</p>`},
            {fieldname:'first_name',label:'First name',fieldtype:'Data',reqd:1,default:d.first_name},
            {fieldname:'middle_name',label:'Middle name',fieldtype:'Data',default:d.middle_name},
            {fieldname:'last_name',label:'Last name',fieldtype:'Data',default:d.last_name},
            {fieldname:'designation',label:'Role / designation',fieldtype:'Link',options:'Designation',default:d.designation},
            {fieldname:'department',label:'Team / department',fieldtype:'Link',options:'Department',default:d.department,get_query:()=>({filters:{company:d.company,disabled:0}})},
            {fieldname:'reports_to',label:'Reports to',fieldtype:'Link',options:'Employee',default:d.reports_to,get_query:()=>({filters:{status:'Active',name:['!=',d.name]}})}
        ],primary_action_label:'Save HR profile',primary_action:async values=>{
            const changed={};Object.keys(values).forEach(k=>{if((values[k]||'')!==(d[k]||''))changed[k]=values[k]||null;});
            if(!Object.keys(changed).length){dialog.hide();return;}
            dialog.get_primary_btn().prop('disabled',true);
            try {await frappe.call({method:'bsgroup.hr_org.save_employee',type:'POST',freeze:true,args:{employee:d.name,values:changed,modified:d.modified}});dialog.hide();frappe.show_alert({message:'HR profile updated',indicator:'green'});await load();}
            finally{dialog.get_primary_btn().prop('disabled',false);}
        }});
        dialog.show();
    }
    function draw() {
        if(!panel[0].isConnected)return;
        panel.empty();
        const employees=state.employees||[], byId=new Map(employees.map(e=>[e.name,e])), children=new Map();
        employees.forEach(e=>{if(e.reports_to&&byId.has(e.reports_to)){if(!children.has(e.reports_to))children.set(e.reports_to,[]);children.get(e.reports_to).push(e);}});
        if(firstLoad){employees.filter(e=>e.reports_to&&children.has(e.name)).forEach(e=>collapsed.add(e.name));firstLoad=false;}
        const tools=$('<div class="org-tools">').appendTo(panel);
        const input=$('<input type="search" class="form-control input-sm" aria-label="Find employee or team" placeholder="Find employee or team">').val(search).appendTo(tools);
        const select=$('<select class="form-control input-sm" aria-label="Focus on a manager">').append($('<option value="">').text('Whole organization')).appendTo(tools);
        employees.filter(e=>children.has(e.name)).forEach(e=>$('<option>').val(e.name).text(e.employee_name).appendTo(select));select.val(focus);
        select.on('change',()=>{focus=select.val();if(focus)collapsed.delete(focus);draw();});
        $('<button class="btn btn-default btn-sm">').text('Expand all').on('click',()=>{collapsed.clear();draw();}).appendTo(tools);
        $('<button class="btn btn-default btn-sm">').text('Collapse teams').on('click',()=>{employees.filter(e=>e.reports_to).forEach(e=>collapsed.add(e.name));draw();}).appendTo(tools);
        if(state.can_create)$('<button class="btn btn-primary btn-sm">').text('Add employee').on('click',()=>frappe.new_doc('Employee',focus?{reports_to:focus}:{})).appendTo(tools);
        if(state.can_create_team)$('<button class="btn btn-default btn-sm">').text('Add team').on('click',()=>frappe.new_doc('Department')).appendTo(tools);
        const teams=[...new Set(employees.map(e=>e.department).filter(Boolean))].sort();
        $('<div class="org-summary">').html(`<span><b>${employees.length}</b>Active employees</span><span><b>${teams.length}</b>Teams</span><span><b>${children.size}</b>Managers</span><span>Teams arranged horizontally · scroll across to explore</span>`).appendTo(panel);
        if(state.can_read_teams){const links=$('<div class="org-team-links" aria-label="Team details">').appendTo(panel);teams.forEach(t=>$('<a>').attr('href','/desk/department/'+encodeURIComponent(t)).text(t).appendTo(links));}
        const canvas=$('<div class="org-canvas" role="region" aria-label="Organization flow diagram" tabindex="0">').appendTo(panel);
        const tree=$('<ul class="org-forest" aria-label="Employee reporting flow">').appendTo(canvas);
        const shown=new Set();
        function node(e,parent,review=false){
            if(shown.has(e.name))return;shown.add(e.name);
            const reports=children.get(e.name)||[], li=$('<li class="org-node">').appendTo(parent);
            const card=$('<article class="org-card">').toggleClass('org-leader',reports.length>0).attr('aria-label',e.employee_name).appendTo(li);
            const h=$('<div class="org-card-header">').appendTo(card);
            $('<span class="org-initials" aria-hidden="true">').text((e.employee_name||e.name).split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase()).appendTo(h);
            $('<a>').attr('href','/desk/employee/'+encodeURIComponent(e.name)).text(e.employee_name||e.name).appendTo(h);
            $('<div class="org-role">').text(e.designation||'Role not recorded').appendTo(card);
            $('<span class="org-team">').text(e.department||'Team not assigned').appendTo(card);
            if(review||e.manager_outside_view)$('<div class="org-note">').text(review?'Reporting line needs HR review':'Manager outside this view').appendTo(card);
            const controls=$('<div class="org-controls">').appendTo(card);
            if(e.can_edit){$('<button class="btn btn-default btn-xs">').attr('aria-label','Edit '+e.employee_name).text('Edit').on('click',()=>edit(e)).appendTo(controls);
                if(e.reports_to)$('<button class="btn btn-default btn-xs">').attr('aria-label','Remove reporting line for '+e.employee_name).text('Remove line').on('click',()=>edit(e,true)).appendTo(controls);}
            if(reports.length){const shut=collapsed.has(e.name);$('<button class="btn btn-default btn-xs">').attr({'aria-label':`${shut?'Expand':'Collapse'} team of ${e.employee_name}`,'aria-expanded':!shut}).text(`${shut?'+':'−'} ${reports.length} reports`).on('click',()=>{shut?collapsed.delete(e.name):collapsed.add(e.name);draw();}).appendTo(controls);
                if(!shut){const sub=$('<ul class="org-branch">').appendTo(li);reports.forEach(x=>node(x,sub));}
                else{const mark=id=>{if(shown.has(id))return;shown.add(id);(children.get(id)||[]).forEach(x=>mark(x.name));};reports.forEach(x=>mark(x.name));}}
        }
        if(focus&&byId.has(focus))node(byId.get(focus),tree);
        else {employees.filter(e=>!e.reports_to).sort((a,b)=>(children.get(b.name)?.length||0)-(children.get(a.name)?.length||0)).forEach(e=>node(e,tree));employees.filter(e=>!shown.has(e.name)).forEach(e=>node(e,tree,true));}
        if(!employees.length)$('<p class="org-empty">').text('No active employees are available in your view.').appendTo(canvas);
        function highlight(){const term=search.toLowerCase().trim();tree.find('.org-card').each(function(){$(this).toggleClass('org-match',!!term&&$(this).text().toLowerCase().includes(term));});}
        input.on('input',()=>{search=input.val();if(search){collapsed.clear();focus='';const pos=input[0].selectionStart;draw();const replacement=panel.find('input[type="search"]');replacement.trigger('focus');replacement[0].setSelectionRange(pos,pos);}else highlight();});highlight();
        const foot=$('<div class="org-footer">').text('Edit updates HR names, roles, teams and reporting lines. Remove line keeps the employee and their history. Select a team above to edit its details. ').appendTo(panel);
        const zoomBox=$('<span class="hrm-actions" style="margin-top:10px">').appendTo(foot);
        const applyZoom=()=>tree.css('zoom',zoom/100);applyZoom();
        [['−',-10],['+',10]].forEach(([label,delta])=>$('<button class="btn btn-default btn-xs">').attr('aria-label',delta<0?'Zoom out':'Zoom in').text(label).on('click',()=>{zoom=Math.max(50,Math.min(130,zoom+delta));applyZoom();}).appendTo(zoomBox));
        $('<button class="btn btn-default btn-xs">').text('Reset zoom').on('click',()=>{zoom=100;applyZoom();}).appendTo(zoomBox);
        if(search)tree.find('.org-match').first()[0]?.scrollIntoView({block:'nearest',inline:'nearest'});
        else requestAnimationFrame(()=>{
            const leader=tree.find('.org-card')[0];
            if(leader&&panel[0].isConnected){const c=canvas[0],r=leader.getBoundingClientRect();c.scrollLeft+=r.left+r.width/2-c.getBoundingClientRect().left-c.clientWidth/2;}
        });
    }
    async function load(){
        try{const r=await frappe.call({method:'bsgroup.hr_management.organization'});state=r.message;draw();}
        catch(e){if(panel[0].isConnected)panel.html('<div class="org-empty">Could not load the organization flow. Refresh to try again.</div>');}
    }
    panel.html('<div class="org-empty">Loading organization flow…</div>');await load();
};
