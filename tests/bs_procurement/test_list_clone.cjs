const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {parseHTML}=require('./ui/node_modules/linkedom');
const fixture=require('./ui_fixture.cjs');
const tick=()=>new Promise(r=>setTimeout(r,20));
(async()=>{
 const {document,Event}=parseHTML('<html><body><main></main></body></html>');
 const {frappe,state}=fixture(document,{route:{bsp_view:'list'}});
 state.request.canClone=false;
 const second={...state.manual,id:'MANUAL-SECOND'},calls=[],errors=[];
 let failSecond=false,created=0;
 const original=frappe.call;
 frappe.call=async args=>{
  if(args.method.endsWith('clone_request')){
   calls.push({...args.args});
   if(failSecond&&args.args.name===second.id)throw Error('Temporary failure');
   return {message:{...state.manual,id:'COPY-'+(++created),approval:'Draft'}};
  }
  const result=await original(args);
  if(args.method.endsWith('get_requests'))result.message.requests.push(second);
  return result;
 };
 vm.runInNewContext(fs.readFileSync('bsgroup/bs_group/page/bs_procurement/bs_procurement.js','utf8'),{document,frappe,Intl,crypto:require('node:crypto').webcrypto,Uint8Array,setTimeout,clearTimeout,console:{error:e=>errors.push(e)}});
 frappe.pages['bs-procurement'].on_page_load({});await tick();
 const q=s=>document.querySelector(s);
 const select=(id,on=true)=>{const el=q(`[data-select-pr="${id}"]`);el.checked=on;el.dispatchEvent(new Event('input',{bubbles:true}));};
 const click=async()=>{q('[data-action="clone-selected-pr"]').dispatchEvent(new Event('click',{bubbles:true}));await tick();};
 assert(q('[data-action="clone-selected-pr"]').disabled);
 assert(q(`[data-select-pr="${state.request.id}"]`).disabled);
 select(state.manual.id);assert(!q('[data-action="clone-selected-pr"]').disabled);
 await click();assert.equal(calls.length,1);assert.equal(calls[0].name,state.manual.id);
 assert.equal(q('.bsp h2').textContent.includes('Purchase Requisition'),true);
 assert(q('[data-action="open-pr"][data-id="COPY-1"]'));
 assert(q('[data-action="clone-selected-pr"]').disabled);
 select(state.manual.id);select(second.id);failSecond=true;await click();
 assert.equal(calls.length,3);assert(!q(`[data-select-pr="${state.manual.id}"]`).checked);assert(q(`[data-select-pr="${second.id}"]`).checked);
 const retryKey=calls[2].key;failSecond=false;await click();assert.equal(calls[3].key,retryKey);assert.equal(calls.length,4);
 select(state.manual.id);const search=q('[data-search]');search.value='MANUAL-SECOND';search.dispatchEvent(new Event('input',{bubbles:true}));
 assert(!q(`[data-select-pr="${state.manual.id}"]`).checked);
 const all=q('[data-select-all-pr]');all.checked=true;all.dispatchEvent(new Event('input',{bubbles:true}));
 assert(q(`[data-select-pr="${second.id}"]`).checked);assert(!q(`[data-select-pr="${state.manual.id}"]`).checked);
 assert.equal(errors.length,1);
 console.log('PASS list cloning: eligibility, single/multiple drafts, partial failure, idempotent retry, filtered selection and no external navigation');
})().catch(e=>{console.error(e);process.exitCode=1;});
