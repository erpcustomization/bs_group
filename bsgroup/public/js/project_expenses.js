(() => {
    const method = 'bsgroup.project_expenses.context';
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    frappe.ui.form.on('Project', {
        refresh(frm) {
            if (!frm.is_new()) frm.add_custom_button(__('Expenses'), () => openExpenses(frm), __('Project Requests'));
        }
    });
    async function openExpenses(frm) {
        const {message: data} = await frappe.call({method, args:{project:frm.doc.name}, freeze:true});
        const dialog = new frappe.ui.Dialog({title:__('Project Expenses'), size:'large',
            fields:[{fieldtype:'HTML', fieldname:'claims'}]});
        const rows = data.claims.map(row => `<tr><td><a href="/desk/expense-claim/${encodeURIComponent(row.name)}">${esc(row.name)}</a></td><td>${esc(row.employee_name)}</td><td>${esc(frappe.datetime.str_to_user(row.posting_date))}</td><td>${esc(row.workflow_state || row.status)}</td><td style="text-align:right">${esc(format_currency(row.total_claimed_amount,data.currency))}</td></tr>`).join('');
        dialog.fields_dict.claims.$wrapper.html(`<div style="margin-bottom:16px"><strong>${esc(data.project_name)}</strong><div class="text-muted">${esc(data.project)} · ${esc(data.company)}</div></div>
            ${data.expense_approver ? `<p>Project Manager approval: <strong>${esc(data.expense_approver)}</strong></p>` : ''}
            ${data.problem ? `<div class="alert alert-warning">${esc(data.problem)}</div>` : ''}
            <div class="table-responsive"><table class="table table-bordered"><thead><tr><th>Claim</th><th>Employee</th><th>Date</th><th>Status</th><th>Amount</th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="text-muted">No expense claims to show for this project.</td></tr>'}</tbody></table></div>
            <p class="text-muted">Claims are linked to this project and follow Project Manager approval, then the existing final approval process.</p>`);
        if (data.can_create) dialog.set_primary_action(__('Add Expense Claim'), async () => {
            dialog.hide();
            await frappe.new_doc('Expense Claim', {project:data.project, company:data.company,
                employee:data.employee, expense_approver:data.expense_approver});
        });
        dialog.show();
    }
})();
