(() => {
    const sections = {tasks:'Tasks', timesheets:'Timesheets', scheduler:'Tech Task Scheduler', expenses:'Expenses', advances:'Advance', labor:'Labour Approval'};
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    frappe.ui.form.on('Project', {
        refresh(frm) {
            for (const name of ['connections_tab', 'costing_tab']) {
                if (frm.fields_dict[name]) frm.set_df_property(name, 'hidden', 1);
            }
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
