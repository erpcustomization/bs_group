/* Compare the actual old/new UI's controls and API calls; no ERP writes. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),cp=require('node:child_process');
const {parseHTML}=require('./ui/node_modules/linkedom');
const fixture=require('./ui_fixture.cjs');
const path='bsgroup/bs_group/page/bs_procurement/bs_procurement.js';
const old=cp.execFileSync('git',['show','HEAD:'+path],{encoding:'utf8'}),current=fs.readFileSync(path,'utf8');
const tick=()=>new Promise(r=>setTimeout(r,10));
async function exercise(source){
  const {document,Event}=parseHTML('<html><body><main></main></body></html>');
  const {frappe,state}=fixture(document),errors=[];
  vm.runInNewContext(source,{document,frappe,Intl,crypto:require('node:crypto').webcrypto,Uint8Array,setTimeout,clearTimeout,console:{error:e=>errors.push(String(e))}});
  frappe.pages['bs-procurement'].on_page_load({});await tick();
  const snapshots={};
  function capture(name){
    snapshots[name]={
      actions:[...document.querySelectorAll('[data-action]')].map(e=>[e.dataset.action,e.dataset.id||'',e.dataset.value||'',e.disabled||false]).sort(),
      fields:[...document.querySelectorAll('input,select,textarea')].map(e=>[e.tagName,e.getAttribute('aria-label'),e.getAttribute('type'),e.getAttribute('data-field'),e.getAttribute('data-pr-field'),e.getAttribute('data-key'),e.getAttribute('data-line'),e.disabled||false,e.value||'',e.getAttribute('required')]).sort(),
      links:[...document.querySelectorAll('.bsp a')].map(e=>[e.getAttribute('href'),e.getAttribute('target')]).sort()
    };
  }
  async function click(selector){const el=document.querySelector(selector);assert(el,selector);el.dispatchEvent(new Event('click',{bubbles:true}));await tick();assert.equal(errors.length,0,errors.join('\n'));}
  capture('dashboard');
  await click('[data-metric="pending"]');capture('dashboard drilldown');
  await click('[data-action="dashboard"]');
  await click('[data-action="list"]');capture('PR list');
  await click('[data-action="open-pr"][data-id="MAT-MR-2026-00005"]');capture('manual draft PR');
  await click('[data-action="list"]');
  await click('[data-action="open-pr"][data-id="MAT-MR-2026-00004"]');capture('approved PR');
  await click('[data-action="open-po"][data-id="PUR-ORD-2026-00131"]');capture('PO awaiting approval');
  await click('[data-action="po-connections"]');capture('read-only connections');
  assert.equal(document.querySelectorAll('.bsp-connection-content button,.bsp-connection-content input,.bsp-connection-content a').length,0);
  await click('[data-action="po-details"]');
  await click('[data-action="open-receipt"]');capture('receipt');
  await click('[data-action="orders"]');
  await click('[data-action="open-po"][data-id="PUR-ORD-2026-00132"]');capture('draft PO');
  await click('[data-action="services"]');capture('Payment Order list');
  await click('[data-action="settlement"]');capture('approved Payment Order');
  await click('[data-action="view-accounting"]');capture('accounting entries');
  assert.equal(errors.length,0,errors.join('\n'));
  return {snapshots,calls:JSON.parse(JSON.stringify(state.calls))};
}
(async()=>{
  const before=await exercise(old),after=await exercise(current);
  for(const [name,controls] of Object.entries(before.snapshots)){
    assert.deepEqual(after.snapshots[name],controls,name+' controls changed');console.log('PASS',name);
  }
  assert.deepEqual(after.calls,before.calls,'API calls changed');
  console.log('PASS same API calls and arguments across all screens');
})().catch(e=>{console.error(e);process.exitCode=1;});
