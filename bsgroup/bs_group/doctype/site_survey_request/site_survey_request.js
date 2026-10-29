frappe.ui.form.on('Site Survey Request', {
    refresh(frm) {
        frm.page.set_indicator(frm.doc.status, {
            Requested: 'orange', Scheduled: 'blue', 'In Progress': 'purple',
            Completed: 'green', Cancelled: 'gray'
        }[frm.doc.status] || 'blue');
        if (frm.doc.presales_request) frm.add_custom_button(__('Presales Request'), () =>
            frappe.set_route('Form', 'Presales Request', frm.doc.presales_request));
        if (frm.doc.opportunity) frm.add_custom_button(__('Opportunity'), () =>
            frappe.set_route('Form', 'Opportunity', frm.doc.opportunity));
    }
});
