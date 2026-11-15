(() => {
    const allowed=()=>frappe.user.has_role('System Manager');
    const open=()=>frappe.set_route('bs-user-management');
    frappe.ui.form.on('User', {refresh(frm) {
        frm.set_df_property('first_name','reqd',1);
        frm.set_df_property('first_name','hidden',0);
        if(allowed())frm.add_custom_button(__('BS User Management'),open);
    }});
    const settings=frappe.listview_settings.User=frappe.listview_settings.User||{};
    const prior=settings.onload;
    settings.onload=function(listview){if(prior)prior.call(this,listview);if(allowed())listview.page.add_inner_button(__('BS User Management'),open);};
})();
