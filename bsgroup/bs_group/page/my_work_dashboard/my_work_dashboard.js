frappe.pages['my-work-dashboard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('My Dashboard'),single_column:true});
    const host = $('<div class="bs-work"></div>').appendTo(page.main);
    const controls = $('<div class="bs-work-month-controls"><label>Month <input type="month" aria-label="Dashboard month"></label></div>').insertBefore(host);
    const monthInput = controls.find('input');
    monthInput.val(frappe.datetime.get_today().slice(0,7));
    let requestId = 0;
    monthInput.on('change', () => { if (monthInput.val()) refresh(); });
    const openList = dt => frappe.set_route('List',dt);
    const duration = n => `${Math.floor(n/60)}h ${n%60}m`;
    async function attendance() {
        const target=host.find('.bs-today-attendance');
        if (!target.length || !target.is(':visible')) return;
        try {
            const response=await frappe.call('bsgroup.dashboard_attendance.today');
            if (!target[0].isConnected) return;
            const a=response.message;
            target.empty();
            $('<h3>').text(__('Today’s attendance')).appendTo(target);
            $('<p class="bs-month-note">').text(__('9:00 AM–6:00 PM · Dubai time · attendance check-ins')).appendTo(target);
            if (a.remaining_minutes !== undefined) {
                const clock=$('<div class="bs-workday-clock">').toggleClass('wrap-up',a.remaining_minutes<=30).appendTo(target);
                const ring=$('<div class="bs-clock-ring" role="img">').attr('aria-label',`${duration(a.remaining_minutes)} remaining until 6 PM`).css('--day-progress',`${Math.max(0,Math.min(100,(540-a.remaining_minutes)/540*100))}%`).appendTo(clock);
                const face=$('<div class="bs-clock-face">').appendTo(ring);
                $('<span class="bs-clock-symbol" aria-hidden="true">').text('◷').appendTo(face);
                $('<strong>').text(duration(a.remaining_minutes)).appendTo(face);
                $('<small>').text(__('remaining')).appendTo(face);
                const text=$('<div class="bs-clock-copy">').appendTo(clock);
                $('<h4>').text(a.remaining_minutes===0 ? __('Workday complete') : a.remaining_minutes<=30 ? __('Time to wrap up') : __('Make the rest of today count')).appendTo(text);
                $('<p>').text(a.remaining_minutes===0 ? __('Your 6:00 PM working window has ended.') : a.remaining_minutes<=30 ? __('Finish priority tasks, update their status, and prepare to close your day.') : __('Time remaining until 6:00 PM. Focus on your next priority.')).appendTo(text);
                $('<small>').text(__('9:00 AM start · 5:30 PM wrap-up · 6:00 PM finish')).appendTo(text);
            }
            if (['unlinked','ambiguous'].includes(a.state)) {
                $('<p>').text(a.state==='unlinked' ? __('No active Employee profile is linked to your account.') : __('More than one Employee profile is linked. HR needs to confirm the correct profile.')).appendTo(target);
                return;
            }
            if (!a.check_in) {
                $('<p>').text(__('No attendance check-in recorded today.')).appendTo(target);
                return;
            }
            const grid=$('<div class="bs-attendance-grid">').appendTo(target);
            const cells=[['Check-in',a.check_in],['Arrival',a.late_minutes ? `${a.late_minutes} minutes late` : 'On time'],['Working time so far',duration(a.worked_minutes)],['Available from arrival to 6 PM',duration(a.available_minutes)]];
            cells.forEach(([label,value])=>{const cell=$('<div>').appendTo(grid);$('<small>').text(__(label)).appendTo(cell);$('<strong>').text(value).appendTo(cell);});
            const note=a.checked_in ? `${duration(a.remaining_minutes)} until 6 PM · projected working time ${duration(a.projected_minutes)} if you remain checked in.` : a.check_out ? `Last check-out: ${a.check_out}.` : 'The 6 PM working window has ended.';
            $('<p class="bs-month-note">').text(note+' Recorded OUT–IN breaks are excluded. Time is limited to 9 AM–6 PM.').appendTo(target);
            if(a.unknown_logs) $('<p class="bs-month-note">').text(__('Some punches have no IN/OUT type; these are excluded from this estimate.')).appendTo(target);
        } catch(error) {
            target.empty().append($('<p>').text(__('Attendance is unavailable. Please try Refresh.')));
        }
    }
    setInterval(attendance,60000);
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
            $('<section class="bs-today-attendance bs-month-chart">').text(__('Loading today’s attendance…')).appendTo(host);
            attendance();
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
                $('<span class="bs-day-bar">').css('height',`${n ? Math.max(3,n/max*110) : 2}px`).toggleClass('empty',!n).appendTo(bar);
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
                const statuses = $('<div class="bs-work-statuses"></div>').appendTo(box);
                card.statuses.forEach(s=>{
                    const label = !s.label || s.label === 'None' ? __('Not set') : __(s.label);
                    const badge = $('<span class="bs-work-status"></span>').text(`${label} · ${s.total}`).appendTo(statuses);
                    if (/completed|submitted|won|ordered|converted/i.test(label)) badge.addClass('good');
                    else if (/cancelled|lost|dropped/i.test(label)) badge.addClass('bad');
                    else if (/awaiting|draft|delayed|expired/i.test(label)) badge.addClass('warn');
                });
                const recent = $('<div class="bs-work-recent">').appendTo(box);
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
