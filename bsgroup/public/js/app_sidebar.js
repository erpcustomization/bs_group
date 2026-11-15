/* Scope the shared BS sidebar to the current app. Never add permissioned links. */
(() => {
    const groups = {
        'BS Sales': [],
        'BS User Management': [],
        'BS Project': ['BS Project','BS Project Support','BS Supply Projects','BS ELV Projects','BS Infra Projects','BS 3CX Projects'],
        ...Object.fromEntries(['BS HR','BS Helpdesk','BS Approvals','BS Procurement','BS AMC','BS PPM','BS Support'].map(x=>[x,[x]])),
    };
    function appForSection(section) {
        return Object.keys(groups).find(app=>groups[app].includes(section)) || 'BS Sales';
    }
    function appForRow(row) {
        if(row.classList.contains('section-item')) return appForSection(row.dataset.id);
        // Native workspace navigation can render these as top-level links.
        return ['Site Survey Request','Delivery Request','Project','Task Summary Report',
            'Task Scheduler Report','Tech Task Scheduler Report'].includes(row.dataset.id)
            ? 'BS Project' : 'BS Sales';
    }
    function routeMatches(current, target) {
        const normalize = path=>decodeURIComponent(path).replace(/^\/desk\/bs-group\//,'/desk/').replace(/\/$/,'');
        const path=normalize(current.pathname), base=normalize(target.pathname);
        return (path===base || path.startsWith(base+'/')) && [...target.searchParams].every(([k,v])=>current.searchParams.get(k)===v);
    }
    function chooseApp(current, candidates, previous) {
        const explicit=current.searchParams.get('bs_app');
        if(groups[explicit]) return explicit;
        const matches=candidates.filter(x=>routeMatches(current,new URL(x.href,current.origin)));
        if(matches.length) {
            matches.sort((a,b)=>b.href.length-a.href.length);
            const best=matches.filter(x=>x.href.length===matches[0].href.length);
            return best.find(x=>x.app===previous)?.app || best[0].app;
        }
        return groups[previous] ? previous : 'BS Sales';
    }
    function isDashboard(path) {
        return /^\/desk\/(?:bs-group\/)?my-work-dashboard\/?$/.test(path);
    }
    function dashboardLinks(destinations) {
        return [
            {label:'Dashboard',href:'/desk/my-work-dashboard'},
            {label:'All apps',href:'/desk'},
            ...Object.entries(destinations || {}).filter(([app,path])=>groups[app] && typeof path==='string' && path.startsWith('/desk/'))
                .map(([app,path])=>({label:app==='BS Project'?'BS Project Support':app,
                    href:path+(path.includes('?')?'&':'?')+'bs_app='+encodeURIComponent(app)})),
        ];
    }
    if(typeof module!=='undefined' && module.exports) {module.exports={groups,appForSection,routeMatches,chooseApp,isDashboard,dashboardLinks};return;}
    if(window.top!==window.self || window.bsAppSidebarInstalled) return;
    window.bsAppSidebarInstalled=true;
    const key='bs-sidebar-app:'+frappe.session.user;
    let previous, scheduled=false;
    try { previous=sessionStorage.getItem(key); } catch (_) {}
    const style=document.createElement('style');
    style.textContent='.bs-app-unrelated,.bs-dashboard-hidden{display:none!important}';
    document.head.append(style);
    function update() {
        scheduled=false;
        const current=new URL(location.href);
        const dashboard=isDashboard(current.pathname);
        for(const host of document.querySelectorAll('.body-sidebar .sidebar-items, .desk-sidebar .sidebar-items')) {
            let nav=host.querySelector('.bs-dashboard-modules');
            if(dashboard && frappe.boot.bs_work_dashboard) {
                if(!nav) {
                    nav=document.createElement('div');
                    nav.className='bs-dashboard-modules';
                    for(const item of dashboardLinks(frappe.boot.bs_app_destinations)) {
                        const row=document.createElement('div'), link=document.createElement('a');
                        row.className='standard-sidebar-item';
                        link.className='item-anchor';
                        link.href=item.href;
                        link.textContent=__(item.label);
                        row.append(link);nav.append(row);
                    }
                    host.prepend(nav);
                }
                for(const row of host.children) row.classList.toggle('bs-dashboard-hidden',row!==nav);
            } else {
                if(nav) nav.remove();
                for(const row of host.children) row.classList.remove('bs-dashboard-hidden');
            }
        }
        if(dashboard) return;
        for(const sidebar of document.querySelectorAll('.body-sidebar[data-title="BS Group"]')) {
            const host=sidebar.querySelector('.sidebar-items');
            if(!host) continue;
            if(!host.querySelector('.bs-all-apps')) {
                const row=document.createElement('div');
                row.className='standard-sidebar-item bs-all-apps';
                const link=document.createElement('a');
                link.className='item-anchor';
                link.href='/desk';
                link.textContent=__('All apps');
                row.append(link);
                host.prepend(row);
            }
            const rows=[...host.children], candidates=[];
            for(const row of rows) {
                if(row.classList.contains('bs-personal-dashboard') || row.classList.contains('bs-all-apps')) continue;
                const app=appForRow(row);
                for(const link of row.querySelectorAll('a[href]')) candidates.push({app,href:link.getAttribute('href')});
            }
            const active=chooseApp(current,candidates,previous);
            previous=active;
            try { sessionStorage.setItem(key,active); } catch (_) {}
            for(const row of rows) {
                const app=appForRow(row);
                row.classList.toggle('bs-app-unrelated',!row.classList.contains('bs-personal-dashboard') && !row.classList.contains('bs-all-apps') && app!==active);
            }
            const title=sidebar.querySelector('.sidebar-header .header-title');
            const displayTitle=active==='BS Project'?'BS Project Support':active;
            if(title && title.textContent!==displayTitle) title.textContent=displayTitle;
        }
    }
    function schedule() {if(!scheduled){scheduled=true;setTimeout(update,50);}}
    new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
    frappe.router.on('change',schedule);
    update();
})();
