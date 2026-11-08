(() => {
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    const config = {
        advance: {title:'Project Advances', action:'Request Advance', route:'employee-advance',
            help:'Enter the purpose and amount, then send the advance through the existing approval process.'},
        labor: {title:'Project Labour Approvals', action:'Request Labour Approval', route:'labor-preapproval',
            help:'Choose a task from this project and enter the labour, days and rates. Existing approval and budget controls apply.'}
    };
    frappe.ui.form.on('Project', {
        refresh(frm) {
            if (frm.is_new()) return;
            frm.add_custom_button(__('Advance'), () => openRequests(frm,'advance'), __('Project Requests'));
            frm.add_custom_button(__('Labour Approval'), () => openRequests(frm,'labor'), __('Project Requests'));
        }
    });
    async function openRequests(frm,kind) {
        const settings = config[kind];
        const {message:data} = await frappe.call({method:'bsgroup.project_requests.context',
            args:{project:frm.doc.name,kind},freeze:true});
        const dialog = new frappe.ui.Dialog({title:__(settings.title),size:'large',
            fields:[{fieldname:'requests',fieldtype:'HTML'}]});
        const rows = data.records.map(row => `<tr><td><a href="/desk/${settings.route}/${encodeURIComponent(row.name)}">${esc(row.name)}</a></td>
            <td>${esc(row.employee_name || row.task || '—')}</td><td>${esc(frappe.datetime.str_to_user(row.creation))}</td>
            <td>${esc(row.workflow_state || row.status || ['Draft','Submitted','Cancelled'][row.docstatus])}</td>
            <td style="text-align:right">${esc(format_currency(row[data.amount_field],row.currency || data.currency))}</td></tr>`).join('');
        dialog.fields_dict.requests.$wrapper.html(`<strong>${esc(data.project_name)}</strong><div class="text-muted" style="margin-bottom:18px">${esc(data.project)} · ${esc(data.company)}</div>
            ${data.problem ? `<div class="alert alert-warning">${esc(data.problem)}</div>` : ''}
            <div class="table-responsive"><table class="table table-bordered"><thead><tr><th>Request</th><th>${kind==='advance'?'Employee':'Task'}</th><th>Created</th><th>Status</th><th>Amount</th></tr></thead>
            <tbody>${rows || '<tr><td colspan="5" class="text-muted">No requests to show for this project.</td></tr>'}</tbody></table></div>
            <p class="text-muted">${esc(__(settings.help))}</p>`);
        if (data.can_create) dialog.set_primary_action(__(settings.action), () => {
            dialog.hide();
            frappe.new_doc(data.doctype,data.defaults,doc => {doc.__bs_project_request = data.project;});
        });
        dialog.show();
    }
})();
