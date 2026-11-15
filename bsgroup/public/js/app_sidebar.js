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
        return /^\/desk\/(?:[^/]+\/)?my-work-dashboard\/?$/.test(path);
    }
    function dashboardLinks(destinations, supportLinks=[]) {
        return [
            {label:'Dashboard',href:'/desk/my-work-dashboard'},
            {label:'All apps',href:'/desk'},
            ...Object.entries(destinations || {}).filter(([app,path])=>groups[app] && typeof path==='string' && path.startsWith('/desk/'))
                .flatMap(([app,path])=>[
                    {label:app==='BS Project'?'BS Project Support':app,
                        href:path+(path.includes('?')?'&':'?')+'bs_app='+encodeURIComponent(app),
                        ...(app==='BS Project' && supportLinks.length ? {children:supportLinks.filter(x=>typeof x.href==='string' && x.href.startsWith('/desk/'))} : {})},
                    // Project is the first server destination only when Project read
                    // is allowed. A Task/Timesheet-only fallback must not add these.
                    ...(app==='BS Project' && path==='/desk/bs-group/project'
                        ? [['supply','Supply'],['3cx','3CX'],['infra','Infra'],['elv','ELV']].map(([key,label])=>({
                            label:label+' Projects',children:['Projects','AMC'].map(section=>({
                                label:section,href:'/desk/bs-group/bs-project-modules?bs_module='+key+
                                    '&bs_section='+section.toLowerCase()+'&bs_app=BS%20Project',
                            })),
                        })) : []),
                ]),
        ];
    }
    function persistentMenu(current, privateSidebar) {
        if(isDashboard(current.pathname)) return 'all';
        if(current.searchParams.get('bs_app')==='BS Project' ||
            /^\/desk\/(?:[^/]+\/)?(?:bs-project-modules|project|task|timesheet|tech-task-scheduler|delivery-request|site-survey-request)(?:\/|$)/.test(current.pathname)) return 'projects';
        return privateSidebar ? 'all' : null;
    }
    if(typeof module!=='undefined' && module.exports) {module.exports={groups,appForSection,routeMatches,chooseApp,isDashboard,dashboardLinks,persistentMenu};return;}
    if(window.top!==window.self || window.bsAppSidebarInstalled) return;
    window.bsAppSidebarInstalled=true;
    const key='bs-sidebar-app:'+frappe.session.user;
    let previous, scheduled=false;
    try { previous=sessionStorage.getItem(key); } catch (_) {}
    const style=document.createElement('style');
    style.textContent='.bs-app-unrelated,.bs-dashboard-hidden{display:none!important}'+
        '.bs-dashboard-category{margin:10px 0 5px}.bs-dashboard-category-title{font-weight:600;padding:5px 12px}'+
        '.bs-dashboard-category .standard-sidebar-item{margin-left:12px}';
    document.head.append(style);
    function update() {
        scheduled=false;
        const current=new URL(location.href);
        const dashboard=isDashboard(current.pathname);
        for(const host of document.querySelectorAll('.body-sidebar .sidebar-items, .desk-sidebar .sidebar-items')) {
            const mode=persistentMenu(current,host.closest('.body-sidebar')?.dataset.title==='Private');
            let nav=host.querySelector('.bs-dashboard-modules');
            if(nav && nav.dataset.mode!==mode) {nav.remove();nav=null;}
            if(mode && frappe.boot.bs_work_dashboard) {
                if(!nav) {
                    nav=document.createElement('div');
                    nav.className='bs-dashboard-modules';
                    nav.dataset.mode=mode;
                    const destinations=mode==='projects'?{'BS Project':frappe.boot.bs_app_destinations?.['BS Project']}:frappe.boot.bs_app_destinations;
                    for(const item of dashboardLinks(destinations,frappe.boot.bs_project_support_links || [])) {
                        if(item.children) {
                            const section=document.createElement('div'), heading=document.createElement('div');
                            section.className='bs-dashboard-category';
                            heading.className='bs-dashboard-category-title';
                            heading.textContent=__(item.label);
                            section.append(heading);
                            for(const child of item.children) {
                                const row=document.createElement('div'), link=document.createElement('a');
                                row.className='standard-sidebar-item';link.className='item-anchor';
                                link.href=child.href;link.textContent=__(child.label);
                                row.append(link);section.append(row);
                            }
                            nav.append(section);
                            continue;
                        }
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
            if(host.querySelector('.bs-dashboard-modules')) continue;
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
