const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {parseHTML}=require('linkedom');
const source=fs.readFileSync('bsgroup/public/js/bs_erp_app.js','utf8');
let count=0;const check=(label,value)=>{assert.ok(value,label);count++;};
function fixture({host='erp.bitssecureit.com',user='mohan@bitssecureit.com',path='/desk/my-work-dashboard',iframe=false,installed=false}={}){
    const {document,Event}=parseHTML('<html><head></head><body><aside class="body-sidebar-container"><a href="/desk/quotation" id="permitted">Quotation</a><a href="/desk/payroll" hidden id="denied">Payroll</a></aside><main class="page-container"><button class="sidebar-toggle-btn">Menu</button></main><button data-bs-erp-install>Install</button><p class="bserp-install-status"></p><section id="install-guide"></section></body></html>');
    const events={},navigator={onLine:true},window={matchMedia:()=>({matches:installed}),addEventListener:(name,fn)=>events[name]=fn};
    window.top=iframe?{}:window;window.self=window;let toggles=0,scrolls=0;
    const toggle=document.querySelector('.sidebar-toggle-btn');toggle.getClientRects=()=>[{}];toggle.addEventListener('click',()=>toggles++);
    document.querySelector('#install-guide').scrollIntoView=()=>scrolls++;document.querySelector('#install-guide').focus=()=>{};
    const frappe={session:{user}};window.frappe=frappe;
    const context={window,document,frappe,navigator,location:{hostname:host,pathname:path}};
    vm.runInNewContext(source,context);
    return {document,events,window,context,navigator,Event,get toggles(){return toggles;},get scrolls(){return scrolls;}};
}
(async()=>{
    for(const user of ['mohan@bitssecureit.com','raj@bitssecureit.com','employee@example.com','Administrator']){
        const f=fixture({user});check(user+' uses same permitted link',f.document.querySelector('#permitted').getAttribute('href')==='/desk/quotation');
        check(user+' does not reveal inaccessible module',f.document.querySelector('#denied').hidden);
        check(user+' gets install manifest',f.document.querySelector('link[rel=manifest]').href.endsWith('bs_erp_app.manifest'));
    }
    let f=fixture();f.document.querySelector('[data-bserp-modules]').click();check('Modules delegates to native authorised menu',f.toggles===1);
    vm.runInNewContext(source,f.context);check('SPA reload does not duplicate app navigation',f.document.querySelectorAll('.bserp-mobile-bar').length===1);
    check('UAE app named separately',f.document.querySelector('meta[name=apple-mobile-web-app-title]').content==='BS ERP UAE');
    f=fixture({host:'erp-om.bitssecureit.com'});check('Oman app named separately',f.document.querySelector('meta[name=apple-mobile-web-app-title]').content==='BS ERP Oman');
    f.navigator.onLine=false;f.events.offline();check('Offline notice shown',!f.document.querySelector('.bserp-offline').hidden);
    f.navigator.onLine=true;f.events.online();check('Offline notice clears on reconnect',f.document.querySelector('.bserp-offline').hidden);
    f=fixture({user:'Guest'});check('Guest gets no Desk navigation',!f.document.querySelector('.bserp-mobile-bar'));
    f=fixture({iframe:true});check('Project popup frames unchanged',!f.document.querySelector('.bserp-mobile-bar'));
    f=fixture({path:'/bs-erp'});check('Install page does not create a module list',!f.document.querySelector('.bserp-mobile-bar'));
    f.document.querySelector('[data-bs-erp-install]').click();check('Unsupported install shows instructions',f.scrolls===1);
    let prompted=0,prevented=0;f.events.beforeinstallprompt({preventDefault(){prevented++;},async prompt(){prompted++;},userChoice:Promise.resolve({outcome:'accepted'})});
    f.document.querySelector('[data-bs-erp-install]').click();await new Promise(r=>setTimeout(r,0));
    check('Install requires explicit click',prompted===1&&prevented===1);
    check('Install status accurately reports request',f.document.querySelector('.bserp-install-status').textContent.includes('Installation requested'));
    f.events.appinstalled();check('Completed installation hides install button',f.document.querySelector('[data-bs-erp-install]').hidden);
    f=fixture({installed:true,path:'/bs-erp'});check('Already installed mode offers opening app',f.document.querySelector('[data-bs-erp-install]').hidden);
    check('App has no data fetch, alternate login or offline cache',!/(fetch\(|XMLHttpRequest|localStorage|sessionStorage|serviceWorker\.register|frappe\.call)/.test(source));
    console.log(`${count} BS ERP app UI checks passed`);
})();
