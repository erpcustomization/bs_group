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
    if(typeof module!=='undefined' && module.exports) {module.exports={groups,appForSection,routeMatches,chooseApp};return;}
    if(window.top!==window.self || window.bsAppSidebarInstalled) return;
    window.bsAppSidebarInstalled=true;
    const key='bs-sidebar-app:'+frappe.session.user;
    let previous, scheduled=false;
    try { previous=sessionStorage.getItem(key); } catch (_) {}
    const style=document.createElement('style');
    style.textContent='.bs-app-unrelated{display:none!important}';
    document.head.append(style);
    function update() {
        scheduled=false;
        const current=new URL(location.href);
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
                const app=appForSection(row.classList.contains('section-item')?row.dataset.id:null);
                for(const link of row.querySelectorAll('a[href]')) candidates.push({app,href:link.getAttribute('href')});
            }
            const active=chooseApp(current,candidates,previous);
            previous=active;
            try { sessionStorage.setItem(key,active); } catch (_) {}
            for(const row of rows) {
                const app=appForSection(row.classList.contains('section-item')?row.dataset.id:null);
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
