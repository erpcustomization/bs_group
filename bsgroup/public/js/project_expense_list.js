// Keep the native approval/audit list. New claims always start from a project.
(() => {
    const settings = frappe.listview_settings['Expense Claim'] ||= {};
    const prior = settings.refresh;
    settings.refresh = function(listview) {
        if (prior) prior.call(this,listview);
        if (frappe.model.can_create('Expense Claim')) listview.page.set_primary_action(
            __('Choose Project for Expense'), () => frappe.set_route('List','Project'), 'add');
    };
})();
