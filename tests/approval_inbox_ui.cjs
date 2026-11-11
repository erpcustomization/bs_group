// Run with NODE_PATH pointing at the isolated test dependency directory.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {parseHTML}=require('linkedom');
const nav=fs.readFileSync('bsgroup/public/js/approval_request_navigation.js','utf8');
const source=fs.readFileSync('bsgroup/bs_group/page/bs_approval_request/bs_approval_request.js','utf8');
let checks=0;const check=(label,value)=>{assert.ok(value,label);checks++;};
const tick=()=>new Promise(r=>setTimeout(r,10));
function dom(){return parseHTML('<html><body><aside class="body-sidebar"><div class="sidebar-items"><div class="sidebar-item-container" id="quote"><div class="standard-sidebar-item"><a href="/desk/bs-group/quotation">Quotation</a></div></div><div id="next">Sales Target</div></div></aside><main></main></body></html>');}
function navigation(user){
    const {document}=dom();let update;
    const window={};window.top=window;window.self=window;
    vm.runInNewContext(nav,{document,window,frappe:{session:{user},router:{on:()=>{}}},__:x=>x,$:()=>({on:()=>{}}),MutationObserver:class{constructor(fn){update=fn;}observe(){}},setTimeout:fn=>fn()});
    return {document,update};
}
for(const user of ['Administrator','paul@bitssecureit.com','raj@bitssecureit.com','Guest']){
    const {document}=navigation(user);check('Menu hidden from '+user,!document.querySelector('.bs-approval-request-link'));
}
const n=navigation('mohan@bitssecureit.com');
check('Menu inserted immediately after Quotation',n.document.querySelector('#quote').nextElementSibling.classList.contains('bs-approval-request-link'));
n.update();n.update();check('Menu does not duplicate after rerender',n.document.querySelectorAll('.bs-approval-request-link').length===1);
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
async function page(user){
    const {document,Event}=dom(),calls=[],messages=[];let dialog;
    const records=[{kind:'sales',name:'DCS-1',subject:'<img src=x onerror=bad()>',requested_by:'sales@example.com',amount:250,currency:'OMR',state:'Pending Manager'},
        {kind:'purchase',name:'PR-1',subject:'WiFi project',requested_by:'buyer@example.com',amount:100,currency:'AED',state:'Pending Approval'}];
    const frappe={session:{user},pages:{'bs-approval-request':{}},utils:{escape_html:esc},datetime:{str_to_user:x=>x},
        ui:{make_app_page:()=>({main:document.querySelector('main'),set_primary_action:()=>{}}),Dialog:class{constructor(options){this.options=options;dialog=this;}show(){}hide(){this.hidden=true;}disable_primary_action(){this.disabled=true;}enable_primary_action(){this.disabled=false;}}},
        msgprint:x=>messages.push(x),show_alert:()=>{},call:async({method,args})=>{calls.push({method,args});
            if(method.endsWith('.pending'))return{message:{requests:records}};
            if(method.endsWith('.review'))return{message:{kind:'sales',name:'DCS-1',modified:'version1',revision:'R7',deal:{currency:'OMR'},current:{},previous_approved:{},items:[],actions:['Approve','Reject','Return for Rework']}};
            if(method.endsWith('.decide')){records.splice(0,1);return{message:{saved:true}};}
            throw Error(method);}};
    vm.runInNewContext(source,{document,frappe,__:s=>s});frappe.pages['bs-approval-request'].on_page_load({});await tick();
    return {document,Event,calls,messages,getDialog:()=>dialog};
}
(async()=>{
    let p=await page('Administrator');check('Denied account does not request any approval data',p.calls.length===0&&!p.document.querySelector('.bsar-controls'));
    p=await page('mohan@bitssecureit.com');
    check('Both approval types are rendered',p.document.querySelectorAll('[data-review]').length===2);
    check('Untrusted subjects are escaped',!p.document.querySelector('.bsar-results img'));
    check('Oman amount uses three decimals',p.document.body.textContent.includes('250.000'));
    p.document.querySelector('[data-kind="purchase"]').dispatchEvent(new p.Event('click',{bubbles:true}));
    check('Purchase filter keeps only requisitions',p.document.querySelectorAll('[data-review]').length===1&&p.document.querySelector('[data-review]').dataset.review==='PR-1');
    p.document.querySelector('[data-kind="all"]').dispatchEvent(new p.Event('click',{bubbles:true}));
    p.document.querySelector('[data-review="DCS-1"]').dispatchEvent(new p.Event('click',{bubbles:true}));await tick();
    const d=p.getDialog();check('Review requires an explicit decision',d.options.fields.find(f=>f.fieldname==='action').reqd===1);
    await d.options.primary_action({action:'Reject',reason:''});check('Blank rejection sends no decision',!p.calls.some(c=>c.method.endsWith('.decide')));
    await d.options.primary_action({action:'Approve',reason:'Reviewed'});
    const submitted=p.calls.find(c=>c.method.endsWith('.decide'));
    check('Decision sends reviewed document version',submitted.args.modified==='version1'&&submitted.args.revision==='R7');
    check('Successful decision closes dialog and refreshes queue',d.hidden&&p.document.querySelectorAll('[data-review]').length===1);
    console.log(JSON.stringify({passed:checks,failed:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
