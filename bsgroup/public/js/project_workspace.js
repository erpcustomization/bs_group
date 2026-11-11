(() => {
    const sections = {tasks:'Tasks', timesheets:'Timesheets', scheduler:'Tech Task Scheduler', expenses:'Expenses', advances:'Advance', labor:'Labour Approval'};
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    const pendingSaves = new Set();
    window.addEventListener('beforeunload', event => {
        if (pendingSaves.size) { event.preventDefault(); event.returnValue = ''; }
    });
    // One request per row at a time. Acknowledging an older edit must never
    // remove a newer edit made while its request was in flight.
    function planAutosave(initial, send, notify, acknowledge) {
        let base=initial, sequence=0, busy=false, timer=null, failed=false;
        const pending=new Map();
        const state=()=>notify({busy,failed,pending:pending.size>0});
        async function flush() {
            clearTimeout(timer);timer=null;
            if(busy || !pending.size) return;
            busy=true;failed=false;state();
            while(pending.size) {
                const batch=new Map(pending);
                try {
                    const receipt=await send(Object.fromEntries([...batch].map(([key,edit])=>[key,edit.value])),base);
                    base=receipt.row;
                    for(const [key,edit] of batch) if(pending.get(key)===edit) pending.delete(key);
                    acknowledge(receipt,new Set(pending.keys()));
                } catch(error) {failed=true;break;}
            }
            busy=false;state();
        }
        return {
            edit(key,value,delay=0) {
                const field={start_date:'exp_start_date',end_date:'exp_end_date'}[key] || key;
                const equal=key==='assigned_to'
                    ? JSON.stringify([...(base[field] || [])].sort())===JSON.stringify([...value].sort())
                    : String(base[field] || '')===String(value || '');
                if(!busy && equal){pending.delete(key);failed=false;state();return;}
                pending.set(key,{value,sequence:++sequence});failed=false;
                clearTimeout(timer);state();
                timer=setTimeout(flush,delay);
            },
            flush,
            busy:()=>busy,
            hasPending:()=>pending.size>0,
            dispose(){clearTimeout(timer);pending.clear();failed=false;state();},
        };
    }
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
        const host = field.$wrapper.addClass('bs-project-plan');
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
            if (frm.__bs_plan_dirty.size) return frappe.msgprint(__('Wait for automatic saving to finish. Resolve any row showing a save error before refreshing.'));
            renderPlan(frm);
        }).appendTo(actions);
        if (!data.work_updates_ready && frappe.user.has_role('System Manager')) $('<button type="button" class="btn btn-primary btn-sm">').text(__('Enable Task Work Updates')).on('click',async()=>{
            await frappe.call({method:'bsgroup.project_plan.setup',type:'POST',freeze:true}); renderPlan(frm);
        }).appendTo(actions);
        if (data.can_create) $('<button type="button" class="btn btn-primary btn-sm">').text(__('Add Activity')).on('click',()=>{
            openProjectRecord(frm,{doctype:'Task',defaults:{project,company:data.company}},null,()=>renderPlan(frm));
        }).appendTo(actions);
        if (!data.can_read_tasks) {$('<p>').text(__('Your current access does not allow viewing project tasks.')).appendTo(host); return;}
        const table = $('<div class="table-responsive">').html('<table class="table table-bordered"><thead><tr><th>Activity</th><th>Description</th><th>Start Date</th><th>End Date</th><th>Assigned To</th><th>Today’s Work</th><th>Status</th></tr></thead><tbody></tbody></table>').appendTo(host).find('tbody');
        for (const row of data.rows) drawPlanRow(frm,project,row,data,$('<tr>').appendTo(table));
        if (!data.rows.length) $('<tr><td colspan="7"></td></tr>').find('td').text(__('No activities yet. Add an activity or save this project with a Project Template to generate its tasks.')).end().appendTo(table);
    }
    function drawPlanRow(frm,project,row,data,tr) {
        tr.empty();
        let description=row.description || '', selected=[...row.assigned_to], names={...data.user_names};
        const dirtyRows=frm.__bs_plan_dirty;
        const cell=()=> $('<td style="vertical-align:top;min-width:130px">').appendTo(tr);
        const titleCell=cell();
        const indicator=$('<div class="small text-muted" role="status" aria-live="polite">').text(__('Saved automatically'));
        const recovery=$('<div hidden>');
        let controller;
        const input=(parent,label,key,value,type='text')=>{
            const control=$('<input class="form-control input-sm bs-plan-edit">').attr({type,'aria-label':label+' '+row.name}).val(value || '').prop('disabled',!row.can_edit).appendTo(parent);
            control.on('input',event=>{
                // Mark composition as pending, but commit its final value only.
                if(event.originalEvent?.isComposing) return;
                controller.edit(key,control.val(),type==='text'?900:400);
            }).on('compositionend',()=>controller.edit(key,control.val(),900));
            control.on('change',()=>controller.edit(key,control.val())).on('blur',()=>controller.flush());
            return control;
        };
        const subject=input(titleCell,__('Activity'),'subject',row.subject);
        $('<div class="text-muted small">').text(row.name).appendTo(titleCell);
        indicator.appendTo(titleCell);recovery.appendTo(titleCell);
        $('<button type="button" class="btn btn-link btn-xs">').text(__('Open task form')).on('click',()=>{
            if(dirtyRows.size) return frappe.msgprint(__('Wait for automatic saving to finish or resolve the row save error.'));
            openProjectRecord(frm,{doctype:'Task'},row.name,()=>renderPlan(frm));
        }).appendTo(titleCell);
        const descriptionCell=cell();
        const preview=$('<div style="white-space:pre-wrap;max-width:250px;max-height:100px;overflow:auto">').text(row.description_text || '—').appendTo(descriptionCell);
        $('<button type="button" class="btn btn-default btn-xs bs-plan-edit">').text(__('Edit description')).prop('disabled',!row.can_edit).on('click',()=>{
            const d=new frappe.ui.Dialog({title:__('Activity Description'),size:'large',fields:[{fieldname:'description',fieldtype:'Text Editor',label:__('Description'),default:description}],primary_action_label:__('Done'),primary_action(v){description=v.description || '';preview.text(new DOMParser().parseFromString(description,'text/html').body.textContent || '—');controller.edit('description',description);d.hide();}});d.show();
        }).appendTo(descriptionCell);
        const start=input(cell(),__('Start Date'),'start_date',row.exp_start_date,'date'), end=input(cell(),__('End Date'),'end_date',row.exp_end_date,'date');
        const assigned=cell();
        const label=$('<div>').text(selected.map(u=>names[u] || u).join(', ') || __('Unassigned')).appendTo(assigned);
        $('<button type="button" class="btn btn-default btn-xs bs-plan-edit">').text(__('Choose users')).prop('disabled',!row.can_edit).on('click',async()=>{
            const {message:choices}=await frappe.call({method:'bsgroup.project_plan.assignment_choices',args:{project,task:row.name}});
            for(const u of selected) if(!choices.some(o=>o.value===u)) choices.push({value:u,label:names[u] || u,description:u});
            for(const o of choices) {names[o.value]=o.label;o.label=esc(o.label);o.description=esc(o.description);}
            const d=new frappe.ui.Dialog({title:__('Assign Activity'),fields:[{fieldname:'users',fieldtype:'MultiSelectList',label:__('Assigned To'),get_data:txt=>choices.filter(o=>(o.label+' '+o.value).toLowerCase().includes((txt||'').toLowerCase()))}],primary_action_label:__('Done'),primary_action(v){selected=[...(v.users || [])];label.text(selected.map(u=>names[u] || u).join(', ') || __('Unassigned'));controller.edit('assigned_to',selected);d.hide();}});
            d.show();await d.fields_dict.users.set_options();d.fields_dict.users.set_value(selected);
        }).appendTo(assigned);
        const work=cell();
        const workButton=$('<button type="button" class="btn btn-default btn-sm">').text(__('Enter today’s task')).attr('title',row.can_log_work?'':__('Only assigned users can record work.')).prop('disabled',!row.can_log_work).on('click',()=>showWork(frm,project,row,true)).appendTo(work);
        $('<button type="button" class="btn btn-link btn-sm">').text(__('View work history')).on('click',()=>showWork(frm,project,row,false)).appendTo(work);
        const statusCell=cell(), status=$('<select class="form-control input-sm">').attr('aria-label',__('Status')+' '+row.name).prop('disabled',!row.can_change_status || !data.work_updates_ready).appendTo(statusCell);
        const options=[...data.status_options]; if(!options.includes(row.status)) options.unshift(row.status);
        for(const value of options) $('<option>').val(value).text(__(value)).appendTo(status);
        status.val(row.status).on('change',()=>controller.edit('status',status.val()));
        const overdue=$('<div class="text-warning small">').text(__('Past end date')).toggle(!!row.overdue).appendTo(statusCell);
        controller=planAutosave(row,async(changes,base)=>{
            const {message:receipt}=await frappe.call({method:'bsgroup.project_plan.autosave_task',type:'POST',args:{project,task:row.name,changes,expected_modified:base.modified,expected_assignees:base.assigned_to}});
            return receipt;
        },state=>{
            const unsaved=state.busy || state.pending;
            if(unsaved){dirtyRows.add(row.name);pendingSaves.add(controller);}
            else {dirtyRows.delete(row.name);pendingSaves.delete(controller);}
            indicator.text(state.failed?__('Not saved — check the error and retry or reload this row.'):unsaved?__('Saving…'):__('Saved automatically'))
                .toggleClass('text-danger',state.failed).toggleClass('text-muted',!state.failed);
            recovery.prop('hidden',!state.failed);
        },(receipt,pending)=>{
            row=receipt.row;Object.assign(names,receipt.user_names);
            // Update only acknowledged fields; preserve anything typed while
            // the request was in flight and keep the user's focus in place.
            if(!pending.has('subject'))subject.val(row.subject);
            if(!pending.has('description')){description=row.description || '';preview.text(row.description_text || '—');}
            if(!pending.has('start_date'))start.val(row.exp_start_date || '');
            if(!pending.has('end_date'))end.val(row.exp_end_date || '');
            if(!pending.has('assigned_to')){selected=[...row.assigned_to];label.text(selected.map(u=>names[u] || u).join(', ') || __('Unassigned'));}
            if(!pending.has('status')){
                if(!status.find('option').toArray().some(o=>o.value===row.status)) $('<option>').val(row.status).text(__(row.status)).appendTo(status);
                status.val(row.status);
            }
            tr.find('.bs-plan-edit').prop('disabled',!row.can_edit);
            status.prop('disabled',!row.can_change_status || !data.work_updates_ready);
            workButton.prop('disabled',!row.can_log_work);
            overdue.toggle(!!row.overdue);
            if(frm.__bs_activity_tabs?.tasks)frm.__bs_activity_tabs.tasks.activity_project=null;
        });
        $('<button type="button" class="btn btn-link btn-xs">').text(__('Retry')).on('click',()=>controller.flush()).appendTo(recovery);
        $('<button type="button" class="btn btn-link btn-xs">').text(__('Reload row')).on('click',()=>{
            if(controller.busy())return;
            frappe.confirm(__('Reload this row and discard its unsaved changes?'),async()=>{
                if(controller.busy())return;
                const {message:fresh}=await frappe.call({method:'bsgroup.project_plan.get_plan',args:{project}});
                if(controller.busy())return;
                controller.dispose();
                const updated=fresh.rows.find(r=>r.name===row.name);
                if(updated)drawPlanRow(frm,project,updated,fresh,tr);else tr.remove();
            });
        }).appendTo(recovery);
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
        const host = tab.activity_host.addClass('bs-project-activity');
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
        if(frm.__bs_plan_dirty?.size) return frappe.msgprint(__('Wait for automatic saving to finish or resolve the row save error before opening another form.'));
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
