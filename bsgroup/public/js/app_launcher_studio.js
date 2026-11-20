/* Presentation only. Enhance native, permission-filtered tiles in place. */
(() => {
    if (window.top !== window.self || window.__bsLauncherStudio) return;
    window.__bsLauncherStudio = true;
    const descriptions = {
        'BS Approvals':'Review requests and decisions', 'BS Helpdesk':'Customer tickets and service requests',
        'BS HR':'People, attendance and employee services', 'BS Procurement':'Purchasing, requisitions and orders',
        'BS Project':'Project delivery and technical operations', 'BS Project Support':'Project delivery and technical operations',
        'BS Sales':'Leads, opportunities and quotations', 'BS Support':'Support requests and follow-up',
        'BS User Management':'User accounts and module access', 'Data Migration':'Import and manage business data',
        'Framework':'System tools and configuration', 'Helpdesk':'Service desk workspace',
        'Accounting':'Accounts, payments and financial reports', 'Assets':'Assets and their lifecycle',
        'Buying':'Suppliers and purchasing', 'Manufacturing':'Production and manufacturing',
        'Projects':'Project records and planning', 'Quality':'Quality checks and controls',
        'Selling':'Sales records and transactions', 'Stock':'Inventory and warehouse operations',
        'ERPNext Settings':'Business settings and configuration', 'Bits Secure HR':'Human resources workspace'
    };
    const css = `
    .bs-launcher{display:block!important;max-width:1240px!important;width:100%!important;margin:0 auto!important;padding:32px 28px 64px!important;box-sizing:border-box}
    .bs-launcher .bs-launcher-hero{position:relative;overflow:hidden;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:34px 38px;margin:0 0 30px;border-radius:22px;background:linear-gradient(115deg,#102b50,#194a80);color:#fff;box-shadow:0 12px 32px #12375f18}
    .bs-launcher-hero:after{content:'';position:absolute;right:130px;top:-130px;width:340px;height:340px;border:1px solid #ffffff14;border-radius:50%;pointer-events:none}
    .bs-launcher .bs-launcher-kicker{font-size:10px;font-weight:700;letter-spacing:2.5px;color:#b9d8fc;text-transform:uppercase;margin-bottom:10px}
    .bs-launcher .bs-launcher-hero h1{font-size:32px;line-height:1.15;letter-spacing:-1px;font-weight:700;color:#fff;margin:0 0 10px}
    .bs-launcher .bs-launcher-hero p{font-size:13px;line-height:1.7;color:#d3e3f6;margin:0;max-width:530px}
    .bs-launcher .bs-launcher-dashboard{position:relative;z-index:1;flex-shrink:0;display:inline-flex;align-items:center;gap:14px;padding:12px 18px;border:1px solid #ffffff55;border-radius:10px;color:#fff;background:#ffffff0d;font-size:12px;font-weight:600;text-decoration:none;transition:background .16s}
    .bs-launcher .bs-launcher-dashboard:hover{background:#ffffff22}
    .bs-launcher .bs-launcher-section{display:flex;align-items:center;justify-content:space-between;margin:0 2px 16px;gap:12px}
    .bs-launcher .bs-launcher-section h2{margin:0;font-size:17px;font-weight:700;color:var(--text-color,#132d4b)}
    .bs-launcher .bs-launcher-section span{font-size:11px;color:var(--text-muted,#718198)}
    .bs-launcher>.icons-container{width:100%!important;max-width:none!important;margin:0!important;padding:0!important}
    .bs-launcher>.icons-container>.icons{display:grid!important;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px!important;width:100%!important;padding:0!important;margin:0!important;justify-content:initial!important}
    .bs-launcher>.icons-container>.icons>.desktop-icon{position:relative!important;display:flex!important;flex-direction:row!important;align-items:center!important;gap:16px!important;width:100%!important;box-sizing:border-box!important;min-width:0!important;height:auto!important;min-height:112px!important;margin:0!important;padding:22px 20px!important;border:1px solid var(--border-color,#e1e8f1)!important;border-radius:16px!important;background:var(--card-bg,#fff)!important;box-shadow:0 3px 10px #19385804;transition:transform .16s,box-shadow .16s,border-color .16s;text-align:left!important}
    .bs-launcher>.icons-container>.icons>.desktop-icon[hidden]{display:none!important}
    .bs-launcher>.icons-container>.icons>.desktop-icon:hover{transform:translateY(-3px);border-color:#97b5e1!important;box-shadow:0 10px 24px #1b4e8412}
    .bs-launcher>.icons-container>.icons>.desktop-icon:focus-visible,.bs-launcher-dashboard:focus-visible{outline:3px solid #568bdb;outline-offset:3px}
    .bs-launcher>.icons-container>.icons>.desktop-icon>.icon-container{flex-shrink:0;width:50px!important;height:50px!important;min-width:50px!important;margin:0!important;border-radius:13px!important;box-shadow:none!important}
    .bs-launcher>.icons-container>.icons>.desktop-icon>.icon-container:not([style]){background:#f0f5fc!important}
    .bs-launcher>.icons-container>.icons>.desktop-icon>.icon-container>.app-icon{width:40px!important;height:40px!important;object-fit:contain}
    .bs-launcher>.icons-container>.icons>.desktop-icon>.icon-caption{min-width:0;flex:1;text-align:left!important;width:auto!important;height:auto!important;max-height:none!important;overflow:visible!important;max-width:none!important;margin:0!important;padding:0!important}
    .bs-launcher>.icons-container>.icons>.desktop-icon>.icon-caption>.icon-title{font-size:14px!important;font-weight:700!important;line-height:1.4!important;color:var(--text-color,#16365b)!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;max-width:none!important;width:auto!important;margin:0!important}
    .bs-launcher .bs-launcher-description{font-size:11px;line-height:1.6;color:var(--text-muted,#6f8199);margin-top:5px;white-space:normal}
    .bs-launcher>.icons-container>.icons>.desktop-icon.bs-launcher-business{border-top:3px solid #285da5!important;padding-top:20px!important}
    .bs-launcher>.icons-container>.icons>.desktop-icon>.hide-button{top:6px!important;right:6px!important}
    @media(min-width:1450px){.bs-launcher>.icons-container>.icons{grid-template-columns:repeat(4,minmax(0,1fr))}}
    @media(max-width:850px){.bs-launcher{padding:22px 18px 40px!important}.bs-launcher>.icons-container>.icons{grid-template-columns:repeat(2,minmax(0,1fr))}.bs-launcher .bs-launcher-hero{padding:28px}.bs-launcher .bs-launcher-hero h1{font-size:28px}}
    @media(max-width:550px){.bs-launcher .bs-launcher-hero{align-items:flex-start;flex-direction:column;gap:20px}.bs-launcher>.icons-container>.icons{grid-template-columns:1fr}.bs-launcher .bs-launcher-section span{display:none}}
    @media(prefers-reduced-motion:reduce){.bs-launcher *{transition:none!important}.bs-launcher>.icons-container>.icons>.desktop-icon:hover{transform:none}}
    `;
    const style=document.createElement('style');style.id='bs-launcher-studio-style';style.textContent=css;document.head.append(style);
    let queued=false;
    function enhance() {
        queued=false;
        const root=document.querySelector('.desktop-container');
        if(!root)return;
        root.classList.add('bs-launcher');
        const grid=root.querySelector(':scope > .icons-container > .icons');
        if(!grid)return;
        if(!root.querySelector(':scope > .bs-launcher-hero')){
            const hero=document.createElement('section');hero.className='bs-launcher-hero';
            hero.innerHTML='<div><div class="bs-launcher-kicker">BITS Secure IT · BS ERP</div><h1>Your workspace, connected.</h1><p>Everything you need to move work forward. Choose an app to get started.</p></div><a class="bs-launcher-dashboard" href="/desk/my-work-dashboard">My dashboard <span aria-hidden="true">↗</span></a>';
            const heading=document.createElement('div');heading.className='bs-launcher-section';
            heading.innerHTML='<h2>All apps</h2><span>Your tools. One workspace.</span>';
            root.insertBefore(hero,root.firstChild);hero.after(heading);
        }
        for(const tile of grid.children){
            if(!tile.classList.contains('desktop-icon'))continue;
            const caption=tile.querySelector(':scope > .icon-caption');
            if(!caption)continue;
            const name=tile.dataset.id||caption.textContent.trim();
            tile.classList.toggle('bs-launcher-business',name.startsWith('BS '));
            if(!caption.querySelector('.bs-launcher-description')){
                const desc=document.createElement('div');desc.className='bs-launcher-description';
                desc.textContent=descriptions[name]||'Open workspace';caption.append(desc);
            }
        }
    }
    const schedule=()=>{if(!queued){queued=true;requestAnimationFrame(enhance);}};
    new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true});
    frappe.router?.on('change',schedule);
    schedule();
})();
