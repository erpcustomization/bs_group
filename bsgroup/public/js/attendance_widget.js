/* One attendance renderer for Desk Workspaces and bsgroup dashboard pages. */
(() => {
    if (window.bsAttendance) return;
    let data = null, fetched = 0, pending = null;
    const esc = value => frappe.utils.escape_html(String(value ?? ''));
    const mins = (a,b) => Math.max(0,Math.ceil((a-b)/60000));
    const duration = n => `${Math.floor(n/60)}h ${Math.floor(n%60)}m`;
    const clock = value => new Date(value).toLocaleTimeString('en-US',{timeZone:'Asia/Dubai',hour:'numeric',minute:'2-digit'});
    const time = value => new Date(value).getTime();
    const phrases = {sales:'update your quotations and follow-ups',projects:'update your tasks and timesheet',procurement:'update your PRs and POs',accounts:"post today's entries",helpdesk:'update your tickets and handovers'};
    function render(el, module) {
        if (!data?.visible) { el.hidden = true; return; }
        el.hidden = false;
        const a = data, now = Date.now(), start = time(a.shift_start), end = time(a.shift_end);
        const lunch = time(a.lunch_start), back = time(a.lunch_end), wrap = time(a.wrapup_start);
        let phase = now < start ? 'Before work' : now < lunch ? 'Focus time' : now < back ? 'Lunch break' : now < wrap ? 'Afternoon' : now < end ? 'Wrap up' : 'Day complete';
        let colour = 'teal', headline = 'Focus time – tackle your top priority.', target = lunch, label = 'until lunch';
        let badges = [];
        if (a.on_duty) badges.push(['ON DUTY','teal']);
        else if (a.first_in) badges.push([a.late_minutes ? `LATE · ${a.late_minutes} min` : 'ON TIME ✓',a.late_minutes ? 'amber':'teal']);
        if (now >= back) { headline = 'Back to it – keep the momentum.'; target=end; label='until finish'; }
        if (now >= lunch && now < back) { colour='grey'; headline=`Take a proper break – back at ${clock(a.lunch_end)}.`; target=back; label='until work resumes'; }
        if (now >= wrap && now < end) { colour='amber'; headline=`${mins(end,now)} minutes left – close your tasks and ${phrases[module] || 'update your records'} before you leave.`; }
        if (now < start) { headline=`Your day starts at ${clock(a.shift_start)} – check in on time.`; target=start; label='until start'; }
        if (now >= end) { headline='Day complete – please check out and leave 👋'; target=end; }
        if (!a.first_in && now >= start && now < end && !a.on_duty) { badges=[['NOT CHECKED IN','red']]; headline="You're late. Check in now."; colour='red'; }
        if (a.first_in && !a.checked_in) {
            phase='Checked out'; headline=`In ${clock(a.first_in)} · Out ${clock(a.last_out)} · ${duration(a.worked_minutes)}`;
            if (a.early_exit_minutes) badges.push([`LEFT EARLY · ${a.early_exit_minutes} min`,'amber']);
        }
        if (a.on_leave) { phase='On leave'; headline="You're on leave today."; badges=[]; }
        if (a.is_holiday) { phase='Day off'; headline='Enjoy your day off 🌴'; badges=[]; }
        const rest=a.on_leave || a.is_holiday, done=rest || (!!a.first_in && !a.checked_in);
        const percent = x => Math.max(0,Math.min(100,(x-start)/(end-start)*100));
        const marker=percent(now)*3.6;
        const timeline=[[start,'start'],[lunch,'lunch'],[wrap,'wrap-up'],[end,'finish']];
        let current=0; timeline.forEach(([value],i)=>{if(now>=value) current=i;});
        const sub = rest ? (a.is_holiday ? a.holiday_name : '') : a.first_in && !a.on_duty ? a.late_minutes ? 'You started late today – stay focused and be productive.' : 'Great start! Make the day count.' : '';
        el.innerHTML=`<div class="bs-att-ring" role="img" aria-label="${esc(done ? phase : duration(mins(target,now))+' '+label)}" style="--lunch:${percent(lunch)}%;--back:${percent(back)}%;--wrap:${percent(wrap)}%;--marker:${marker}deg"><span class="bs-att-now"></span><div><strong>${done ? (rest?'☀':'✓') : duration(mins(target,now))}</strong><small>${esc(done ? phase : label)}</small></div></div><div class="bs-att-content"><div class="bs-att-top"><span>Today’s attendance</span><span class="bs-att-badges">${badges.map(([text,tone])=>`<b class="bs-att-badge ${tone}">${esc(text)}</b>`).join('')}</span></div><div class="bs-att-phase ${colour}">${esc(phase.toUpperCase())}</div><h3>${esc(headline)}</h3>${sub?`<p>${esc(sub)}</p>`:''}<div class="bs-att-timeline">${timeline.map(([value,text],i)=>`<${i===current?'b':'span'}>${esc(clock(value))} ${text}</${i===current?'b':'span'}>`).join('<i>·</i>')}</div><small class="bs-att-foot">Dubai time · Come on time, work on time, go on time.</small></div>`;
    }
    async function refresh() {
        if (!data || Date.now()-fetched>=300000) {
            if (!pending) pending=frappe.call({method:'bsgroup.attendance_widget.get_today_status',quiet:true}).then(r=>{data=r.message;fetched=Date.now();}).catch(()=>{}).finally(()=>{pending=null;});
            await pending;
        }
        document.querySelectorAll('.bs-attendance-widget').forEach(el=>render(el,el.dataset.module));
    }
    function mount(parent,module='sales') {
        let el=parent.querySelector(':scope > .bs-attendance-widget');
        if (el) {
            if (el.dataset.module !== module) { el.dataset.module=module; render(el,module); }
            return el;
        }
        if (!el) { el=document.createElement('section');el.className='bs-attendance-widget';el.hidden=true;parent.prepend(el); }
        el.dataset.module=module; refresh(); return el;
    }
    function routeModule() {
        const route=(frappe.get_route?.()||[]).join('/').toLowerCase().replace(/^(workspaces?|dashboard-view)\//,'');
        if (route==='my-work-dashboard' && !frappe.boot?.bs_scoped_screens && (frappe.user_roles||[]).includes('Projects User')) return 'projects';
        if (/^(workspace\/)?(selling|bs sales)$|^(sales-management-das|presales-request-das|monthly-sales-entry|my-work-dashboard)$/.test(route)) return 'sales';
        if (/^(workspace\/)?(projects|bs project|projects, amc & ppm management)$/.test(route)) return 'projects';
        if (/^(workspace\/)?buying$|^bs-procurement/.test(route)) return 'procurement';
        if (/^(workspace\/)?accounting$/.test(route)) return 'accounts';
        if (/^(workspace\/)?(helpdesk|bs helpdesk)$|^hd-ticket-das$/.test(route)) return 'helpdesk';
        return null;
    }
    function mountDashboard(hero) {
        const stamp=hero?.querySelector('.bs-work-stamp');
        if (!stamp) return;
        let slot=hero.querySelector('.bs-hero-attendance');
        if (!slot) { slot=document.createElement('div');slot.className='bs-hero-attendance';hero.insertBefore(slot,stamp); }
        mount(slot,routeModule() || 'sales');
    }
    function scan() {
        const module=routeModule();
        const page=Array.from(document.querySelectorAll('.page-container')).find(el=>el.offsetParent!==null);
        const parent=page?.querySelector('.layout-main-section');
        if (!module) { parent?.querySelector(':scope > .bs-attendance-widget')?.remove(); return; }
        if ((frappe.get_route?.()||[]).includes('my-work-dashboard')) {
            parent?.querySelector(':scope > .bs-attendance-widget')?.remove();
            const hero=parent?.querySelector('.bs-work-hero');
            mountDashboard(hero);
            return;
        }
        if (parent) mount(parent,module);
    }
    window.bsAttendance={mount,refresh,mountDashboard};
    let timer;
    // Throttle instead of debouncing: chart/sidebar mutations must not keep
    // postponing initial attendance mounting on a full browser load.
    new MutationObserver(()=>{if(!timer) timer=setTimeout(()=>{timer=null;scan();},200);}).observe(document.body,{childList:true,subtree:true});
    frappe.router?.on('change',()=>setTimeout(scan,250));
    setInterval(()=>{if(!document.hidden){scan();refresh();}},60000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden){scan();refresh();}});
    scan();
    document.dispatchEvent?.(new Event('bs-attendance-ready'));
})();
