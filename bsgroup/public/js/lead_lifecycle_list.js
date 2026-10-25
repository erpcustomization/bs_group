// Preserve native list actions and links; replace only the visible lifecycle indicator.
frappe.bsi_setup_sales_list = (doctype) => {

    const isLead = doctype === 'Lead';
    const ownerField = isLead ? 'lead_owner' : 'opportunity_owner';
    const settings = frappe.listview_settings[doctype] || (frappe.listview_settings[doctype] = {});
    settings.add_fields = [...new Set([...(settings.add_fields || []), "status", "creation", ownerField])];
    if (!isLead) settings.add_fields = [...new Set([...settings.add_fields, "custom_subject", "custom_organization_name", "opportunity_amount", "currency"])];
    const active = ["Lead", "Open", "Replied", "Interested", "Delayed"];
    const closed = ["Opportunity", "Quotation", "Converted", "Lost Quotation"];
    settings.formatters = {...(settings.formatters || {})};
    for (const field of ['name', isLead ? 'company_name' : 'customer_name']) {
        settings.formatters[field] = (value, df, doc) => {
            const label = frappe.utils.escape_html(String(value || ''));
            const name = frappe.utils.escape_html(String(doc.name));
            return `<a class="ellipsis" data-doctype="${doctype}" data-name="${name}" href="/desk/${doctype.toLowerCase()}/${encodeURIComponent(doc.name)}" title="${label}">${label}</a>`;
        };
    }
    const ownerLabels = {};
    const nativeRefresh = settings.refresh;
    settings.refresh = function(listview) {
        nativeRefresh?.call(this, listview);
        const missing = (listview.data || []).filter(doc => doc[ownerField] && !ownerLabels[doc[ownerField]]);
        if (!missing.length || listview._bsi_owner_labels_loading) return;
        listview._bsi_owner_labels_loading = true;
        frappe.call({method: 'bsgroup.lead_lifecycle.list_owner_labels',
            args: {names: missing.map(doc => doc.name), doctype},
            callback: result => {
                Object.assign(ownerLabels, result.message || {});
                const root = listview.page.wrapper[0] || listview.page.wrapper;
                root.querySelectorAll('.bsi-lead-owner').forEach(badge => {
                    const label = ownerLabels[badge.dataset.leadOwner];
                    if (!label) return;
                    badge.textContent = label.initial;
                    badge.title = __(isLead ? 'Lead Owner' : 'Opportunity Owner') + ': ' + label.full_name;
                    badge.setAttribute('aria-label', badge.title);
                });
            },
            always: () => { listview._bsi_owner_labels_loading = false; }
        });
    };
    const nativeOnload = settings.onload;
    settings.onload = function(listview) {
        nativeOnload?.call(this, listview);
        const root = listview.page.wrapper[0] || listview.page.wrapper;
        root.classList.add('bsi-lead-list-colors');
        if (!isLead) {
            root.classList.add('bsi-opportunity-columns');
            const applyColumns = () => {
                const field = (name, label) => ({...frappe.meta.get_docfield('Opportunity', name), fieldname:name, label:__(label)});
                listview.columns = [
                    {type:'Subject', df:field('custom_subject', 'Title')},
                    {type:'Status'},
                    {type:'Field', df:field('custom_organization_name', 'Organization')},
                    {type:'Field', df:field('opportunity_amount', 'Opportunity Amount')},
                    {type:'Field', df:{fieldname:'name', label:__('ID'), fieldtype:'Data'}}
                ];
            };
            const nativeColumns = listview.setup_columns;
            listview.setup_columns = async function(...args) {
                await nativeColumns.apply(this, args);
                applyColumns();
            };
            applyColumns();
        }
        if (!root.querySelector('.bsi-lead-status-style')) {
            const style = document.createElement('style'); style.className = 'bsi-lead-status-style';
            const colors = {blue:['#ddd6fe','#5b21b6','#a78bfa'],green:['#087f5b','#ffffff','#087f5b'],red:['#c92a2a','#ffffff','#c92a2a'],orange:['#a35b00','#ffffff','#a35b00'],amber:['#a35b00','#ffffff','#a35b00']};
            style.textContent = Object.entries(colors).map(([color,[bg,text,border]]) =>
                `.bsi-lead-list-colors .es-badge[data-filter^="status,"][data-theme="${color}"],.bsi-lead-list-colors .indicator-pill.${color}[data-filter^="status,"]{background:${bg}!important;color:${text}!important;border:1px solid ${border}!important}.bsi-lead-list-colors .es-badge[data-filter^="status,"][data-theme="${color}"] .es-badge__label{color:${text}!important}`
            ).join('');
            style.textContent += '.bsi-lead-list-colors{--text-color:#172b4d;--text-muted:#60718b;--border-color:#dfe7f2;color:#172b4d}.bsi-lead-list-colors .list-row-head{background:#eef3fb!important;color:#4c6486!important;border-color:#dfe7f2!important}.bsi-lead-list-colors .list-row{color:#172b4d}.bsi-lead-list-colors .list-row a{color:#1b5ab4!important}.bsi-lead-list-colors .title-text{color:#12335f!important}.bsi-lead-list-colors .primary-action{background:#1d5fc4!important;color:#fff!important;border-color:#1d5fc4!important}';
            style.textContent += '@media(min-width:768px){.bsi-lead-list-colors .list-row-col{order:10}.bsi-lead-list-colors .list-row-col[data-fieldname="title"]{position:static!important}.bsi-lead-list-colors .list-row>.level-left:first-child,.bsi-lead-list-colors .list-header-subject{position:relative;padding-left:26px}.bsi-lead-list-colors .list-row-col[data-fieldname="name"]{order:1;flex:0 0 180px!important;width:180px!important;min-width:180px!important;max-width:none!important}.bsi-lead-list-colors .list-row-col[data-fieldname="status_field"]{order:2}.bsi-lead-list-colors .list-row-col[data-fieldname="company_name"]{order:3}.bsi-lead-list-colors .list-row-col[data-fieldname="title"]{order:4}.bsi-lead-list-colors .list-row-col[data-fieldname="title"]>.select-like{position:absolute;left:0;top:50%;transform:translateY(-50%);margin:0}.bsi-lead-list-colors .list-row-col.tag-col{order:5}}';
            style.textContent += '.bsi-lead-list-colors .standard-filter-section{display:none!important}.bsi-lead-list-colors .list-page-form{display:flex!important;justify-content:flex-end;align-items:center;gap:10px}.bsi-lead-list-colors .filter-section{margin-left:0!important;border-left:0!important;padding-left:0!important}';
            style.textContent += '.bsi-lead-list-colors .list-liked-by-me,.bsi-lead-list-colors .list-row-like{display:none!important}';
            style.textContent += '.bsi-lead-list-colors .list-row-activity .modified{min-width:82px!important;width:82px!important;flex:0 0 82px!important;white-space:nowrap}.bsi-lead-list-colors .bsi-lead-date{font-variant-numeric:tabular-nums}';
            style.textContent += '.bsi-lead-list-colors .page-actions .view-switcher,.bsi-lead-list-colors .page-actions .page-icon-group,.bsi-lead-list-colors .page-actions .menu-btn-group{display:none!important}';
            style.textContent += '.bsi-lead-list-colors .bsi-lead-header-filter{display:inline-flex!important;align-items:center;justify-content:center;width:34px;height:34px;padding:0!important;border-radius:8px!important;margin-right:8px}.bsi-lead-list-colors .bsi-lead-header-filter .button-label{display:none!important}.bsi-lead-list-colors .bsi-lead-header-filter .filter-icon{margin:0!important}.bsi-lead-list-colors.bsi-filter-in-header .list-page-form{display:none!important}';
            style.textContent += '.bsi-lead-list-colors .bsi-lead-owner{display:inline-flex;align-items:center;justify-content:center;flex:0 0 26px;width:26px;height:26px;border-radius:50%;background:#eef3fb;color:#12335f;font-size:12px;font-weight:600;border:1px solid #dfe7f2}';
            style.textContent += '.bsi-lead-list-colors .list-row-head>.level-right{position:relative}.bsi-lead-list-colors .list-row-head .list-count{visibility:hidden}.bsi-lead-list-colors .bsi-lead-meta-head{position:absolute;right:10px;display:flex;align-items:center;gap:10px;white-space:nowrap;font-size:10px}.bsi-lead-list-colors .bsi-lead-meta-head .date-heading{width:82px;text-align:center}.bsi-lead-list-colors .bsi-lead-meta-head .owner-heading{width:26px;text-align:center}';
            style.textContent += '.bsi-lead-list-colors .list-row-activity .list-assignments-container{display:none!important}';
            style.textContent += '@media(min-width:768px){body.bs-sales-ui[data-route="List/Opportunity/List"] .bsi-opportunity-columns .list-row-col[data-fieldname="name"]{flex:0 0 180px!important;min-width:180px!important}body.bs-sales-ui[data-route="List/Opportunity/List"] .bsi-opportunity-columns .list-row-col[data-fieldname="status_field"]{flex:0 0 100px!important;min-width:100px!important}body.bs-sales-ui[data-route="List/Opportunity/List"] .bsi-opportunity-columns .list-row-col[data-fieldname="custom_organization_name"]{order:3;flex:1 1 0%!important}body.bs-sales-ui[data-route="List/Opportunity/List"] .bsi-opportunity-columns .list-row-col[data-fieldname="custom_subject"]{order:4;position:static!important;flex:1.3 1 0%!important}body.bs-sales-ui[data-route="List/Opportunity/List"] .bsi-opportunity-columns .list-row-col[data-fieldname="opportunity_amount"]{order:5;flex:0 0 145px!important;min-width:145px!important;text-align:right}body.bs-sales-ui[data-route="List/Opportunity/List"] .bsi-opportunity-columns .list-row-col[data-fieldname="custom_subject"]>.select-like{position:absolute;left:0;top:50%;transform:translateY(-50%);margin:0}}';
            root.append(style);
        }

        if (!listview._bsi_meta_headings && typeof listview.get_header_html === 'function') {
            const nativeHeader = listview.get_header_html;
            listview.get_header_html = function(...args) {
                const html = nativeHeader.apply(this, args);
                if (!html) return html;
                const holder = document.createElement('div');
                holder.innerHTML = html;
                const right = holder.querySelector('.list-row-head > .level-right');
                if (right) {
                    const headings = document.createElement('span');
                    headings.className = 'bsi-lead-meta-head hidden-xs';
                    for (const [className, label] of [['date-heading', 'Date'], ['owner-heading', isLead ? 'Owners' : 'Owner']]) {
                        const heading = document.createElement('span');
                        heading.className = className;
                        heading.textContent = __(label);
                        headings.append(heading);
                    }
                    right.append(headings);
                }
                return holder.innerHTML;
            };
            listview._bsi_meta_headings = true;
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
                const comment = holder.querySelector('.comment-count');
                if (comment) {
                    const owner = doc[ownerField];
                    const label = ownerLabels[owner];
                    const fullName = label?.full_name || (owner && frappe.boot.user_info?.[owner]?.fullname);
                    const badge = document.createElement('span');
                    badge.className = 'bsi-lead-owner';
                    badge.dataset.leadOwner = owner || '';
                    if (owner) {
                        // Stable per user, including owners who share the same initial.
                        const hash = Array.from(owner.toLowerCase()).reduce((value, char) =>
                            (Math.imul(value, 31) + char.codePointAt(0)) >>> 0, 0);
                        const hue = hash % 360;
                        badge.style.backgroundColor = `hsl(${hue}, 65%, 93%)`;
                        badge.style.color = `hsl(${hue}, 55%, 28%)`;
                        badge.style.borderColor = `hsl(${hue}, 45%, 80%)`;
                    }
                    badge.textContent = label?.initial || (owner ? '?' : '—');
                    badge.title = owner ? __(isLead ? 'Lead Owner' : 'Opportunity Owner') + ': ' + (fullName || owner) : __(isLead ? 'Lead Owner not set' : 'Opportunity Owner not set');
                    badge.setAttribute('aria-label', badge.title);
                    comment.replaceWith(badge);
                    holder.querySelectorAll('.list-row-activity > .mx-2').forEach(node => node.remove());
                }
                return holder.innerHTML;
            };
            listview._bsi_absolute_dates = true;
        }
        // Reparent the native sorter so its handlers and saved order stay intact.
        const sorter = root.querySelector('.sort-selector');
        const filterButton = root.querySelector('.filter-button');
        const addLead = root.querySelector('.page-actions .primary-action');
        if (filterButton && addLead) {
            filterButton.classList.add('bsi-lead-header-filter');
            filterButton.setAttribute('aria-label', __('Filter'));
            addLead.before(filterButton);
            root.classList.add('bsi-filter-in-header');
        }
        if (sorter && filterButton && !listview._bsi_sort_in_filter) {
            const home = document.createElement('div');
            home.hidden = true;
            sorter.before(home);
            home.append(sorter);
            $(filterButton).on('shown.bs.popover.bsi_lead_sort', () => {
                const popover = document.getElementById(filterButton.getAttribute('aria-describedby'));
                const body = popover?.querySelector('.popover-body');
                if (!body) return;
                let row = body.querySelector('.bsi-lead-filter-sort');
                if (!row) {
                    row = document.createElement('div');
                    row.className = 'bsi-lead-filter-sort';
                    row.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 0 12px;margin:0 0 12px;border-bottom:1px solid #dfe7f2';
                    const label = document.createElement('span');
                    label.textContent = __('Sort by');
                    row.append(label);
                    body.prepend(row);
                }
                row.append(sorter);
                $(filterButton).popover('update');
            });
            $(filterButton).on('hide.bs.popover.bsi_lead_sort', () => home.append(sorter));
            listview._bsi_sort_in_filter = true;
        }
        const field = listview.page.fields_dict.status;
        if (isLead && field) {
            field.df.options = "\nOpen\nDelayed\nOpportunity\nDropped";
            field.refresh();
        }
    };
    if (isLead) settings.get_indicator = doc => {
        if (closed.includes(doc.status)) return [__(doc.status === "Opportunity" ? "Opportunity · Closed" : "Closed"), "green", "status,=," + doc.status];
        if (["Dropped", "Do Not Contact"].includes(doc.status)) return [__("Dropped"), "red", "status,=," + doc.status];
        const age = doc.creation ? moment().diff(frappe.datetime.convert_to_user_tz(doc.creation, false), 'hours', true) : 0;
        return doc.status === "Delayed" || (active.includes(doc.status) && age >= 24)
            ? [__("Delayed"), "orange", "status,=,Delayed"] : [__("Open"), "blue", "status,=," + doc.status];
    };
};
