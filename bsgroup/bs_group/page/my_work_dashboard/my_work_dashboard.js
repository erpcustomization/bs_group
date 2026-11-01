frappe.pages['my-work-dashboard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('My Dashboard'),single_column:true});
    const host = $('<div class="bs-work"></div>').appendTo(page.main);
    const controls = $('<div class="bs-work-month-controls"><label>Month <input type="month" aria-label="Dashboard month"></label></div>').insertBefore(host);
    const monthInput = controls.find('input');
    monthInput.val(frappe.datetime.get_today().slice(0,7));
    let requestId = 0;
    monthInput.on('change', () => { if (monthInput.val()) refresh(); });
    const openList = dt => frappe.set_route('List',dt);
    async function refresh() {
        const currentRequest = ++requestId;
        host.empty().append($('<div class="bs-work-empty" role="status">').text(__('Loading your workspace…')));
        try {
            const response = await frappe.call({method:'bsgroup.work_dashboard.data',args:{month:monthInput.val()}});
            if (currentRequest !== requestId) return;
            const data = response.message;
            host.empty();
            const hero = $('<header class="bs-work-hero"></header>').appendTo(host);
            const intro = $('<div>').appendTo(hero);
            $('<div class="bs-work-eyebrow">').text(__('BITS SECURE · YOUR WORKSPACE')).appendTo(intro);
            $('<h2>').text(__('Your month, at a glance')).appendTo(intro);
            $('<p>').text(__('Records created or last updated in the selected month.')).appendTo(intro);
            const stamp = $('<div class="bs-work-stamp">').appendTo(hero);
            $('<strong>').text(new Date(data.month+'-01T12:00:00').toLocaleDateString(undefined,{month:'long',year:'numeric'})).appendTo(stamp);
            $('<span>').text(__('Updated just now')).appendTo(stamp);

            const summary = $('<div class="bs-month-summary">').appendTo(host);
            const metrics = data.presales ? [
                ['open_requests','Open presales requests','All months · not yet handed to Sales'],
                ['pending_dcs','DCS in progress / delayed','All months · awaiting submission'],
                ['submitted','Submitted to Sales','Selected month · recorded DCS submissions']
            ] : [['created','Created'],['updated','Last updated'],['active','Records with activity']];
            metrics.forEach(([key,label,note])=>{
                const tile=$('<div class="bs-month-kpi">').appendTo(summary);
                $('<span>').text(__(label)).appendTo(tile);
                $('<strong>').text((data.presales || data.totals)[key].toLocaleString()).appendTo(tile);
                if (note) $('<small>').text(__(note)).css({color:'#60718b',fontSize:'11px'}).appendTo(tile);
            });
            const graph=$('<section class="bs-month-chart">').appendTo(host);
            $('<h3>').text(__('Records created each day')).appendTo(graph);
            const bars=$('<div class="bs-day-bars" role="img">').attr('aria-label',data.daily.map((n,i)=>`${i+1}: ${n}`).join('; ')).appendTo(graph);
            const max=Math.max(1,...data.daily);
            data.daily.forEach((n,i)=>{
                const bar=$('<div class="bs-day-column">').attr('title',`${data.month}-${String(i+1).padStart(2,'0')}: ${n} created`).appendTo(bars);
                $('<span class="bs-day-bar">').css('height',`${n ? Math.max(3,n/max*80) : 2}px`).toggleClass('empty',!n).appendTo(bar);
                $('<small>').text(i+1).appendTo(bar);
            });
            $('<p class="bs-month-note">').text(__('Current status of accessible records, not a historical month-end snapshot. Last updated counts use each record’s latest update; created and updated totals may overlap.')).appendTo(host);
            const section = $('<div class="bs-work-section">').appendTo(host);
            $('<h3>').text(__('Workspace overview')).appendTo(section);
            $('<span>').text(__('Selected month · current status · your permitted records')).appendTo(section);
            const grid = $('<div class="bs-work-grid"></div>').appendTo(host);
            for (const card of response.message.cards) {
                const box = $('<section class="bs-work-card"></section>').appendTo(grid);
                const heading = $('<div class="bs-work-card-head">').appendTo(box);
                $('<span class="bs-work-icon" aria-hidden="true">').text(card.doctype.split(' ').map(s=>s[0]).slice(0,2).join('')).appendTo(heading);
                $('<h4>').text(__(card.doctype)).appendTo(heading);
                $('<button class="bs-work-total"></button>').attr('aria-label',__('Open {0}: {1} records',[card.doctype,card.total])).text(card.total.toLocaleString()).on('click',()=>openList(card.doctype)).appendTo(box);
                $('<div class="bs-work-count-label">').text(`${card.created} created · ${card.updated} last updated`).appendTo(box);
                const breakdown=$('<div class="bs-status-chart" role="img">').attr('aria-label',card.statuses.map(s=>`${s.label}: ${s.total}`).join(', ') || 'No activity').appendTo(box);
                const palette=['#2363ad','#00a6b3','#8e74bf','#d6a64b','#7793b4','#b76d83'];
                card.statuses.forEach((s,i)=>$('<span>').css({width:`${s.total/Math.max(1,card.total)*100}%`,background:palette[i%palette.length]}).attr('title',`${s.label}: ${s.total}`).appendTo(breakdown));
                const details = $('<details class="bs-work-details">').appendTo(box);
                $('<summary>').text(__('Status & recent activity')).appendTo(details);
                const statuses = $('<div class="bs-work-statuses"></div>').appendTo(details);
                card.statuses.forEach(s=>{
                    const label = !s.label || s.label === 'None' ? __('Not set') : __(s.label);
                    const badge = $('<span class="bs-work-status"></span>').text(`${label} · ${s.total}`).appendTo(statuses);
                    if (/completed|submitted|won|ordered|converted/i.test(label)) badge.addClass('good');
                    else if (/cancelled|lost|dropped/i.test(label)) badge.addClass('bad');
                    else if (/awaiting|draft|delayed|expired/i.test(label)) badge.addClass('warn');
                });
                const recent = $('<div class="bs-work-recent">').appendTo(details);
                $('<div class="bs-work-recent-title">').text(__('Records with activity in this month')).appendTo(recent);
                for (const record of card.recent.slice(0,3)) {
                    const link = $('<a class="bs-work-record"></a>').attr('href',frappe.utils.get_form_link(card.doctype,record.name)).attr('title',record.name).appendTo(recent);
                    $('<span>').text(record.name).appendTo(link);
                    $('<span aria-hidden="true">').text('↗').appendTo(link);
                }
                if (!card.recent.length) $('<p class="text-muted">').text(__('No activity for this month')).appendTo(recent);
                $('<button class="bs-work-open"></button>').text(__('View all')+' →').on('click',()=>openList(card.doctype)).appendTo(box);
            }
            if (!response.message.cards.length) host.append($('<p>').text(__('No accessible dashboard records.')));
        } catch (error) {
            if (currentRequest !== requestId) return;
            host.empty().append($('<div class="bs-work-empty" role="alert">').text(__('Unable to load your dashboard. Please try Refresh.')));
        }
    }
    page.set_primary_action(__('Refresh'),refresh);
    wrapper.refresh_dashboard = refresh;
};
frappe.pages['my-work-dashboard'].on_page_show = wrapper => wrapper.refresh_dashboard();
