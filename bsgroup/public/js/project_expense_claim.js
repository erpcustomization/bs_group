(() => {
    frappe.ui.form.on('Expense Claim', {
        refresh(frm) {
            if (frm.is_new() && !frm.doc.project) {
                frm.disable_save();
                frm.set_intro(__('To claim an expense, open the project you are working on and choose Expenses.'), 'orange');
                frm.add_custom_button(__('Choose Project'), () => frappe.set_route('List','Project'));
                return;
            }
            if (frm.doc.project) {
                frm.set_df_property('project','read_only',1);
                frm.set_df_property('expense_approver','read_only',1);
                frm.set_df_property('employee','read_only',1);
                frm.set_df_property('company','read_only',1);
                for (const field of ['expenses','taxes']) {
                    frm.fields_dict[field]?.grid?.update_docfield_property('project','read_only',1);
                }
                frm.add_custom_button(__('Back to Project'), () => frappe.set_route('Form','Project',frm.doc.project));
                if (frm.is_new()) frm.set_intro(__('Enter the expense details and attach receipts. Save, then Send for Approval to the Project Manager.'), 'blue');
            }
        },
        validate(frm) {
            if (!frm.doc.project) frappe.throw(__('A project is required. Open your project and choose Expenses.'));
        }
    });
})();
