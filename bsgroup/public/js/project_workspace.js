(() => {
    const sections = {tasks:'Tasks', timesheets:'Timesheets', scheduler:'Tech Task Scheduler', expenses:'Expenses', advances:'Advance', labor:'Labour Approval'};
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    frappe.ui.form.on('Project', {
        before_load(frm) {
            // Register activity tabs before Frappe restores the URL's tab.
            groupActivityTabs(frm);
        },
        refresh(frm) {
            groupAdditionalDetails(frm);
            groupActivityTabs(frm);
            for (const tab of frm.layout.tabs || []) {
                if (['connections_tab', 'costing_tab'].includes(tab.df.fieldname)) tab.df.hidden = 1;
            }
            frm.layout.refresh_tabs();
            renderPlan(frm);
            const field = frm.fields_dict.custom_bs_project_workspace;
            if (!field) {
                if (frappe.user.has_role('System Manager')) frm.add_custom_button(__('Set Up Project Activities'), async () => {
                    await frappe.call({method:'bsgroup.project_workspace.setup',type:'POST',freeze:true});
                    frappe.msgprint(__('Project Activities is ready. Reload the page to use it.'));
                });
                return;
            }
            for (const title of ['Expenses','Advance','Labour Approval']) frm.remove_custom_button(__(title),__('Project Requests'));
            frm.remove_custom_button(__('Project Activities'));
        }
    });
    function groupActivityTabs(frm) {
        const layout = frm.layout;
        const original = layout.tabs.find(tab=>tab.df.fieldname==='custom_bs_project_activities');
        const plan = layout.tabs.find(tab=>tab.df.fieldname==='custom_bs_project_plan_tab');
        if (!original || !plan) return;
        const wasActive = original.is_active();
        frm.__bs_activity_tabs ||= {};
        let previous = plan;
        for (const [id, title] of Object.entries(sections)) {
            let tab = frm.__bs_activity_tabs[id];
            if (!tab || !layout.tabs.includes(tab)) {
                // Reuse native form tabs so routing, keyboard focus and active
                // state behave exactly like Details and Project Plan.
                tab = new original.constructor(layout, {
                    fieldname:'custom_bs_activity_'+id, fieldtype:'Tab Break',
                    label:title, permlevel:original.df.permlevel || 0
                }, frm, layout.tab_link_container, layout.tabs_content);
                layout.tabs.push(tab);
                const section = $('<div class="form-section" style="padding:20px">').appendTo(tab.wrapper);
                // Native refresh hides sections without a visible control.
                tab.activity_host = $('<div class="frappe-control" data-fieldtype="HTML">').appendTo(section);
                const activate = tab.set_active.bind(tab);
                tab.set_active = () => {
                    activate();
                    if (tab.activity_project !== frm.doc.name) render(frm,id);
                };
                frm.__bs_activity_tabs[id] = tab;
            }
            tab.activity_project = null;
            tab.tab_link.insertAfter(previous.tab_link);
            tab.wrapper.insertAfter(previous.wrapper);
            previous = tab;
        }
        // Keep the stored legacy fields for compatibility; their wrapper is
        // replaced by the six project-scoped tabs without changing records.
        original.df.hidden = 1;
        layout.tab_link_container.css('flex-wrap','wrap');
        if (wasActive || window.location.hash==='#custom_bs_project_activities') {
            frm.__bs_activity_tabs[frm.__bs_activity || 'tasks'].set_active();
        }
    }
    function groupAdditionalDetails(frm) {
        const tabs = frm.layout.tabs || [];
        const additional = tabs.find(tab=>tab.df.fieldname==='monitor_progress_tab');
        const boq = tabs.find(tab=>tab.df.fieldname==='custom_boq_tab');
        if (!additional || !boq) return;
        const wasBoqActive = boq.is_active();
        additional.label = additional.df.label = __('Additional Details');
        additional.tab_link.find('.nav-link').text(additional.label);
        if (!additional.wrapper.children('.bs-additional-progress-heading').length) {
            $('<h4 class="bs-additional-progress-heading" style="margin:20px 20px 8px">').text(__('Progress')).prependTo(additional.wrapper);
        }
        // Move the existing controls, keeping their values, editors, validation
        // and event handlers intact. Repeating refresh never copies a control.
        if (boq.wrapper.children().length) {
            if (!additional.wrapper.children('.bs-additional-boq-heading').length) {
                $('<h4 class="bs-additional-boq-heading" style="margin:24px 20px 8px">').text(__('BOQ')).appendTo(additional.wrapper);
            }
            boq.wrapper.children().appendTo(additional.wrapper);
        }
        for (const field of Object.values(frm.fields_dict)) {
            if (field.tab===boq) additional.add_field(field);
        }
        boq.df.hidden = 1;
        if (wasBoqActive) additional.set_active();
    }
    async function renderPlan(frm) {
        if (frm.__bs_plan_dirty?.size && frm.__bs_plan_project===frm.doc.name) return;
        frm.__bs_plan_project=frm.doc.name;
        frm.__bs_plan_dirty=new Set();
        const field = frm.fields_dict.custom_bs_project_plan;
        if (!field) {
            if (frappe.user.has_role('System Manager')) frm.add_custom_button(__('Set Up Project Plan'), async () => {
                await frappe.call({method:'bsgroup.project_plan.setup',type:'POST',freeze:true});
                frappe.msgprint(__('Project Plan is ready. Reload the page to use it.'));
            });
            return;
        }
        const host = field.$wrapper;
        if (frm.is_new()) {host.text(__('Save this project to generate its plan from tasks and template activities.')); return;}
        const project = frm.doc.name;
        const version = frm.__bs_plan_version = (frm.__bs_plan_version || 0) + 1;
        host.text(__('Loading project plan…'));
        let data;
        try {
            ({message:data} = await frappe.call({method:'bsgroup.project_plan.get_plan',args:{project}}));
        } catch (error) {
            if (version===frm.__bs_plan_version) host.text(__('Could not load the plan. Check your access and refresh the project.'));
            return;
        }
        if (version!==frm.__bs_plan_version || frm.doc.name!==project) return;
        host.empty();
        $('<h4>').text(__('Project Plan')+' · '+(data.project_name || project)).appendTo(host);
        $('<p class="text-muted">').text(__('Automatically shows this project’s tasks and template activities. Edits update the same tasks; assigned tasks appear in each selected user’s task list.')).appendTo(host);
        const actions = $('<div style="display:flex;gap:8px;margin:12px 0">').appendTo(host);
        $('<button type="button" class="btn btn-default btn-sm">').text(__('Refresh Plan')).on('click',()=>{
            if (frm.__bs_plan_dirty.size) return frappe.msgprint(__('Save or discard the edited rows before refreshing.'));
            renderPlan(frm);
        }).appendTo(actions);
        if (!data.work_updates_ready && frappe.user.has_role('System Manager')) $('<button type="button" class="btn btn-primary btn-sm">').text(__('Enable Task Work Updates')).on('click',async()=>{
            await frappe.call({method:'bsgroup.project_plan.setup',type:'POST',freeze:true}); renderPlan(frm);
        }).appendTo(actions);
        if (data.can_create) $('<button type="button" class="btn btn-primary btn-sm">').text(__('Add Activity')).on('click',()=>{
            openProjectRecord(frm,{doctype:'Task',defaults:{project,company:data.company}},null,()=>renderPlan(frm));
        }).appendTo(actions);
        if (!data.can_read_tasks) {$('<p>').text(__('Your current access does not allow viewing project tasks.')).appendTo(host); return;}
        const table = $('<div class="table-responsive">').html('<table class="table table-bordered"><thead><tr><th>Activity</th><th>Description</th><th>Start Date</th><th>End Date</th><th>Assigned To</th><th>Today’s Work</th><th>Status</th><th>Save</th></tr></thead><tbody></tbody></table>').appendTo(host).find('tbody');
        for (const row of data.rows) drawPlanRow(frm,project,row,data,$('<tr>').appendTo(table));
        if (!data.rows.length) $('<tr><td colspan="8"></td></tr>').find('td').text(__('No activities yet. Add an activity or save this project with a Project Template to generate its tasks.')).end().appendTo(table);
    }
    function drawPlanRow(frm,project,row,data,tr) {
        tr.empty();
        let description=row.description || '', selected=[...row.assigned_to], names={...data.user_names}, busy=false;
        const dirty=()=>{frm.__bs_plan_dirty.add(row.name);save.prop('disabled',false).text(__('Save changes'));};
        const cell=()=> $('<td style="vertical-align:top;min-width:130px">').appendTo(tr);
        const input=(parent,label,value,type='text')=>$('<input class="form-control input-sm">').attr({type,'aria-label':label+' '+row.name}).val(value || '').prop('disabled',!row.can_edit).on('input change',dirty).appendTo(parent);
        const titleCell=cell(), subject=input(titleCell,__('Activity'),row.subject);
        $('<div class="text-muted small">').text(row.name).appendTo(titleCell);
        $('<button type="button" class="btn btn-link btn-xs">').text(__('Open task form')).on('click',()=>{
            if(frm.__bs_plan_dirty.size) return frappe.msgprint(__('Save or discard the edited rows before opening the task form.'));
            openProjectRecord(frm,{doctype:'Task'},row.name,()=>renderPlan(frm));
        }).appendTo(titleCell);
        const descriptionCell=cell();
        const preview=$('<div style="white-space:pre-wrap;max-width:250px;max-height:100px;overflow:auto">').text(row.description_text || '—').appendTo(descriptionCell);
        $('<button type="button" class="btn btn-default btn-xs">').text(__('Edit description')).prop('disabled',!row.can_edit).on('click',()=>{
            const d=new frappe.ui.Dialog({title:__('Activity Description'),size:'large',fields:[{fieldname:'description',fieldtype:'Text Editor',label:__('Description'),default:description}],primary_action_label:__('Use description'),primary_action(v){description=v.description || '';preview.text(new DOMParser().parseFromString(description,'text/html').body.textContent || '—');dirty();d.hide();}});d.show();
        }).appendTo(descriptionCell);
        const start=input(cell(),__('Start Date'),row.exp_start_date,'date'), end=input(cell(),__('End Date'),row.exp_end_date,'date');
        const assigned=cell();
        const label=$('<div>').text(selected.map(u=>names[u] || u).join(', ') || __('Unassigned')).appendTo(assigned);
        $('<button type="button" class="btn btn-default btn-xs">').text(__('Choose users')).prop('disabled',!row.can_edit).on('click',async()=>{
            const {message:choices}=await frappe.call({method:'bsgroup.project_plan.assignment_choices',args:{project,task:row.name}});
            for(const u of selected) if(!choices.some(o=>o.value===u)) choices.push({value:u,label:names[u] || u,description:u});
            for(const o of choices) {names[o.value]=o.label;o.label=esc(o.label);o.description=esc(o.description);}
            const d=new frappe.ui.Dialog({title:__('Assign Activity'),fields:[{fieldname:'users',fieldtype:'MultiSelectList',label:__('Assigned To'),get_data:txt=>choices.filter(o=>(o.label+' '+o.value).toLowerCase().includes((txt||'').toLowerCase()))}],primary_action_label:__('Use selection'),primary_action(v){selected=v.users || [];label.text(selected.map(u=>names[u] || u).join(', ') || __('Unassigned'));dirty();d.hide();}});
            d.show();await d.fields_dict.users.set_options();d.fields_dict.users.set_value(selected);
        }).appendTo(assigned);
        const work=cell();
        $('<button type="button" class="btn btn-default btn-sm">').text(__('Enter today’s task')).attr('title',row.can_log_work?'':__('Only assigned users can record work.')).prop('disabled',!row.can_log_work).on('click',()=>showWork(frm,project,row,true)).appendTo(work);
        $('<button type="button" class="btn btn-link btn-sm">').text(__('View work history')).on('click',()=>showWork(frm,project,row,false)).appendTo(work);
        const statusCell=cell(), status=$('<select class="form-control input-sm">').attr('aria-label',__('Status')+' '+row.name).prop('disabled',!row.can_change_status || !data.work_updates_ready).appendTo(statusCell);
        const options=[...data.status_options]; if(!options.includes(row.status)) options.unshift(row.status);
        for(const value of options) $('<option>').val(value).text(__(value)).appendTo(status);
        status.val(row.status);
        if(row.overdue) $('<div class="text-warning small">').text(__('Past end date')).appendTo(statusCell);
        $('<button type="button" class="btn btn-default btn-xs">').text(__('Save status')).prop('disabled',!row.can_change_status || !data.work_updates_ready).on('click',async()=>{
            if(status.val()===row.status) return;
            if(frm.__bs_plan_dirty.has(row.name)) return frappe.msgprint(__('Save the row changes before updating its status.'));
            await perform(async()=>{await frappe.call({method:'bsgroup.project_plan.set_task_status',type:'POST',args:{project,task:row.name,status:status.val(),expected_modified:row.modified}});});
        }).appendTo(statusCell);
        const saveCell=cell();
        const save=$('<button type="button" class="btn btn-primary btn-sm">').text(__('Saved')).prop('disabled',true).on('click',async()=>{
            await perform(async()=>{await frappe.call({method:'bsgroup.project_plan.save_task',type:'POST',args:{project,task:row.name,subject:subject.val(),description,start_date:start.val(),end_date:end.val(),assigned_to:selected,expected_modified:row.modified,expected_assignees:row.assigned_to}});});
        }).appendTo(saveCell);
        $('<button type="button" class="btn btn-link btn-xs">').text(__('Discard changes')).prop('disabled',!row.can_edit).on('click',()=>{frm.__bs_plan_dirty.delete(row.name);drawPlanRow(frm,project,row,data,tr);}).appendTo(saveCell);
        async function perform(action) {
            if(busy) return;busy=true;
            const buttons=tr.find('button').toArray().map(button=>[button,button.disabled]);
            tr.find('button').prop('disabled',true);
            try {
                await action();frm.__bs_plan_dirty.delete(row.name);
                if(frm.doc.name===project && !frm.__bs_plan_dirty.size && !frm.is_dirty()) {
                    await frm.reload_doc();
                    frappe.show_alert({message:__('Task saved'),indicator:'green'});
                    return;
                }
                const {message:fresh}=await frappe.call({method:'bsgroup.project_plan.get_plan',args:{project}});
                if(frm.doc.name!==project) return;
                const updated=fresh.rows.find(r=>r.name===row.name);
                if(updated) drawPlanRow(frm,project,updated,fresh,tr);else tr.remove();
                if(frm.__bs_activity_tabs?.tasks) frm.__bs_activity_tabs.tasks.activity_project=null;
                frappe.show_alert({message:__('Task saved'),indicator:'green'});
            } catch(error) {for(const [button,disabled] of buttons) button.disabled=disabled;}
            finally {busy=false;}
        }
    }
    async function showWork(frm,project,row,entry) {
        const d=new frappe.ui.Dialog({title:entry?__('Enter today’s task'):__('Task Work History'),size:'large',fields:[
            {fieldname:'activity',fieldtype:'HTML',options:'<p><strong>'+esc(row.subject)+'</strong><br>'+esc(row.name)+'</p>'},
            ...(entry?[{fieldname:'work',fieldtype:'Small Text',label:__('Work completed today'),reqd:1}]:[]),
            {fieldname:'history',fieldtype:'HTML'}],
            primary_action_label:entry?__('Save work'):__('Close'),async primary_action(values){
                if(!entry) {d.hide();return;}
                if(d.__saving)return;d.__saving=true;d.get_primary_btn().prop('disabled',true);
                try {await frappe.call({method:'bsgroup.project_plan.save_work',type:'POST',args:{project,task:row.name,work:values.work}});d.hide();frappe.show_alert({message:__('Today’s work saved'),indicator:'green'});}
                finally {d.__saving=false;d.get_primary_btn().prop('disabled',false);}
            }});
        d.show();d.fields_dict.history.$wrapper.text(__('Loading work history…'));
        const {message:history}=await frappe.call({method:'bsgroup.project_plan.work_history',args:{project,task:row.name}});
        const host=d.fields_dict.history.$wrapper.empty();
        $('<h5>').text(__('Recent work updates')).appendTo(host);
        for(const log of history) {$('<p class="text-muted small">').text((log.comment_by || log.comment_email)+' · '+frappe.datetime.str_to_user(log.creation)).appendTo(host);$('<p style="white-space:pre-wrap">').text(log.text).appendTo(host);}
        if(!history.length) $('<p>').text(__('No work updates recorded yet.')).appendTo(host);
    }
    async function render(frm, section) {
        frm.__bs_activity = section;
        const tab = frm.__bs_activity_tabs?.[section];
        if (!tab) return;
        const version = tab.activity_version = (tab.activity_version || 0) + 1;
        const project = frm.doc.name;
        tab.activity_project = project;
        const host = tab.activity_host;
        host.empty();
        if (frm.is_new()) {host.text(__('Save this project to use its activities.')); return;}
        $('<h4>').text(__(sections[section])+' · '+(frm.doc.project_name || project)).appendTo(host);
        $('<p class="text-muted">').text(__('Activities for this project only') + ' · ' + project).appendTo(host);
        const panel = $('<section aria-live="polite">').text(__('Loading…')).appendTo(host);
        let data;
        try {
            ({message:data} = await frappe.call({method:'bsgroup.project_workspace.context',args:{project,section}}));
        } catch (error) {
            if (version===tab.activity_version) panel.text(__('Could not load this project activity. Check your access and try again.'));
            return;
        }
        if (version!==tab.activity_version || frm.doc.name!==project) return;
        panel.empty();
        if (data.problem) $('<p class="text-muted">').text(data.problem).appendTo(panel);
        const actions = $('<div style="display:flex;gap:8px;margin-bottom:12px">').appendTo(panel);
        if (data.can_create) $('<button type="button" class="btn btn-primary btn-sm">').text(__('New')+' '+__(data.doctype)).on('click',()=>{
            openProjectRecord(frm,data,null,()=>render(frm,section));
        }).appendTo(actions);
        $('<button type="button" class="btn btn-default btn-sm">').text(__('Refresh')).on('click',()=>render(frm,section)).appendTo(actions);
        if (!data.available) {$('<p>').text(__('This activity is restricted by your existing access.')).appendTo(panel); return;}

        const records=$('<div class="table-responsive">').html(`<table class="table table-bordered"><thead><tr><th>Record</th><th>Details</th><th>Status</th></tr></thead><tbody>${data.rows.map(row=>
            `<tr><td><button type="button" class="btn btn-link btn-xs" data-record="${esc(row.name)}">${esc(row.name)}</button></td><td>${esc(row.subject||row.employee_name||row.task||'—')}</td><td>${esc(row.workflow_state||row.status||['Draft','Submitted','Cancelled'][row.docstatus])}</td></tr>`
        ).join('') || '<tr><td colspan="3">No records for this project.</td></tr>'}</tbody></table>`).appendTo(panel);
        records.on('click','button[data-record]',e=>openProjectRecord(frm,data,e.currentTarget.dataset.record,()=>render(frm,section)));
        $('<p class="text-muted">').text(__('Showing up to 100 accessible records linked to this project.')).appendTo(panel);
    }
    function openProjectRecord(frm,data,name,afterClose) {
        if(frm.__bs_plan_dirty?.size) return frappe.msgprint(__('Save or discard the edited plan rows before opening another form.'));
        const project=frm.doc.name;
        const d=new frappe.ui.Dialog({title:(name || __('New')+' '+__(data.doctype))+' · '+project,size:'extra-large',fields:[{fieldname:'form',fieldtype:'HTML'}]});
        const host=d.fields_dict.form.$wrapper;
        const loading=$('<p>').text(__('Loading form…')).appendTo(host);
        const iframe=$('<iframe title="Project record editor" style="width:100%;height:76vh;border:0;visibility:hidden">').appendTo(host);
        let timer,closing=false,initialized=false;
        iframe.on('load',()=>{
            const win=iframe[0].contentWindow;
            let attempts=0;
            clearInterval(timer);
            timer=setInterval(()=>{
                const f=win.frappe;
                if(!f?.boot?.user || !f?.model?.with_doctype || !f?.set_route) {
                    if(++attempts>120) {clearInterval(timer);loading.text(__('The form could not load. Close this popup and try again.'));}
                    return;
                }
                clearInterval(timer);
                if(initialized)return;initialized=true;
                const style=win.document.createElement('style');
                style.textContent='#desk-dock,.body-sidebar,.workspace-sidebar,.navbar{display:none!important}.body-sidebar-container{display:none!important}.main-section{margin-left:0!important}.layout-main-section-wrapper{margin-left:0!important}.page-container{padding-left:12px!important;padding-right:12px!important}';
                win.document.head.appendChild(style);
                f.after_ajax(()=>f.model.with_doctype(data.doctype,()=>{
                    if(name) f.set_route('Form',data.doctype,name);
                    else {
                        const doc=f.model.get_new_doc(data.doctype);
                        Object.assign(doc,data.defaults);doc.__bs_project_request=project;
                        if(data.child) Object.assign(f.model.add_child(doc,data.child.field),data.child.values);
                        f.set_route('Form',data.doctype,doc.name);
                    }
                    loading.remove();iframe.css('visibility','visible');
                }));
            },100);
        });
        d.$wrapper.on('hide.bs.modal',event=>{
            const win=iframe[0].contentWindow;
            if(!closing && win?.cur_frm?.is_dirty()) {
                event.preventDefault();
                frappe.confirm(__('This form has unsaved changes. Discard them and close?'),()=>{closing=true;d.hide();});
            }
        });
        d.$wrapper.on('hidden.bs.modal',()=>{
            clearInterval(timer);iframe.remove();
            if(frm.doc.name===project) {
                if(!frm.is_dirty() && !frm.__bs_plan_dirty?.size) frm.reload_doc();
                else afterClose();
            }
        });
        d.show();iframe.attr('src','/desk');
    }
})();
