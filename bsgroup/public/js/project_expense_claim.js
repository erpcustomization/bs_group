(() => {
    const types={'Transportation':'Travel','Petrol / fuel':'Travel','Food':'Food','Food for labourers':'Food','Project material expense':'Others'};
    frappe.ui.form.on('Expense Claim Detail',{
        async custom_project_expense_category(frm,cdt,cdn){
            const row=locals[cdt][cdn],type=types[row.custom_project_expense_category];
            if(frm.doc.project && type) await frappe.model.set_value(cdt,cdn,'expense_type',type);
        }
    });
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
                // Draft entry is allowed before the project's approver is set.
                // Server validation still requires an eligible manager to submit.
                frm.set_df_property('expense_approver','reqd',0);
                frm.set_df_property('employee','read_only',1);
                frm.set_df_property('company','read_only',1);
                frm.fields_dict.expenses?.grid?.update_docfield_property('custom_project_expense_category','reqd',frm.is_new()?1:0);
                for (const field of ['expenses','taxes']) {
                    frm.fields_dict[field]?.grid?.update_docfield_property('project','read_only',1);
                }
                frm.add_custom_button(__('Back to Project'), () => frappe.set_route('Form','Project',frm.doc.project));
                if (frm.is_new()) frm.set_intro(__('Enter the expense details and attach receipts, then save your draft. Approval can be configured later; saving does not approve or pay the claim.'), 'blue');
            }
        },
        validate(frm) {
            if (!frm.doc.project) frappe.throw(__('A project is required. Open your project and choose Expenses.'));
        }
    });
})();
