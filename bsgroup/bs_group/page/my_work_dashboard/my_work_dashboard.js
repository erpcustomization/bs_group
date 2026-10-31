frappe.pages['my-work-dashboard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('My Dashboard'),single_column:true});
    const host = $('<div class="bs-work"></div>').appendTo(page.main);
    const openList = dt => frappe.set_route('List',dt);
    async function refresh() {
        host.empty().append($('<div class="bs-work-empty" role="status">').text(__('Loading your workspace…')));
        try {
            const response = await frappe.call('bsgroup.work_dashboard.data');
            host.empty();
            const hero = $('<header class="bs-work-hero"></header>').appendTo(host);
            const intro = $('<div>').appendTo(hero);
            $('<div class="bs-work-eyebrow">').text(__('BITS SECURE · YOUR WORKSPACE')).appendTo(intro);
            $('<h2>').text(__('Your work, at a glance')).appendTo(intro);
            $('<p>').text(__('A clear view of your records, progress and recent activity.')).appendTo(intro);
            const stamp = $('<div class="bs-work-stamp">').appendTo(hero);
            $('<strong>').text(new Date().toLocaleDateString(undefined,{day:'numeric',month:'long',year:'numeric'})).appendTo(stamp);
            $('<span>').text(__('Updated just now')).appendTo(stamp);
            const section = $('<div class="bs-work-section">').appendTo(host);
            $('<h3>').text(__('Workspace overview')).appendTo(section);
            $('<span>').text(__('Showing records you have access to')).appendTo(section);
            const grid = $('<div class="bs-work-grid"></div>').appendTo(host);
            for (const card of response.message.cards) {
                const box = $('<section class="bs-work-card"></section>').appendTo(grid);
                const heading = $('<div class="bs-work-card-head">').appendTo(box);
                $('<span class="bs-work-icon" aria-hidden="true">').text(card.doctype.split(' ').map(s=>s[0]).slice(0,2).join('')).appendTo(heading);
                $('<h4>').text(__(card.doctype)).appendTo(heading);
                $('<button class="bs-work-total"></button>').attr('aria-label',__('Open {0}: {1} records',[card.doctype,card.total])).text(card.total.toLocaleString()).on('click',()=>openList(card.doctype)).appendTo(box);
                $('<div class="bs-work-count-label">').text(__('Accessible records')).appendTo(box);
                const statuses = $('<div class="bs-work-statuses"></div>').appendTo(box);
                card.statuses.forEach(s=>{
                    const label = !s.label || s.label === 'None' ? __('Not set') : __(s.label);
                    const badge = $('<span class="bs-work-status"></span>').text(`${label} · ${s.total}`).appendTo(statuses);
                    if (/completed|submitted|won|ordered|converted/i.test(label)) badge.addClass('good');
                    else if (/cancelled|lost|dropped/i.test(label)) badge.addClass('bad');
                    else if (/awaiting|draft|delayed|expired/i.test(label)) badge.addClass('warn');
                });
                const recent = $('<div class="bs-work-recent">').appendTo(box);
                $('<div class="bs-work-recent-title">').text(__('Recently updated')).appendTo(recent);
                for (const record of card.recent.slice(0,3)) {
                    const link = $('<a class="bs-work-record"></a>').attr('href',frappe.utils.get_form_link(card.doctype,record.name)).attr('title',record.name).appendTo(recent);
                    $('<span>').text(record.name).appendTo(link);
                    $('<span aria-hidden="true">').text('↗').appendTo(link);
                }
                if (!card.recent.length) $('<p class="text-muted">').text(__('No records yet')).appendTo(recent);
                $('<button class="bs-work-open"></button>').text(__('View all')+' →').on('click',()=>openList(card.doctype)).appendTo(box);
            }
            if (!response.message.cards.length) host.append($('<p>').text(__('No accessible dashboard records.')));
        } catch (error) {
            host.empty().append($('<div class="bs-work-empty" role="alert">').text(__('Unable to load your dashboard. Please try Refresh.')));
        }
    }
    page.set_primary_action(__('Refresh'),refresh);
    wrapper.refresh_dashboard = refresh;
};
frappe.pages['my-work-dashboard'].on_page_show = wrapper => wrapper.refresh_dashboard();
