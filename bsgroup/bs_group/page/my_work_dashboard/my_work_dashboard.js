frappe.pages['my-work-dashboard'].on_page_load = function(wrapper) {
    if(frappe.session.user==='mohan@bitssecureit.com' || (frappe.session.user==='Administrator' && new URLSearchParams(location.search).get('executive_preview')==='1')) return bsChairmanDashboard(wrapper);
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('My Dashboard'),single_column:true});
    const host = $('<div class="bs-work"></div>').appendTo(page.main);
    const management = frappe.session.user === 'mohan@bitssecureit.com';
    let managementDay = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Dubai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
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
            if (day && (day < leaveContext.today || (day === leaveContext.today && leaveContext.today_locked))) return;
            const existing = day && leaveContext.requests.filter(x=>x.from_date<=day && x.to_date>=day);
            if (existing?.length) {
                const dialog = new frappe.ui.Dialog({title:__('Leave requests for {0}',[day]),fields:[{fieldname:'requests',fieldtype:'HTML'}]});
                existing.forEach(x=>$('<button type="button" class="btn btn-default btn-sm">').text(`${x.leave_type} · ${x.status==='Approved' && x.docstatus===1?'Approved':'Pending'}`)
                    .on('click',()=>{dialog.hide();openLeave(x.name);}).appendTo(dialog.fields_dict.requests.$wrapper));
                dialog.show();
                return;
            }
            if (!leaveContext.can_create) return frappe.msgprint(__('Please contact HR to request leave access.'));
            const start = day || leaveContext.today;
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
    function mountTeamOverview() {
        function numberDetails(element, title, rows, unavailable=false) {
            const items=rows || [];
            const empty=unavailable?'You do not have access to these records.':'No matching records for this number.';
            element.attr({title:`${title}\n${items.length?items.join('\n'):empty}\nClick to keep details open.`,role:'button',tabindex:0,'aria-label':`${title}: ${items.length} records. Show details`})
                .css({cursor:'pointer',textDecoration:'underline',textDecorationStyle:'dotted',textUnderlineOffset:'4px'});
            const show=()=>{
                const dialog=new frappe.ui.Dialog({title,fields:[{fieldname:'details',fieldtype:'HTML'}]});
                const content=dialog.fields_dict.details.$wrapper;
                $('<p>').text(`${managementDay} · ${items.length} matching record(s)`).appendTo(content);
                const list=$('<div>').css({maxHeight:'55vh',overflowY:'auto'}).appendTo(content);
                if(!items.length) $('<p>').text(empty).appendTo(list);
                items.forEach(item=>$('<div>').text(item).css({padding:'8px 0',borderBottom:'1px solid #e6edf5',whiteSpace:'normal',overflowWrap:'anywhere'}).appendTo(list));
                dialog.show();
            };
            element.on('click',show).on('keydown',event=>{
                if(event.key==='Enter'||event.key===' '){event.preventDefault();show();}
            });
            return element;
        }
        const section=$('<section class="bs-team-daily" aria-label="Daily team overview">').css({background:'#fff',border:'1px solid #dbe5f1',borderRadius:'12px',padding:'14px',marginBottom:'12px'}).appendTo(host);
        const heading=$('<div>').css({display:'flex',justifyContent:'space-between',alignItems:'center',gap:'12px',flexWrap:'wrap',marginBottom:'10px'}).appendTo(section);
        $('<h3>').text('Management overview').css({margin:0,fontSize:'16px'}).appendTo(heading);
        const label=$('<label>').text('Day ').css({margin:0}).appendTo(heading);
        const day=$('<input type="date" aria-label="Team overview date">').val(managementDay).css({border:'1px solid #cbd8e8',borderRadius:'6px',padding:'5px 8px'}).appendTo(label);
        const status=$('<p role="status">').css({fontSize:'12px',color:'#60718b',margin:'0 0 10px'}).appendTo(section);
        const grid=$('<div>').css({display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(145px,1fr))',gap:'10px'}).appendTo(section);
        const teamAttendance=$('<div aria-label="Employee attendance overview">').css({marginTop:'14px'}).appendTo(section);
        const contribution=$('<div>').css({marginTop:'12px',overflowX:'auto'}).appendTo(section);
        let sequence=0;
        async function load() {
            const request=++sequence;
            status.text('Loading team figures…');
            grid.empty();
            teamAttendance.empty();
            contribution.empty();
            try {
                const r=await frappe.call({method:'bsgroup.management_dashboard.daily',args:{day:managementDay},quiet:true});
                if(request!==sequence || !section[0].isConnected) return;
                const data=r.message;
                day.attr('max',data.today);
                status.text(`${data.day} · UAE team records you can access · Updated ${new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`);
                const cards=[
                    ['leads','Leads created','Created on this day','#eef4fc'],
                    ['opportunities','Opportunities created','Created on this day','#edf5ff'],
                    ['presales','Presales received','Requests created on this day','#e5f5f7'],
                    ['dcs','DCS in progress','Current outstanding drafts · all dates','#fff2da'],
                    ['quoted','Quoted value','Submitted quotations dated this day','#e9f3ff'],
                    ['won','Won value','Submitted quotations · recorded win date','#e3f5ed']
                ];
                for(const [key,title,note,color] of cards) {
                    const tile=$('<div>').css({background:color,borderRadius:'9px',padding:'12px',minWidth:0}).appendTo(grid);
                    $('<div>').text(title).css({fontSize:'12px',color:'#294867'}).appendTo(tile);
                    const metric=data[key];
                    let value=metric===null?'Unavailable':Number(metric).toLocaleString();
                    if(metric && typeof metric==='object') {
                        const amounts=Object.entries(metric.amounts);
                        value=amounts.length?amounts.map(([currency,amount])=>`${currency} ${Number(amount).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}`).join(' · '):'0.00';
                    }
                    numberDetails($('<strong>').text(value).css({display:'block',fontSize:'22px',lineHeight:'1.35',margin:'6px 0',overflowWrap:'anywhere',color:key==='won'?'#13754e':'#16365f'}).appendTo(tile),title,data.details?.[key],metric===null);
                    $('<small>').text(metric && typeof metric==='object'?`${metric.count} quotation(s) · ${note}`:note).css({display:'block',fontSize:'11px',color:'#526781'}).appendTo(tile);
                }
                const attendance=data.attendance;
                $('<h4>').text(`Employee attendance · ${attendance.day} · ${attendance.total} employees`).css({fontSize:'14px',margin:'0 0 8px'}).appendTo(teamAttendance);
                const attendanceGrid=$('<div>').css({display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(125px,1fr))',gap:'8px'}).appendTo(teamAttendance);
                const attendanceCards=[['on_time','On time','#e3f5ed'],['late','Late · IN/OUT recorded','#fff2da'],['pending_checkout','Late arrival · checkout pending','#fff2da'],['no_checkin','Not checked in','#ffe9e9'],['leave','On leave','#eef0ff'],['on_duty','On duty / WFH','#e5f5f7'],['off','Day off','#edf1f6'],['not_started','Shift not started','#edf1f6'],['partial_day','Half-day leave / duty','#eef0ff'],['unconfigured','Shift not assigned','#fff2da']];
                for(const [key,title,color] of attendanceCards) {
                    if(['not_started','partial_day','unconfigured'].includes(key) && !attendance.totals[key]) continue;
                    const tile=$('<div>').css({background:color,borderRadius:'8px',padding:'10px'}).appendTo(attendanceGrid);
                    $('<span>').text(title).css({fontSize:'11px',display:'block'}).appendTo(tile);
                    numberDetails($('<strong>').text(attendance.totals[key]).css({display:'inline-block',fontSize:'23px',color:key==='no_checkin'?'#b42318':'#16365f'}).appendTo(tile),title,attendance.details?.[key]);
                }
                $('<p>').text('Employee headcounts for the selected day. Actual check-ins only; manual Present records are excluded. Late arrivals awaiting checkout are shown separately. Approved leave, on-duty requests and holiday calendars are respected.').css({fontSize:'11px',color:'#60718b',margin:'8px 0 0'}).appendTo(teamAttendance);
                $('<h4>').text('Team contribution · selected day').css({fontSize:'13px',margin:'0 0 8px'}).appendTo(contribution);
                if(!data.people.length) $('<p>').text('No sales activity recorded for this day.').appendTo(contribution);
                else {
                    const table=$('<table class="table table-sm">').css({fontSize:'12px',marginBottom:0}).appendTo(contribution);
                    const head=$('<tr>').appendTo($('<thead>').appendTo(table));
                    ['Sales owner','Leads','Opportunities','Quoted value','Won value'].forEach(title=>$('<th>').text(title).appendTo(head));
                    const body=$('<tbody>').appendTo(table);
                    const money=metric=>Object.entries(metric.amounts).map(([currency,value])=>`${currency} ${Number(value).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}`).join(' · ') || '—';
                    data.people.forEach(person=>{
                        const row=$('<tr>').appendTo(body);
                        $('<td>').text(person.name).appendTo(row);
                        [['leads',person.leads],['opportunities',person.opportunities],['quoted',money(person.quoted)],['won',money(person.won)]].forEach(([key,value])=>numberDetails($('<td>').text(value).appendTo(row),`${person.name} · ${key}`,person.details?.[key]));
                    });
                }
                $('<p>').text('Quoted and won values include quotation taxes. Currencies are shown separately. Cancelled records are excluded; DCS workload shows the current position, even when viewing an earlier day.').css({fontSize:'11px',color:'#60718b',margin:'8px 0 0'}).appendTo(contribution);
            } catch(e) {
                if(request===sequence && section[0].isConnected) status.text('Unable to load team figures. Select a valid date or reload the page.');
            }
        }
        day.on('change',()=>{if(day.val()){managementDay=day.val();load();}});
        wrapper.refresh_team_overview=load;
        load();
    }
    if(management) setInterval(()=>{
        if(host[0].isConnected && host.is(':visible')) wrapper.refresh_team_overview?.();
    },300000);
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
            $('<h2>').text(__(management?'Company performance, at a glance':'Your month, at a glance')).appendTo(intro);
            $('<p>').text(__(management?'Daily sales activity and current costing workload.':'Records created or last updated in the selected month.')).appendTo(intro);
            const stamp = $('<div class="bs-work-stamp">').appendTo(hero);
            $('<strong>').text(new Date(data.month+'-01T12:00:00').toLocaleDateString(undefined,{month:'long',year:'numeric'})).appendTo(stamp);
            $('<span>').text(__('Updated just now')).appendTo(stamp);
            window.bsAttendance?.mountDashboard(hero[0]);
            if(management) mountTeamOverview();

            if(!management) {
            const attendance=$('<section class="bs-month-attendance" aria-label="Monthly attendance">').appendTo(host);
            attendance.text(__('Loading monthly attendance…'));
            Promise.resolve(frappe.call({method:'bsgroup.monthly_attendance.get_month',args:{month:data.month},quiet:true})).then(async r=>{
                await loadLeave();
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
                const labels={on_time:'On time',late:'Late',leave:'Leave',off:'Off',on_duty:'On duty / WFH',not_started:'Not started yet · starts at 9 AM',no_checkin:'No check-in',pending_checkout:'Check-in recorded; checkout pending (not counted as late)'};
                a.days.forEach(d=>{
                    const enabled=leaveContext?.can_create && d.date===leaveContext.today && !leaveContext.today_locked && ['no_checkin','not_started'].includes(d.status);
                    const label=`${d.date}: ${labels[d.status]}\nCheck-in: ${d.check_in || 'Not recorded'}\nCheck-out: ${d.check_out || 'Not recorded'}\nDubai time · ${duration(d.working_minutes)}${d.holiday?' · '+d.holiday:''} · ${enabled?'Apply for leave':'Locked · contact HR for corrections'}`;
                    const cell=$('<span>').addClass('bs-att-day-'+d.status).text(Number(d.date.slice(-2))).attr('title',label).attr('aria-label',label).appendTo(days);
                    if(enabled) cell.attr({role:'button',tabindex:'0'}).on('click',()=>applyLeave(d.date)).on('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();applyLeave(d.date);}});
                });
                $('<p>').text(`9 AM–6 PM only · Recorded IN/OUT pairs; no overtime or assumed on-duty hours. ${a.totals.no_checkin} day(s) without check-in · ${a.totals.incomplete} missing checkout(s). Off days follow the HR holiday calendar.`).appendTo(attendance);
            }).catch(()=>{if(currentRequest===requestId) attendance.text(__('Attendance could not be loaded. Please reload the page.'));});
            }

            const summary = $('<div class="bs-month-summary">').appendTo(host);
            if(management) summary.hide();
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

function bsChairmanDashboard(wrapper) {
    const page=frappe.ui.make_app_page({parent:wrapper,title:'Executive Overview',single_column:true});
    page.clear_primary_action();
    const root=$('<div class="bs-exec">').appendTo(page.main);
    const css=`
    .bs-exec{--ink:#152b41;--muted:#65778a;--line:#e1e8ef;--teal:#178579;--navy:#152f49;font-family:Inter,"Segoe UI",Arial,sans-serif;color:var(--ink);padding:4px 0 24px;line-height:1.5;font-weight:400;letter-spacing:normal;-webkit-font-smoothing:antialiased}
    .bs-exec *{box-sizing:border-box}.bs-exec button,.bs-exec input,.bs-exec select{font:inherit}.bs-exec button:focus-visible,.bs-exec input:focus-visible,.bs-exec select:focus-visible{outline:3px solid #66bdb2;outline-offset:3px}
    .bs-exec .ex-hero{background:linear-gradient(110deg,#10283e,#1d3d57);color:white;border-radius:16px;padding:25px 28px;display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:18px}
    .bs-exec .ex-eyebrow{font-size:11px;font-weight:600;letter-spacing:1.7px;text-transform:uppercase;color:#9fb9ca}.bs-exec h2{font-size:27px;font-weight:600;letter-spacing:-.7px;margin:5px 0 5px;color:inherit}.bs-exec .ex-subtitle{color:#bfd0dc;font-size:13px;margin:0}
    .bs-exec .ex-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.bs-exec .ex-controls label{margin:0;font-size:11px;color:#c1d0db}.bs-exec input,.bs-exec select{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:white;color:var(--ink);font-size:12px}
    .bs-exec .ex-button{border:1px solid var(--line);border-radius:8px;background:white;color:var(--ink);padding:8px 12px;cursor:pointer;font-size:12px;font-weight:600}.bs-exec .ex-update{font-size:11px;color:var(--muted);margin:0 0 12px;display:flex;gap:12px;justify-content:space-between;flex-wrap:wrap}.bs-exec .ex-live{color:#167667}.bs-exec .ex-live:before{content:'';display:inline-block;width:6px;height:6px;background:#21a18b;border-radius:50%;margin-right:6px}
    .bs-exec .ex-kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px;margin-bottom:16px}.bs-exec .ex-kpi{background:white;border:1px solid var(--line);border-radius:12px;padding:16px;min-width:0;box-shadow:0 3px 12px #16334e04}.bs-exec .ex-kpi.ex-featured{border-top:3px solid var(--teal);padding-top:14px}.bs-exec .ex-label{font-size:12px;color:#5a7085;font-weight:500}.bs-exec .ex-value{display:block;border:0;background:none;padding:0;color:var(--ink);font-size:27px;font-weight:600;letter-spacing:-.7px;line-height:1.2;margin:9px 0;cursor:pointer;text-align:left;max-width:100%;overflow-wrap:anywhere}.bs-exec .ex-value:hover{color:var(--teal)}.bs-exec .ex-unit{font-size:11px;color:var(--muted);font-weight:500;letter-spacing:.6px;display:block;margin-top:8px}.bs-exec .ex-note{font-size:11px;color:var(--muted);margin:5px 0 0}.bs-exec .ex-change{font-size:11px;color:#45677d;font-weight:500;margin-top:10px}
    .bs-exec .ex-grid{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);gap:16px;margin-bottom:16px}.bs-exec .ex-panel{background:white;border:1px solid var(--line);border-radius:12px;padding:20px;min-width:0}.bs-exec .ex-panel-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:16px}.bs-exec h3{font-size:15px;letter-spacing:-.2px;font-weight:600;margin:0}.bs-exec .ex-panel-head p{font-size:11px;color:var(--muted);margin:4px 0 0}.bs-exec .ex-tabs{display:flex;gap:3px;padding:3px;background:#f1f5f8;border-radius:8px}.bs-exec .ex-tabs button{border:0;border-radius:6px;background:transparent;color:var(--muted);padding:5px 9px;font-size:11px;cursor:pointer}.bs-exec .ex-tabs button.active{background:white;color:var(--ink);box-shadow:0 1px 4px #1f385418}
    .bs-exec .ex-chart{height:205px}.bs-exec .ex-chart svg{width:100%;height:100%;overflow:visible}.bs-exec .ex-legend{font-size:11px;color:var(--muted);display:flex;gap:16px}.bs-exec .ex-legend i{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px}.bs-exec .ex-chart-note{font-size:11px;min-height:20px;color:var(--muted);margin-top:8px}
    .bs-exec .ex-attendance{display:grid;grid-template-columns:126px minmax(0,1fr);gap:18px;align-items:center}.bs-exec .ex-donut{width:120px;height:120px;border-radius:50%;display:grid;place-items:center}.bs-exec .ex-donut-inner{width:90px;height:90px;background:white;border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center}.bs-exec .ex-donut strong{font-size:27px;font-weight:600;line-height:1.2}.bs-exec .ex-donut span{font-size:10px;color:var(--muted)}
    .bs-exec .ex-att-row{display:flex;align-items:center;gap:7px;font-size:11px;min-height:26px}.bs-exec .ex-dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}.bs-exec .ex-att-row button{margin-left:auto;border:0;background:#f2f6f8;min-width:29px;border-radius:5px;color:var(--ink);font-size:12px;font-weight:600;cursor:pointer}.bs-exec .ex-att-row button:hover{background:#e0efec}.bs-exec .ex-alert{background:#faf5ed;border-left:2px solid #b88a45;border-radius:0 6px 6px 0;padding:9px 11px;margin-top:14px;font-size:11px;color:#806232}
    .bs-exec .ex-table-wrap{overflow:auto}.bs-exec table{width:100%;border-collapse:collapse;font-size:12px}.bs-exec th{text-align:right;color:var(--muted);font-size:10px;letter-spacing:.6px;text-transform:uppercase;font-weight:600;border-bottom:1px solid var(--line);padding:9px 8px;white-space:nowrap}.bs-exec th:first-child{text-align:left}.bs-exec td{padding:12px 8px;border-bottom:1px solid #edf1f5;text-align:right;white-space:nowrap}.bs-exec td:first-child{text-align:left}.bs-exec tbody tr:last-child td{border:0}.bs-exec .ex-cell{border:0;background:none;color:#2b526c;padding:0;cursor:pointer;font-size:12px}.bs-exec .ex-cell:hover{text-decoration:underline}.bs-exec .ex-avatar{width:26px;height:26px;display:inline-grid;place-items:center;background:#edf3f7;border-radius:50%;font-size:10px;font-weight:600;color:#536d80;margin-right:8px}
    .bs-exec .ex-work-row{margin:13px 0}.bs-exec .ex-work-label{display:flex;justify-content:space-between;align-items:center;font-size:12px;margin-bottom:6px}.bs-exec .ex-track{height:6px;background:#eef3f6;border-radius:5px;overflow:hidden}.bs-exec .ex-track span{height:100%;display:block;background:#7393a8;border-radius:5px}.bs-exec .ex-wins{display:flex;gap:20px;align-items:center;border-top:1px solid var(--line);margin-top:16px;padding-top:14px}.bs-exec .ex-wins strong{font-size:23px;font-weight:600;color:var(--teal)}.bs-exec .ex-empty{color:var(--muted);padding:18px 0;font-size:12px}.bs-exec .ex-footer{font-size:10px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px}.bs-exec .ex-tooltip{position:fixed;background:#132d42;color:#fff;border-radius:10px;box-shadow:0 8px 30px #10263930;padding:12px 14px;max-width:400px;max-height:290px;overflow:hidden;z-index:1060;font-size:11px;pointer-events:none;line-height:1.7}.bs-exec .ex-tooltip strong{display:block;font-size:12px;margin-bottom:5px;color:#fff}.bs-exec .ex-tooltip small{display:block;color:#b6ccd8;margin-top:5px}
    @media(max-width:1100px){.bs-exec .ex-grid{grid-template-columns:1fr}.bs-exec .ex-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.bs-exec .ex-attendance{grid-template-columns:100px minmax(0,1fr);gap:12px}.bs-exec .ex-donut{width:96px;height:96px}.bs-exec .ex-donut-inner{width:72px;height:72px}.bs-exec .ex-donut strong{font-size:23px}}
    @media(max-width:850px){.bs-exec .ex-grid{grid-template-columns:1fr}.bs-exec .ex-hero{padding:20px;align-items:flex-start;flex-direction:column}.bs-exec .ex-attendance{grid-template-columns:120px minmax(0,1fr)}.bs-exec .ex-panel{padding:16px}.bs-exec h2{font-size:24px}}
    @media(max-width:480px){.bs-exec .ex-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.bs-exec .ex-kpi{padding:12px}.bs-exec .ex-value{font-size:23px}.bs-exec .ex-panel-head{flex-wrap:wrap}}
    `;
    $('<style>').text(css).appendTo(root);
    const hero=$('<header class="ex-hero">').appendTo(root);
    const intro=$('<div>').appendTo(hero);
    $('<div class="ex-eyebrow">').text('BITS SECURE  /  CHAIRMAN’S OFFICE').appendTo(intro);
    $('<h2>').text('The business, in focus.').appendTo(intro);
    $('<p class="ex-subtitle">').text('Commercial performance, execution and people — one clear view.').appendTo(intro);
    const controls=$('<div class="ex-controls">').appendTo(hero);
    const dayLabel=$('<label>').text('Reporting date ').appendTo(controls);
    const dayInput=$('<input type="date" aria-label="Executive reporting date">').appendTo(dayLabel);
    const refreshButton=$('<button class="ex-button" type="button">').text('↻ Refresh').appendTo(controls);
    const updated=$('<div class="ex-update" role="status" aria-live="polite">').appendTo(root);
    const content=$('<div>').appendTo(root);
    const tooltip=$('<div class="ex-tooltip" role="tooltip">').hide().appendTo(root);
    let day=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Dubai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    let sequence=0, mode='activity', currency='', payload;
    dayInput.val(day).attr('max',day);
    const number=value=>Number(value || 0).toLocaleString('en-US',{maximumFractionDigits:0});
    const money=value=>Number(value || 0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    const short=value=>Math.abs(value)>=1e6?(value/1e6).toFixed(1)+'m':Math.abs(value)>=1e3?(value/1e3).toFixed(0)+'k':number(value);
    const formatted=metric=>metric===null?'Unavailable':Object.entries(metric?.amounts || {}).map(([c,v])=>`${c} ${money(v)}`).join(' · ') || '—';
    function details(button,title,items,hoverTarget) {
        items=items || [];
        button.attr({'aria-label':`${title}. Show ${items.length} matching records.`});
        const hide=()=>tooltip.hide();
        const show=()=>{
            tooltip.empty();$('<strong>').text(title).appendTo(tooltip);
            items.slice(0,7).forEach(item=>$('<div>').text(item).appendTo(tooltip));
            if(!items.length) $('<div>').text('No matching records.').appendTo(tooltip);
            $('<small>').text(items.length>7?`+ ${items.length-7} more · click for the full list`:'Click to keep details open').appendTo(tooltip);
            const box=button[0].getBoundingClientRect();
            tooltip.css({left:Math.max(8,Math.min(box.left,window.innerWidth-410)),top:Math.max(8,Math.min(box.bottom+8,window.innerHeight-300))}).show();
        };
        if(hoverTarget) hoverTarget.on('mouseenter',show).on('mouseleave',hide);
        button.on('mouseenter focus',show).on('mouseleave blur',hide).on('click',()=>{
            hide();const dialog=new frappe.ui.Dialog({title,fields:[{fieldname:'records',fieldtype:'HTML'}]});
            const panel=dialog.fields_dict.records.$wrapper;
            $('<p>').text(`${day} · ${items.length} matching records`).appendTo(panel);
            const list=$('<div>').css({maxHeight:'55vh',overflow:'auto'}).appendTo(panel);
            if(!items.length) $('<p>').text('No matching records.').appendTo(list);
            items.forEach(item=>$('<div>').text(item).css({padding:'10px 0',borderBottom:'1px solid #e1e8ef',overflowWrap:'anywhere'}).appendTo(list));
            dialog.show();
        });
        return button;
    }
    function panel(parent,title,subtitle) {
        const box=$('<section class="ex-panel">').appendTo(parent), head=$('<div class="ex-panel-head">').appendTo(box), text=$('<div>').appendTo(head);
        $('<h3>').text(title).appendTo(text);$('<p>').text(subtitle).appendTo(text);
        return {box,head};
    }
    function delta(current,previous) {
        if(current===null || previous===null) return 'Comparison unavailable';
        const change=current-previous;
        if(!change) return 'No change vs prior day';
        if(!previous) return `${change>0?'+':''}${short(change)} vs prior day`;
        return `${change>0?'+':''}${(change/previous*100).toFixed(0)}% vs prior day`;
    }
    function render(data) {
        content.empty();tooltip.hide();
        const previous=data.series[data.series.length-2];
        const kpis=$('<div class="ex-kpis">').appendTo(content);
        const definitions=[['quoted','Quoted value','Submitted quotes · selected date'],['won','Won value','Recorded win date'],['leads','New leads','Created · selected date'],['opportunities','New opportunities','Created · selected date'],['presales','Presales received','Requests created · selected date'],['dcs','DCS in progress','Outstanding drafts · now']];
        definitions.forEach(([key,title,note])=>{
            const card=$('<section class="ex-kpi">').toggleClass('ex-featured',key==='quoted'||key==='won').appendTo(kpis);
            $('<div class="ex-label">').text(title).appendTo(card);
            if(key==='quoted'||key==='won') {
                const metric=data[key], amounts=Object.entries(metric?.amounts || {});
                const display=amounts.length?amounts:[[data.currencies[0]||'',0]];
                display.forEach(([c,value])=>{
                    $('<span class="ex-unit">').text(c || 'VALUE').appendTo(card);
                    details($('<button type="button" class="ex-value">').text(metric===null?'—':money(value)).appendTo(card),title,data.details[key]);
                    $('<div class="ex-change">').text(delta(metric===null?null:value,data.series_available[key]?(previous[key][c]||0):null)).appendTo(card);
                });
            } else {
                details($('<button type="button" class="ex-value">').text(data[key]===null?'—':number(data[key])).appendTo(card),title,data.details[key]);
                $('<div class="ex-change">').text(key==='dcs'?'Current workload':delta(data[key],data.series_available[key]?previous[key]:null)).appendTo(card);
            }
            $('<p class="ex-note">').text(note).appendTo(card);
        });
        const top=$('<div class="ex-grid">').appendTo(content);
        const trend=panel(top,'Business momentum','Seven days ending '+data.day+' · choose a day to explore');
        const tabs=$('<div class="ex-tabs" role="group" aria-label="Chart metric">').appendTo(trend.head);
        [['activity','Activity'],['value','Value']].forEach(([key,title])=>$('<button type="button">').text(title).toggleClass('active',mode===key).attr('aria-pressed',mode===key).on('click',()=>{mode=key;render(data);}).appendTo(tabs));
        if(mode==='value' && data.currencies.length>1) {
            const select=$('<select aria-label="Chart currency">').appendTo(trend.head);
            data.currencies.forEach(c=>$('<option>').val(c).text(c).appendTo(select));
            select.val(currency).on('change',()=>{currency=select.val();render(data);});
        }
        const keys=mode==='activity'?['leads','opportunities']:['quoted','won'];
        const labels=mode==='activity'?['Leads','Opportunities']:[`Quoted · ${currency}`,`Won · ${currency}`];
        const colors=['#315b7a','#198578'];
        const legend=$('<div class="ex-legend">').appendTo(trend.box);
        labels.forEach((label,i)=>{const item=$('<span>').appendTo(legend);$('<i>').css('background',colors[i]).appendTo(item);item.append(document.createTextNode(label));});
        const chart=$('<div class="ex-chart">').appendTo(trend.box);
        const chartNote=$('<div class="ex-chart-note" aria-live="polite">').text('Hover a bar for exact figures. Click a day to update the overview.').appendTo(trend.box);
        const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 600 210');svg.setAttribute('role','group');svg.setAttribute('aria-label','Seven day '+mode+' trend');chart.append(svg);
        const add=(tag,attrs,text)=>{const e=document.createElementNS(svg.namespaceURI,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,String(v)));if(text!==undefined)e.textContent=text;svg.appendChild(e);return e;};
        const val=(point,key)=>mode==='activity'?point[key]:(point[key][currency]||0);
        const rawMax=Math.max(1,...data.series.flatMap(p=>keys.map(k=>val(p,k))));
        const max=mode==='activity'?Math.ceil(rawMax/2)*2:rawMax;
        [0,.5,1].forEach(f=>{add('line',{x1:45,x2:590,y1:168-f*132,y2:168-f*132,stroke:'#e7edf2','stroke-dasharray':f?'3 4':'0'});add('text',{x:36,y:172-f*132,'text-anchor':'end',fill:'#8192a1','font-size':10},short(max*f));});
        data.series.forEach((point,i)=>{
            const x=65+i*75;
            const group=add('g',{tabindex:0,role:'button','aria-label':`${point.day}: ${labels.map((l,j)=>l+' '+number(val(point,keys[j]))).join(', ')}. Open date.`,style:'cursor:pointer'});
            const hit=document.createElementNS(svg.namespaceURI,'rect');Object.entries({x:x-15,y:20,width:65,height:178,fill:'transparent'}).forEach(([k,v])=>hit.setAttribute(k,v));group.appendChild(hit);
            keys.forEach((key,j)=>{
                const value=val(point,key), height=value/max*132;
                const bar=document.createElementNS(svg.namespaceURI,'rect');Object.entries({x:x+j*22,y:168-Math.max(2,height),width:16,height:Math.max(2,height),rx:3,fill:colors[j],opacity:value?1:.18}).forEach(([k,v])=>bar.setAttribute(k,v));group.appendChild(bar);
            });
            add('text',{x:x+19,y:191,'text-anchor':'middle',fill:point.day===data.day?'#152b41':'#8192a1','font-size':11,'font-weight':point.day===data.day?600:400},new Date(point.day+'T12:00:00').toLocaleDateString('en-GB',{day:'numeric',month:'short'}));
            const describe=()=>chartNote.text(`${point.day} · ${labels.map((l,j)=>`${l}: ${mode==='value'?money(val(point,keys[j])):number(val(point,keys[j]))}`).join(' · ')}`);
            group.addEventListener('mouseenter',describe);group.addEventListener('focus',describe);
            const select=()=>{day=point.day;dayInput.val(day);refresh();};group.addEventListener('click',select);group.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});
        });
        if(keys.some(k=>!data.series_available[k])) chartNote.text('Some metrics are unavailable under current permissions.');
        const att=data.attendance;
        const attendance=panel(top,'People & attendance',`${att.total} employees · ${data.day}`);
        const layout=$('<div class="ex-attendance">').appendTo(attendance.box);
        const categories=[['on_time','On time','#198578'],['late','Late · IN/OUT complete','#b78c49'],['pending_checkout','Late · awaiting checkout','#d3b587'],['no_checkin','Not checked in','#b16c65'],['leave','On leave','#8b9aad'],['on_duty','On duty / WFH','#6292ac'],['off','Day off','#c9d3dd'],['not_started','Shift not started','#dfe5eb'],['partial_day','Half-day leave / duty','#a5adbc'],['unconfigured','Shift not assigned','#879099']];
        let position=0;const stops=[];categories.forEach(([key,label,color])=>{const end=position+(att.total?att.totals[key]/att.total*100:0);if(end>position)stops.push(`${color} ${position}% ${end}%`);position=end;});
        const ring=$('<div class="ex-donut" role="img">').attr('aria-label',categories.map(([k,l])=>`${l}: ${att.totals[k]}`).join(', ')).css('background',stops.length?`conic-gradient(${stops.join(',')})`:'#edf1f5').appendTo(layout);
        const center=$('<div class="ex-donut-inner">').appendTo(ring);$('<strong>').text(number(att.totals.on_time+att.totals.late+att.totals.pending_checkout)).appendTo(center);$('<span>').text('arrivals counted').appendTo(center);
        const rows=$('<div>').appendTo(layout);
        categories.forEach(([key,label,color])=>{
            if(!att.totals[key] && !['on_time','late','pending_checkout','no_checkin','leave','on_duty'].includes(key))return;
            const row=$('<div class="ex-att-row">').appendTo(rows);$('<span class="ex-dot">').css('background',color).appendTo(row);$('<span>').text(label).appendTo(row);details($('<button type="button">').text(att.totals[key]).appendTo(row),label,att.details[key],row);
        });
        if(att.totals.no_checkin || att.totals.unconfigured) $('<div class="ex-alert">').text(`${att.totals.no_checkin} without check-in · ${att.totals.unconfigured} missing shift assignments`).appendTo(attendance.box);
        $('<p class="ex-note">').text('Actual punches only. Manual Present records excluded. Late arrivals without checkout are separated.').appendTo(attendance.box);
        const bottom=$('<div class="ex-grid">').appendTo(content);
        const team=panel(bottom,'Team performance','Contribution by sales owner · selected day');
        if(!data.people.length) $('<p class="ex-empty">').text('No sales activity recorded for this day. Choose another date to review performance.').appendTo(team.box);
        else {
            const table=$('<table>').appendTo($('<div class="ex-table-wrap">').appendTo(team.box));
            const heading=$('<tr>').appendTo($('<thead>').appendTo(table));['Sales owner','Leads','Opps','Quoted','Won'].forEach(text=>$('<th>').text(text).appendTo(heading));
            const body=$('<tbody>').appendTo(table);
            data.people.forEach(person=>{
                const row=$('<tr>').appendTo(body), name=$('<td>').appendTo(row);$('<span class="ex-avatar" aria-hidden="true">').text(person.name.split(' ').map(x=>x[0]).slice(0,2).join('')).appendTo(name);name.append(document.createTextNode(person.name));
                [['leads',number(person.leads)],['opportunities',number(person.opportunities)],['quoted',formatted(person.quoted)],['won',formatted(person.won)]].forEach(([key,value])=>details($('<button type="button" class="ex-cell">').text(value).appendTo($('<td>').appendTo(row)),`${person.name} · ${key}`,person.details[key]));
            });
        }
        const workload=panel(bottom,'Costing execution','Current outstanding DCS · age since creation');
        const largest=Math.max(1,...data.dcs_age.map(x=>x.count));
        data.dcs_age.forEach(bucket=>{
            const row=$('<div class="ex-work-row">').appendTo(workload.box), label=$('<div class="ex-work-label">').appendTo(row);$('<span>').text(bucket.label).appendTo(label);details($('<button type="button" class="ex-cell">').text(bucket.count+' DCS').appendTo(label),bucket.label+' · outstanding DCS',bucket.details);
            $('<span>').css({width:`${bucket.count/largest*100}%`,background:bucket.label==='Over 30 days'?'#b09161':'#7393a8'}).appendTo($('<div class="ex-track">').appendTo(row));
        });
        if(data.dcs===null) $('<p class="ex-empty">').text('Costing data is unavailable under current permissions.').appendTo(workload.box);
        const wins=$('<div class="ex-wins">').appendTo(workload.box);details($('<button type="button" class="ex-cell">').append($('<strong>').text(data.won?.count || 0)).appendTo(wins),'Daily wins',data.details.won);const winText=$('<div>').appendTo(wins);$('<h3>').text('Wins recorded').appendTo(winText);$('<p class="ex-note">').text(data.won?.count?formatted(data.won):'No submitted quotations marked won on this date.').appendTo(winText);
        $('<footer class="ex-footer">').text('Dubai time · Existing company access applies · Values include quotation taxes; currencies stay separate · Comparisons are against the previous calendar day, not the same elapsed hours · Historic dates show current record outcomes; costing workload is live · Refreshes every 5 minutes').appendTo(content);
    }
    async function refresh() {
        const request=++sequence;tooltip.hide();refreshButton.prop('disabled',true);updated.text('Updating executive overview…');
        if(!payload) content.html('<div class="ex-panel ex-empty">Loading company performance…</div>');
        try {
            const response=await frappe.call({method:'bsgroup.management_dashboard.executive',args:{day},quiet:true});
            if(request!==sequence)return;
            payload=response.message;dayInput.attr('max',payload.today);
            if(!payload.currencies.includes(currency)) currency=payload.currencies[0]||'';
            updated.empty();$('<span>').text(`UAE company overview · ${day}`).appendTo(updated);$('<span class="ex-live">').text('Updated '+new Date().toLocaleTimeString('en-GB',{timeZone:'Asia/Dubai',hour:'2-digit',minute:'2-digit'})+' GST · Auto-refresh on').appendTo(updated);
            render(payload);
        } catch(error) {
            if(request===sequence){content.empty();$('<div class="ex-panel ex-empty" role="alert">').text('The overview could not be loaded. Check the selected date and select Refresh to try again.').appendTo(content);updated.text('Update unsuccessful · figures are unavailable.');}
        } finally {if(request===sequence)refreshButton.prop('disabled',false);}
    }
    dayInput.on('change',()=>{if(dayInput.val()){day=dayInput.val();refresh();}});refreshButton.on('click',refresh);
    wrapper.refresh_dashboard=refresh;
    setInterval(()=>{if(root[0].isConnected && root.is(':visible') && !document.hidden)refresh();},300000);
}
