// With the standard filter bar hidden, keep every saved filter in the popup.
(() => {
    for (const doctype of ['Lead', 'Opportunity']) {
        const settings = frappe.listview_settings[doctype];
        if (!settings || settings._bsi_popup_filters) continue;
        settings._bsi_popup_filters = true;
        const previous = settings.onload;
        settings.onload = function(listview) {
            previous?.call(this, listview);
            const area = listview.filter_area;
            if (!area || area._bsi_popup_only) return;
            area._bsi_popup_only = true;
            const saved = area.get_standard_filters();
            // Future saved/route filters must not repopulate the hidden controls.
            area.set_standard_filter = filters => ({non_standard_filters:filters, promise:Promise.resolve()});
            const existing = area.filter_list.get_filters();
            const pending = saved.filter(f => !existing.some(e => e[0] === f[0] && e[1] === f[1]));
            const wasRefreshing = area.trigger_refresh;
            area.trigger_refresh = false;
            const migration = (async () => {
                try {
                    for (const f of saved) {
                        await listview.page.fields_dict[f[1]]?.set_value('');
                    }
                    await area.filter_list.add_filters(pending);
                    area.filter_list.update_filter_button();
                } finally { area.trigger_refresh = wasRefreshing; }
            })();
            const beforeRefresh = listview.before_refresh;
            listview.before_refresh = async function(...args) {
                await migration;
                return beforeRefresh?.apply(this,args);
            };
        };
    }
})();
