// Keep native creation flows; no downstream record may be saved without its source.
for (const doctype of ['Presales Request', 'Deal Cost Sheet', 'Quotation', 'Site Survey Request']) {
    frappe.ui.form.on(doctype, {
        refresh(frm) {
            if (!frm.is_new()) return;
            frm.toggle_reqd('opportunity', true);
            if (!frm.doc.opportunity) frm.set_intro(__('Create or select an Opportunity first. This record cannot be created without an Opportunity.'), 'orange');
        },
        opportunity(frm) {
            if (frm.is_new() && frm.doc.opportunity) frm.set_intro('');
        },
        validate(frm) {
            if (frm.is_new() && !frm.doc.opportunity) frappe.throw(__('Create or select an Opportunity first.'));
        }
    });
}
