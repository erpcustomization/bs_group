// These records are started from their linked sales workflow, not the list.
(() => {
    for (const doctype of ['Presales Request', 'Deal Cost Sheet', 'Quotation']) {
        const settings = frappe.listview_settings[doctype] ||= {};
        if (settings.bsi_linked_creation_only) continue;
        settings.bsi_linked_creation_only = true;
        for (const event of ['onload', 'refresh']) {
            const previous = settings[event];
            settings[event] = function (listview) {
                listview.can_create = false;
                const result = previous?.apply(this, arguments);
                listview.page.clear_primary_action();
                listview.$no_result?.find('.btn-new-doc').hide();
                return result;
            };
        }
    }
})();
