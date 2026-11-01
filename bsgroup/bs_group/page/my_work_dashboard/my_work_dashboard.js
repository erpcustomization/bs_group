frappe.pages['my-work-dashboard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('My Dashboard'),single_column:true});
    const host = $('<div class="bs-work"></div>').appendTo(page.main);
    const controls = $('<div class="bs-work-month-controls"><label>Month <input type="month" aria-label="Dashboard month"></label></div>').insertBefore(host);
    const monthInput = controls.find('input');
    const leaveButton = $('<button type="button" class="btn btn-primary btn-sm">').text(__('Apply for Leave')).hide().appendTo(controls);
    const leavePanel = $('<div class="bs-dashboard-leave">').insertAfter(controls);
    let leaveContext;
    const openLeave = name => frappe.set_route('Form', 'Leave Application', name);
    async function loadLeave() {
        const r = await frappe.call({method:'bsgroup.dashboard_leave.context',quiet:true});
        leaveContext = r.message;
        leaveButton.toggle(!!leaveContext?.can_create);
        leavePanel.empty();
        if (!leaveContext?.visible) return;
        const upcoming = leaveContext.requests.filter(x=>x.to_date>=leaveContext.today).sort((a,b)=>a.from_date.localeCompare(b.from_date));
        if (upcoming.length) {
            $('<strong>').text(__('Upcoming / current leave')).appendTo(leavePanel);
            upcoming.forEach(x=>$('<button type="button" class="btn btn-default btn-xs">')
                .text(`${x.from_date} – ${x.to_date} · ${x.leave_type} · ${x.status==='Approved' && x.docstatus===1?'Approved':'Pending'}`)
                .on('click',()=>openLeave(x.name)).appendTo(leavePanel));
        }
    }
    async function applyLeave(day) {
        try {
            await loadLeave();
            if (!leaveContext?.visible) return;
            const existing = day && leaveContext.requests.filter(x=>x.from_date<=day && x.to_date>=day);
            if (existing?.length) {
                const dialog = new frappe.ui.Dialog({title:__('Leave requests for {0}',[day]),fields:[{fieldname:'requests',fieldtype:'HTML'}]});
                existing.forEach(x=>$('<button type="button" class="btn btn-default btn-sm">').text(`${x.leave_type} · ${x.status==='Approved' && x.docstatus===1?'Approved':'Pending'}`)
                    .on('click',()=>{dialog.hide();openLeave(x.name);}).appendTo(dialog.fields_dict.requests.$wrapper));
                dialog.show();
                return;
            }
            if (!leaveContext.can_create) return frappe.msgprint(__('Please contact HR to request leave access.'));
            const start = day || frappe.datetime.get_today();
            const create = ()=>frappe.new_doc('Leave Application', {employee:leaveContext.employee,company:leaveContext.company,from_date:start,to_date:start});
            if (day) frappe.confirm(__('Apply for leave on {0}? You can change the dates in the leave form.',[frappe.datetime.str_to_user(day)]),create);
            else create();
        } catch (e) { frappe.msgprint(__('Leave details could not be loaded. Please try again.')); }
    }
    leaveButton.on('click',()=>applyLeave());
    monthInput.val(frappe.datetime.get_today().slice(0,7));
    let requestId = 0;
    monthInput.on('change', () => { if (monthInput.val()) refresh(); });
    const openList = dt => frappe.set_route('List',dt);
    // Support either load order: shared attendance script or dashboard first.
    document.addEventListener('bs-attendance-ready', () => {
        const hero=host[0].querySelector('.bs-work-hero');
        if (hero) window.bsAttendance?.mountDashboard(hero);
    });
    async function refresh() {
        loadLeave().catch(()=>{leaveButton.hide();leavePanel.text(__('Leave details could not be loaded. Please reload to try again.'));});
        const currentRequest = ++requestId;
        host.empty().append($('<div class="bs-work-empty" role="status">').text(__('Loading your workspace…')));
        try {
            const response = await frappe.call({method:'bsgroup.work_dashboard.data',args:{month:monthInput.val()}});
            if (currentRequest !== requestId) return;
            const data = response.message;
            host.empty();
            const hero = $('<header class="bs-work-hero"></header>').attr('data-month',data.month).appendTo(host);
            const intro = $('<div>').appendTo(hero);
            $('<div class="bs-work-eyebrow">').text(__('BITS SECURE · YOUR WORKSPACE')).appendTo(intro);
            $('<h2>').text(__('Your month, at a glance')).appendTo(intro);
            $('<p>').text(__('Records created or last updated in the selected month.')).appendTo(intro);
            const stamp = $('<div class="bs-work-stamp">').appendTo(hero);
            $('<strong>').text(new Date(data.month+'-01T12:00:00').toLocaleDateString(undefined,{month:'long',year:'numeric'})).appendTo(stamp);
            $('<span>').text(__('Updated just now')).appendTo(stamp);
            window.bsAttendance?.mountDashboard(hero[0]);

            const attendance=$('<section class="bs-month-attendance" aria-label="Monthly attendance">').appendTo(host);
            attendance.text(__('Loading monthly attendance…'));
            Promise.resolve(frappe.call({method:'bsgroup.monthly_attendance.get_month',args:{month:data.month},quiet:true})).then(r=>{
                if (currentRequest !== requestId) return;
                const a=r.message;
                if (!a?.visible) { attendance.remove(); return; }
                attendance.empty();
                $('<h3>').text(__('Attendance overview')+' · '+data.month+' · '+a.period).appendTo(attendance);
                const metrics=$('<div class="bs-att-month-metrics">').appendTo(attendance);
                const duration=n=>`${Math.floor(n/60)}h ${n%60}m`;
                [['on_time','On-time days'],['late','Late days'],['working_minutes','Working hours · 9–6'],['leave','Leave days'],['off','Off days'],['on_duty','On duty · outside office'],['no_checkin','Not checked in days']].forEach(([key,label])=>{
                    const tile=$('<div>').addClass('bs-att-month-'+key).appendTo(metrics);
                    $('<span>').text(__(label)).appendTo(tile);
                    $('<strong>').text(key==='working_minutes'?duration(a.totals[key]):a.totals[key]).appendTo(tile);
                });
                const days=$('<div class="bs-att-month-days" aria-label="Daily attendance">').appendTo(attendance);
                const labels={on_time:'On time',late:'Late',leave:'Leave',off:'Off',on_duty:'On duty / WFH',no_checkin:'No check-in',pending_checkout:'Check-in recorded; checkout pending (not counted as late)'};
                a.days.forEach(d=>$('<span role="button" tabindex="0">').addClass('bs-att-day-'+d.status).text(Number(d.date.slice(-2)))
                    .attr('title',`${d.date}: ${labels[d.status]} · ${duration(d.working_minutes)}${d.incomplete?' · Missing checkout':''}${d.holiday?' · '+d.holiday:''} · View or apply for leave`)
                    .attr('aria-label',`${d.date}: ${labels[d.status]}. View or apply for leave`)
                    .on('click',()=>applyLeave(d.date)).on('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();applyLeave(d.date);}}).appendTo(days));
                $('<p>').text(`9 AM–6 PM only · Recorded IN/OUT pairs; no overtime or assumed on-duty hours. ${a.totals.no_checkin} day(s) without check-in · ${a.totals.incomplete} missing checkout(s). Off days follow the HR holiday calendar.`).appendTo(attendance);
            }).catch(()=>{if(currentRequest===requestId) attendance.text(__('Attendance could not be loaded. Please reload the page.'));});

            const summary = $('<div class="bs-month-summary">').appendTo(host);
            const metrics = data.presales ? [
                ['open_requests','Open presales requests','All months · not yet handed to Sales'],
                ['pending_dcs','DCS in progress / delayed','All months · awaiting submission'],
                ['submitted','Submitted to Sales','Selected month · recorded DCS submissions']
            ] : data.sales ? [['quoted','Quoted'],['won','Won'],['lost','Lost']] : [['created','Created'],['updated','Last updated'],['active','Records with activity']];
            metrics.forEach(([key,label,note])=>{
                const tile=$('<div class="bs-month-kpi">').appendTo(summary);
                $('<span>').text(__(label)).appendTo(tile);
                if (data.sales) {
                    const metric=data.sales[key];
                    const amounts=Object.entries(metric.amounts);
                    $('<strong class="bs-sales-kpi-amount">').text(amounts.length ? amounts.map(([currency,value])=>`${currency} ${Number(value).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}`).join(' · ') : '0.00').appendTo(tile);
                    $('<small>').text(`${metric.count} quotation${metric.count===1?'':'s'} · ${key==='quoted'?'dated in selected month':'current outcome of month’s quotes'}`).css({color:'#60718b',fontSize:'10px'}).appendTo(tile);
                } else $('<strong>').text((data.presales || data.totals)[key].toLocaleString()).appendTo(tile);
                if (note) $('<small class="bs-kpi-note">').addClass(`bs-kpi-note-${key}`).text(__(note)).appendTo(tile);
            });
            const graph=$('<section class="bs-month-chart">').appendTo(host);
            $('<h3>').text(__('Records created each day')).appendTo(graph);
            const bars=$('<div class="bs-day-bars" role="img">').attr('aria-label',data.daily.map((n,i)=>`${i+1}: ${n}`).join('; ')).appendTo(graph);
            const max=Math.max(1,...data.daily);
            data.daily.forEach((n,i)=>{
                const bar=$('<div class="bs-day-column">').attr('title',`${data.month}-${String(i+1).padStart(2,'0')}: ${n} created`).appendTo(bars);
                $('<span class="bs-day-bar">').css('height',`${n ? Math.max(3,n/max*80) : 2}%`).toggleClass('empty',!n).appendTo(bar);
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
            host.empty().append($('<div class="bs-work-empty" role="alert">').text(__('Unable to load your dashboard. Please reload the page.')));
        }
    }
    page.clear_primary_action();
    wrapper.refresh_dashboard = refresh;
};
frappe.pages['my-work-dashboard'].on_page_show = wrapper => wrapper.refresh_dashboard();
