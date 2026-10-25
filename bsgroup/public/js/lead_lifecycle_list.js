// Preserve native list actions and links; replace only the visible lifecycle indicator.
(() => {
    const settings = frappe.listview_settings.Lead || (frappe.listview_settings.Lead = {});
    settings.add_fields = [...new Set([...(settings.add_fields || []), "status", "creation"])];
    const active = ["Lead", "Open", "Replied", "Interested", "Delayed"];
    const closed = ["Opportunity", "Quotation", "Converted", "Lost Quotation"];
    settings.formatters = {...(settings.formatters || {})};
    for (const field of ['name', 'company_name']) {
        settings.formatters[field] = (value, df, doc) => {
            const label = frappe.utils.escape_html(String(value || ''));
            const name = frappe.utils.escape_html(String(doc.name));
            return `<a class="ellipsis" data-doctype="Lead" data-name="${name}" href="/desk/lead/${encodeURIComponent(doc.name)}" title="${label}">${label}</a>`;
        };
    }
    const nativeOnload = settings.onload;
    settings.onload = function(listview) {
        nativeOnload?.call(this, listview);
        const root = listview.page.wrapper[0] || listview.page.wrapper;
        root.classList.add('bsi-lead-list-colors');
        if (!root.querySelector('.bsi-lead-status-style')) {
            const style = document.createElement('style'); style.className = 'bsi-lead-status-style';
            const colors = {blue:['#ddd6fe','#5b21b6','#a78bfa'],green:['#087f5b','#ffffff','#087f5b'],red:['#c92a2a','#ffffff','#c92a2a'],orange:['#a35b00','#ffffff','#a35b00'],amber:['#a35b00','#ffffff','#a35b00']};
            style.textContent = Object.entries(colors).map(([color,[bg,text,border]]) =>
                `.bsi-lead-list-colors .es-badge[data-filter^="status,"][data-theme="${color}"],.bsi-lead-list-colors .indicator-pill.${color}[data-filter^="status,"]{background:${bg}!important;color:${text}!important;border:1px solid ${border}!important}.bsi-lead-list-colors .es-badge[data-filter^="status,"][data-theme="${color}"] .es-badge__label{color:${text}!important}`
            ).join('');
            style.textContent += '.bsi-lead-list-colors{--text-color:#172b4d;--text-muted:#60718b;--border-color:#dfe7f2;color:#172b4d}.bsi-lead-list-colors .list-row-head{background:#eef3fb!important;color:#4c6486!important;border-color:#dfe7f2!important}.bsi-lead-list-colors .list-row{color:#172b4d}.bsi-lead-list-colors .list-row a{color:#1b5ab4!important}.bsi-lead-list-colors .title-text{color:#12335f!important}.bsi-lead-list-colors .primary-action{background:#1d5fc4!important;color:#fff!important;border-color:#1d5fc4!important}';
            style.textContent += '@media(min-width:768px){.bsi-lead-list-colors .list-row-col{order:10}.bsi-lead-list-colors .list-row-col[data-fieldname="title"]{position:static!important}.bsi-lead-list-colors .list-row>.level-left:first-child,.bsi-lead-list-colors .list-header-subject{position:relative;padding-left:26px}.bsi-lead-list-colors .list-row-col[data-fieldname="name"]{order:1}.bsi-lead-list-colors .list-row-col[data-fieldname="status_field"]{order:2}.bsi-lead-list-colors .list-row-col[data-fieldname="company_name"]{order:3}.bsi-lead-list-colors .list-row-col[data-fieldname="title"]{order:4}.bsi-lead-list-colors .list-row-col[data-fieldname="title"]>.select-like{position:absolute;left:0;top:50%;transform:translateY(-50%);margin:0}.bsi-lead-list-colors .list-row-col.tag-col{order:5}}';
            style.textContent += '.bsi-lead-list-colors .standard-filter-section{display:none!important}.bsi-lead-list-colors .list-page-form{display:flex!important;justify-content:flex-end;align-items:center;gap:10px}.bsi-lead-list-colors .filter-section{margin-left:0!important;border-left:0!important;padding-left:0!important}';
            style.textContent += '.bsi-lead-list-colors .list-liked-by-me,.bsi-lead-list-colors .list-row-like{display:none!important}';
            style.textContent += '.bsi-lead-list-colors .list-row-activity .modified{min-width:82px;width:82px;flex:0 0 82px;white-space:nowrap}.bsi-lead-list-colors .bsi-lead-date{font-variant-numeric:tabular-nums}';
            root.append(style);
        }

        // Format the existing modified timestamp at row creation, including
        // virtual rows. Keep its full timestamp tooltip and all other controls.
        if (!listview._bsi_absolute_dates && typeof listview.get_meta_html === 'function') {
            const nativeMeta = listview.get_meta_html;
            listview.get_meta_html = function(doc) {
                const holder = document.createElement('div');
                holder.innerHTML = nativeMeta.call(this, doc);
                holder.querySelectorAll('.modified [data-timestamp]').forEach(node => {
                    const timestamp = node.dataset.timestamp;
                    node.textContent = frappe.datetime.str_to_user(frappe.datetime.convert_to_user_tz(timestamp).split(' ')[0]);
                    node.classList.remove('frappe-timestamp', 'mini');
                    node.classList.add('bsi-lead-date');
                    node.setAttribute('aria-label', __('Last updated') + ': ' + node.textContent);
                });
                return holder.innerHTML;
            };
            listview._bsi_absolute_dates = true;
        }
        const field = listview.page.fields_dict.status;
        if (field) {
            field.df.options = "\nOpen\nDelayed\nOpportunity\nDropped";
            field.refresh();
        }
    };
    settings.get_indicator = doc => {
        if (closed.includes(doc.status)) return [__(doc.status === "Opportunity" ? "Opportunity · Closed" : "Closed"), "green", "status,=," + doc.status];
        if (["Dropped", "Do Not Contact"].includes(doc.status)) return [__("Dropped"), "red", "status,=," + doc.status];
        const age = doc.creation ? moment().diff(frappe.datetime.convert_to_user_tz(doc.creation, false), 'hours', true) : 0;
        return doc.status === "Delayed" || (active.includes(doc.status) && age >= 24)
            ? [__("Delayed"), "orange", "status,=,Delayed"] : [__("Open"), "blue", "status,=," + doc.status];
    };
})();
