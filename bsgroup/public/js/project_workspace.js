(() => {
    const sections = {tasks:'Tasks', timesheets:'Timesheets', scheduler:'Tech Task Scheduler', expenses:'Expenses', advances:'Advance', labor:'Labour Approval'};
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    frappe.ui.form.on('Project', {
        refresh(frm) {
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
            if (frm.is_new()) {field.$wrapper.text(__('Save this project to use its activities.')); return;}
            for (const title of ['Expenses','Advance','Labour Approval']) frm.remove_custom_button(__(title),__('Project Requests'));
            frm.add_custom_button(__('Project Activities'), () => frm.scroll_to_field('custom_bs_project_workspace'));
            render(frm, frm.__bs_activity || 'tasks');
        }
    });
    async function renderPlan(frm) {
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
        $('<button type="button" class="btn btn-default btn-sm">').text(__('Refresh Plan')).on('click',()=>renderPlan(frm)).appendTo(actions);
        if (data.can_create) $('<button type="button" class="btn btn-primary btn-sm">').text(__('Add Activity')).on('click',()=>{
            frappe.new_doc('Task', {project, company:data.company});
        }).appendTo(actions);
        if (!data.can_read_tasks) {$('<p>').text(__('Your current access does not allow viewing project tasks.')).appendTo(host); return;}
        const table = $('<div class="table-responsive">').html('<table class="table table-bordered"><thead><tr><th>Activity</th><th>Description</th><th>Start Date</th><th>End Date</th><th>Assigned To</th><th>Status</th><th>Action</th></tr></thead><tbody></tbody></table>').appendTo(host).find('tbody');
        for (const row of data.rows) {
            const tr = $('<tr>').appendTo(table);
            $('<td>').html(`<a href="/desk/task/${encodeURIComponent(row.name)}">${esc(row.subject)}</a><div class="text-muted small">${esc(row.name)}</div>`).appendTo(tr);
            $('<td style="min-width:180px;max-width:360px;white-space:pre-wrap">').text(row.description_text || '—').appendTo(tr);
            $('<td style="white-space:nowrap">').text(row.exp_start_date ? frappe.datetime.str_to_user(row.exp_start_date) : '—').appendTo(tr);
            $('<td style="white-space:nowrap">').text(row.exp_end_date ? frappe.datetime.str_to_user(row.exp_end_date) : '—').appendTo(tr);
            $('<td>').text(row.assigned_to.map(user=>data.user_names[user] || user).join(', ') || __('Unassigned')).appendTo(tr);
            $('<td>').text(__(row.status)).appendTo(tr);
            const edit = $('<td>').appendTo(tr);
            if (row.can_edit) $('<button type="button" class="btn btn-default btn-sm">').text(__('Edit')).attr('aria-label',__('Edit')+' '+row.subject).on('click',()=>editPlanTask(frm,project,row,data.user_names)).appendTo(edit);
            else edit.text(__('Read only'));
        }
        if (!data.rows.length) $('<tr><td colspan="7"></td></tr>').find('td').text(__('No activities yet. Add an activity or save this project with a Project Template to generate its tasks.')).end().appendTo(table);
    }
    async function editPlanTask(frm, project, row, names) {
        const {message:choices} = await frappe.call({method:'bsgroup.project_plan.assignment_choices',args:{project,task:row.name}});
        if (frm.doc.name!==project) return;
        for (const user of row.assigned_to) if (!choices.some(option=>option.value===user)) choices.push({value:user,label:names[user] || user,description:user});
        for (const option of choices) {option.label=esc(option.label);option.description=esc(option.description);}
        const dialog = new frappe.ui.Dialog({
            title:__('Edit Project Activity'), size:'large',
            fields:[
                {fieldname:'subject',fieldtype:'Data',label:__('Activity'),reqd:1,default:row.subject},
                {fieldname:'description',fieldtype:'Text Editor',label:__('Description'),default:row.description || ''},
                {fieldname:'date_section',fieldtype:'Section Break'},
                {fieldname:'start_date',fieldtype:'Date',label:__('Start Date'),default:row.exp_start_date},
                {fieldname:'date_column',fieldtype:'Column Break'},
                {fieldname:'end_date',fieldtype:'Date',label:__('End Date'),default:row.exp_end_date},
                {fieldname:'assignment_section',fieldtype:'Section Break'},
                {fieldname:'assigned_to',fieldtype:'MultiSelectList',label:__('Assigned To'),default:[...row.assigned_to],
                    description:__('Choose users who already have access to this project and task.'),
                    get_data:txt=>choices.filter(option=>(option.label+' '+option.value).toLowerCase().includes((txt || '').toLowerCase()))}
            ],
            primary_action_label:__('Save Activity'),
            async primary_action(values) {
                if (dialog.__saving) return;
                dialog.__saving = true;
                dialog.get_primary_btn().prop('disabled',true);
                try {
                    await frappe.call({method:'bsgroup.project_plan.save_task',type:'POST',freeze:true,
                        args:{project,task:row.name,subject:values.subject,description:values.description || '',
                            start_date:values.start_date || '',end_date:values.end_date || '',assigned_to:values.assigned_to || [],
                            expected_modified:row.modified,expected_assignees:row.assigned_to}});
                    dialog.hide();
                    frappe.show_alert({message:__('Project activity updated'),indicator:'green'});
                    if (frm.doc.name===project) {
                        renderPlan(frm);
                        if (frm.fields_dict.custom_bs_project_workspace) render(frm,frm.__bs_activity || 'tasks');
                    }
                } finally {
                    dialog.__saving = false;
                    dialog.get_primary_btn().prop('disabled',false);
                }
            }
        });
        dialog.show();
        await dialog.fields_dict.assigned_to.set_options();
        dialog.fields_dict.assigned_to.set_value([...row.assigned_to]);
    }
    async function render(frm, section) {
        frm.__bs_activity = section;
        const version = frm.__bs_activity_version = (frm.__bs_activity_version || 0) + 1;
        const project = frm.doc.name;
        const host = frm.fields_dict.custom_bs_project_workspace.$wrapper;
        host.empty();
        $('<h4>').text(frm.doc.project_name || project).appendTo(host);
        $('<p class="text-muted">').text(__('Activities for this project only') + ' · ' + project).appendTo(host);
        const nav = $('<nav aria-label="Project activities" style="display:flex;gap:8px;flex-wrap:wrap;margin:16px 0">').appendTo(host);
        for (const [id,title] of Object.entries(sections)) $('<button type="button" class="btn btn-sm">')
            .addClass(id===section ? 'btn-primary' : 'btn-default').attr('aria-pressed',String(id===section))
            .text(__(title)).on('click',()=>render(frm,id)).appendTo(nav);
        const panel = $('<section aria-live="polite">').text(__('Loading…')).appendTo(host);
        let data;
        try {
            ({message:data} = await frappe.call({method:'bsgroup.project_workspace.context',args:{project,section}}));
        } catch (error) {
            if (version===frm.__bs_activity_version) panel.text(__('Could not load this project activity. Check your access and try again.'));
            return;
        }
        if (version!==frm.__bs_activity_version || frm.doc.name!==project) return;
        panel.empty();
        if (data.problem) $('<p class="text-muted">').text(data.problem).appendTo(panel);
        const actions = $('<div style="display:flex;gap:8px;margin-bottom:12px">').appendTo(panel);
        if (data.can_create) $('<button type="button" class="btn btn-primary btn-sm">').text(__('New')+' '+__(data.doctype)).on('click',()=>{
            frappe.model.with_doctype(data.doctype, () => {
                const doc = frappe.model.get_new_doc(data.doctype);
                Object.assign(doc,data.defaults);
                doc.__bs_project_request = project;
                if (data.child) {
                    const child = frappe.model.add_child(doc,data.child.field);
                    Object.assign(child,data.child.values);
                }
                frappe.set_route('Form',data.doctype,doc.name);
            });
        }).appendTo(actions);
        $('<button type="button" class="btn btn-default btn-sm">').text(__('Refresh')).on('click',()=>render(frm,section)).appendTo(actions);
        if (!data.available) {$('<p>').text(__('This activity is restricted by your existing access.')).appendTo(panel); return;}
        const route=data.doctype.toLowerCase().replaceAll(' ','-');
        $('<div class="table-responsive">').html(`<table class="table table-bordered"><thead><tr><th>Record</th><th>Details</th><th>Status</th></tr></thead><tbody>${data.rows.map(row=>
            `<tr><td><a href="/desk/${route}/${encodeURIComponent(row.name)}">${esc(row.name)}</a></td><td>${esc(row.subject||row.employee_name||row.task||'—')}</td><td>${esc(row.workflow_state||row.status||['Draft','Submitted','Cancelled'][row.docstatus])}</td></tr>`
        ).join('') || '<tr><td colspan="3">No records for this project.</td></tr>'}</tbody></table>`).appendTo(panel);
        $('<p class="text-muted">').text(__('Showing up to 100 accessible records linked to this project.')).appendTo(panel);
    }
})();
