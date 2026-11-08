// Native forms, workflows, payments and helpdesk-origin labour requests remain unchanged.
(() => {
    const bind = (frm,project,fields) => {
        if (!project) return;
        frm.add_custom_button(__('Back to Project'), () => frappe.set_route('Form','Project',project));
        if (frm.is_new() && frm.doc.__bs_project_request === project) {
            for (const field of fields) frm.set_df_property(field,'read_only',1);
        }
    };
    frappe.ui.form.on('Employee Advance', {
        refresh(frm) {bind(frm,frm.doc.custom_project,['custom_project','employee','company']);}
    });
    frappe.ui.form.on('Labor Preapproval', {
        refresh(frm) {
            if (frm.doc.source === 'Project') bind(frm,frm.doc.reference,['source','reference','company']);
        }
    });
})();
