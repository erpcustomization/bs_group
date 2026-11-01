(() => {
    const settings = frappe.listview_settings.Opportunity;
    const previous = settings.refresh;
    async function render(listview) {
        const names = (listview.data || []).map(d => d.name);
        if (!names.length || listview._progress_loading) return;
        listview._progress_loading = true;
        try {
            const result = await frappe.call({method:'bsgroup.opportunity_progress.statuses',args:{names:names.slice(0,500)}});
            const root = listview.page.wrapper[0] || listview.page.wrapper;
            root.querySelectorAll('.list-row').forEach(row => {
                const name = row.querySelector('.list-row-checkbox')?.dataset.name;
                const progress = result.message?.[name];
                const cell = row.querySelector('[data-fieldname="status_field"]');
                if (!progress || !cell) return;
                const badge = document.createElement('span');
                badge.className = 'indicator-pill ' + progress.color;
                badge.textContent = __(progress.label);
                badge.title = progress.label;
                badge.style.cssText = 'white-space:normal;line-height:16px;height:auto;padding:3px 7px;max-width:100%';
                cell.replaceChildren(badge);
            });
            if (!root.querySelector('.bsi-progress-list-style')) {
                const style = document.createElement('style');
                style.className = 'bsi-progress-list-style';
                style.textContent = 'body.bs-sales-ui[data-route="List/Opportunity/List"] .bsi-opportunity-columns .list-row-col[data-fieldname="status_field"]{flex:0 0 190px!important;min-width:190px!important;white-space:normal}';
                root.append(style);
            }
        } finally { listview._progress_loading = false; }
    }
    settings.refresh = function(listview) {
        previous?.call(this,listview);
        render(listview);
        clearInterval(listview._progress_timer);
        listview._progress_timer = setInterval(() => {
            const root = listview.page.wrapper[0] || listview.page.wrapper;
            if (!root.isConnected || !root.getClientRects().length) { clearInterval(listview._progress_timer); return; }
            render(listview);
        },60000);
    };
})();
