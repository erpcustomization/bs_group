// With the standard filter bar hidden, keep every saved filter in the popup.
(() => {
    const doctypes = new Set(['Lead', 'Opportunity', 'Presales Request', 'Deal Cost Sheet', 'Quotation']);
    const proto = frappe.views.ListView.prototype;
    if (proto._bsi_popup_filters_installed) return;
    proto._bsi_popup_filters_installed = true;

    async function show_standard_filters(listview) {
        const area = listview.filter_area;
        if (!area || area._bsi_popup_only) return area?._bsi_popup_migration;
        area._bsi_popup_only = true;
        // Run after all list onload handlers, including database Client Scripts
        // that replace listview_settings rather than extending its handlers.
        const saved = area.get_standard_filters();
        area.set_standard_filter = filters => ({non_standard_filters:filters, promise:Promise.resolve()});
        const existing = area.filter_list.get_filters();
        const pending = saved.filter(f => !existing.some(e => e[0] === f[0] && e[1] === f[1]));
        const wasRefreshing = area.trigger_refresh;
        area.trigger_refresh = false;
        area._bsi_popup_migration = Promise.resolve().then(async () => {
            try {
                for (const f of saved) {
                    await listview.page.fields_dict[f[1]]?.set_value('');
                }
                await area.filter_list.add_filters(pending);
                area.filter_list.update_filter_button();
            } finally { area.trigger_refresh = wasRefreshing; }
        });
        return area._bsi_popup_migration;
    }

    const beforeRefresh = proto.before_refresh;
    proto.before_refresh = async function(...args) {
        if (doctypes.has(this.doctype)) await show_standard_filters(this);
        return beforeRefresh.apply(this, args);
    };
})();
