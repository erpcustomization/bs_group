// The app opens the existing Desk. Never construct a second module list or data store.
(() => {
    'use strict';
    if (window.top !== window.self || window.bsErpAppLoaded) return;
    window.bsErpAppLoaded = true;
    const api='/api/method/bsgroup.bs_erp_app.',version='20261112-1';
    const region=/^erp-om[.]/.test(location.hostname)?'Oman':/^(erp[.]bitssecureit[.]com|erp-bitssecureit[.])/.test(location.hostname)?'UAE':'';
    const name=('BS ERP '+region).trim();
    const standalone=()=>window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
    let installPrompt=null;
    function status(text) { document.querySelectorAll('.bserp-install-status').forEach(e=>{e.textContent=text;}); }
    function instructions() {
        const guide=document.getElementById('install-guide');
        if (guide) {guide.scrollIntoView({behavior:'smooth',block:'start'});guide.focus({preventScroll:true});status('Follow the instructions for your phone below.');return;}
        if(window.frappe?.ui?.Dialog) {
            const dialog=new frappe.ui.Dialog({title:name,fields:[{fieldtype:'HTML',fieldname:'help',options:
              '<p>Your app uses your existing ERP login, modules and records.</p><p><b>Android:</b> In Chrome, use the browser menu → Install app or Add to Home screen.</p><p><b>iPhone:</b> In Safari, use Share → Add to Home Screen.</p><p><a href="/bs-erp" target="_blank" rel="noopener">Open the installation page</a></p><p>Internet connection required to load and save your work.</p>'}]});dialog.show();
        }
    }
    async function install() {
        if(!installPrompt) {instructions();return;}
        const prompt=installPrompt;installPrompt=null;
        try {await prompt.prompt();const choice=await prompt.userChoice;status(choice.outcome==='accepted'?'Installation requested. Open BS ERP from your app list.':'You can install BS ERP whenever you are ready.');}
        catch(error){instructions();}
    }
    window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;status('Ready to install. Tap Install to add BS ERP to this device.');});
    window.addEventListener('appinstalled',()=>{installPrompt=null;status('BS ERP is installed. Open it from your app list.');document.querySelectorAll('[data-bs-erp-install]').forEach(b=>{b.hidden=true;});});
    function attach(tag,selector,attributes) {
        let el=document.head.querySelector(selector);if(!el){el=document.createElement(tag);document.head.append(el);}
        for(const [key,value] of Object.entries(attributes))el.setAttribute(key,value);
    }
    function start() {
        document.querySelectorAll('[data-bs-erp-install]').forEach(button=>button.addEventListener('click',install));
        if(standalone()) {document.querySelectorAll('[data-bs-erp-install]').forEach(b=>{b.hidden=true;});status('Open BS ERP below to continue to your dashboard.');}
        if(!/^\/desk(?:\/|$)/.test(location.pathname))return;
        if(!window.frappe?.session || frappe.session.user==='Guest')return;
        document.body.classList.add('bs-erp-shell');
        attach('link','link[rel="manifest"]',{rel:'manifest',href:api+'manifest'});
        attach('link','link[data-bs-erp-style]',{'data-bs-erp-style':'1',rel:'stylesheet',href:api+'style?v='+version});
        attach('meta','meta[name="theme-color"]',{name:'theme-color',content:'#123354'});
        attach('meta','meta[name="apple-mobile-web-app-capable"]',{name:'apple-mobile-web-app-capable',content:'yes'});
        attach('meta','meta[name="apple-mobile-web-app-title"]',{name:'apple-mobile-web-app-title',content:name});
        attach('link','link[rel="apple-touch-icon"]',{rel:'apple-touch-icon',href:api+'icon?size=180&v='+version});
        const bar=document.createElement('nav');bar.className='bserp-mobile-bar';bar.setAttribute('aria-label','BS ERP app navigation');
        bar.innerHTML='<a href="/desk/my-work-dashboard"><span aria-hidden="true">⌂</span>Home</a><button type="button" data-bserp-modules><span aria-hidden="true">☰</span>Modules</button><button type="button" data-bserp-app><span aria-hidden="true">▣</span>App</button>';
        document.body.append(bar);
        bar.querySelector('[data-bserp-modules]').addEventListener('click',event=>{
            // The outer toolbar click must not immediately trigger Desk's click-away close handler.
            event.stopPropagation();
            // Click the real Desk control so its authorised navigation and collapse state remain authoritative.
            const toggle=[...document.querySelectorAll('.page-container .sidebar-toggle-btn')].find(e=>e.getClientRects().length)
                || document.querySelector('.body-sidebar-container .sidebar-collapse-arrow');
            toggle?.click();
        });
        bar.querySelector('[data-bserp-app]').addEventListener('click',install);
        const offline=document.createElement('div');offline.className='bserp-offline';offline.setAttribute('role','status');
        offline.textContent='Offline · Reconnect before loading or saving work.';document.body.append(offline);
        const online=()=>{offline.hidden=navigator.onLine!==false;};online();
        window.addEventListener('online',online);window.addEventListener('offline',online);
        // No service worker, offline business-data cache, or alternate authentication flow.
    }
    if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
