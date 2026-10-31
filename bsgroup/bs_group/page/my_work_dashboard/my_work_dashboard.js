frappe.pages['my-work-dashboard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('My Dashboard'),single_column:true});
    const host = $('<div style="padding:24px"></div>').appendTo(page.main);
    const esc = frappe.utils.escape_html;
    const openList = dt => frappe.set_route('List',dt);
    async function refresh() {
        host.empty().append($('<p>').text(__('Loading your work…')));
        try {
            const response = await frappe.call('bsgroup.work_dashboard.data');
            host.empty().append($('<p class="text-muted">').text(__('Your accessible records · Updated just now')));
            const grid = $('<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px"></div>').appendTo(host);
            for (const card of response.message.cards) {
                const box = $('<section style="border:1px solid var(--border-color);border-radius:12px;padding:20px;background:var(--card-bg)"></section>').appendTo(grid);
                $('<h4>').text(__(card.doctype)).appendTo(box);
                $('<button class="btn btn-default" style="font-size:28px;font-weight:600;margin:8px 0"></button>').text(card.total).on('click',()=>openList(card.doctype)).appendTo(box);
                const statuses = $('<div style="display:flex;flex-wrap:wrap;gap:6px;margin:12px 0"></div>').appendTo(box);
                card.statuses.forEach(s=>$('<span class="badge"></span>').text(`${s.label || __('Not set')}: ${s.total}`).appendTo(statuses));
                $('<div class="text-muted" style="margin:12px 0 6px"></div>').text(__('Recently updated')).appendTo(box);
                for (const record of card.recent) {
                    $('<a style="display:block;padding:5px 0;overflow-wrap:anywhere"></a>').attr('href',frappe.utils.get_form_link(card.doctype,record.name)).text(record.name).appendTo(box);
                }
                if (!card.recent.length) $('<p class="text-muted">').text(__('No records yet')).appendTo(box);
                $('<button class="btn btn-sm btn-default" style="margin-top:12px"></button>').text(__('View all')).on('click',()=>openList(card.doctype)).appendTo(box);
            }
            if (!response.message.cards.length) host.append($('<p>').text(__('No accessible dashboard records.')));
        } catch (error) {
            host.empty().append($('<p>').text(__('Unable to load your dashboard. Please try Refresh.')));
        }
    }
    page.set_primary_action(__('Refresh'),refresh);
    wrapper.refresh_dashboard = refresh;
};
frappe.pages['my-work-dashboard'].on_page_show = wrapper => wrapper.refresh_dashboard();
