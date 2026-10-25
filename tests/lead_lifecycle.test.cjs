const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict');
const {parseHTML} = require('./bs_procurement/ui/node_modules/linkedom');
const {document, window} = parseHTML('<html><body><main><div id="status"></div></main></body></html>');
let config, interval, mapped, routed, prompt, calls=0;
const now = Date.parse('2026-10-25T12:00:00Z');
const frappe = {ui:{form:{on(){}}},session:{user:'sales@test'},datetime:{convert_to_user_tz:(x)=>x,now_datetime:()=>new Date(now).toISOString()},
 utils:{escape_html:x=>String(x).replaceAll('<','&lt;')},model:{sync:x=>mapped=x},set_route:(...x)=>routed=x,
 msgprint:()=>{},prompt:(fields,fn)=>{prompt=fn; assert.equal(fields[0].reqd,1)},
 call:async args=>{calls++;config=args;args.callback({message:{doctype:'Opportunity',name:'new-opp'}})}};
const context={document,frappe,__:x=>x,moment:()=>({diff:x=>(now-Date.parse(x))/3600000}),clearInterval(){},setInterval:fn=>{interval=fn;return 1}};
vm.createContext(context);vm.runInContext(fs.readFileSync('bsgroup/public/js/lead_lifecycle_form.js','utf8')+';this.life=bsi_lead_lifecycle;',context);
const frm={wrapper:document.querySelector('main'),fields_dict:{status:{df:{options:'Open\nDelayed\nDropped'},$wrapper:[document.getElementById('status')]}},
 doc:{name:'L1',status:'Open',creation:'2026-10-25T11:00:00Z',company_name:'Acme'},perm:[{write:1}],page:{set_indicator(){}},set_df_property(){},is_new:()=>false,is_dirty:()=>false,
 async set_value(k,v){this.doc[k]=v},async save(){this.saved=true},add_child:(table,n)=>{frm.note=n;assert.equal(table,'notes')}};
context.life.refresh(frm); context.life.refresh(frm);
assert.equal(document.querySelectorAll('.bsi-lead-outcome').length,1);
assert.deepEqual(Array.from(document.querySelectorAll('option:not([hidden])')).map(x=>x.textContent),['Open','Opportunity','Dropped']);
assert.equal(context.life.display(frm.doc)[0],'Open');
frm.doc.creation='2026-10-24T12:00:00Z';assert.equal(context.life.display(frm.doc)[0],'Delayed');
frm.doc.status='Dropped';assert.equal(context.life.display(frm.doc)[0],'Dropped');
frm.doc.status='Opportunity';assert.equal(context.life.display(frm.doc)[0],'Opportunity \u00b7 Closed');
context.life.refresh(frm);assert.equal(document.querySelector('select').disabled,true);
frm.doc.status='Open';context.life.refresh(frm);
(async()=>{
 await context.life.convert(frm);assert.equal(config.method,'bsgroup.lead_lifecycle.make_opportunity');assert.equal(mapped.sales_stage,'Proposal');assert.equal(mapped.custom_organization_name,'Acme');assert.equal(frm.doc.status,'Open');assert.equal(routed[1],'Opportunity');
 frm.is_dirty=()=>true;await context.life.convert(frm);assert.equal(calls,1);
 const select=document.querySelector('select');select.querySelector('option[value=drop]').selected=true;select.dispatchEvent(new window.Event('change'));await prompt({reason:'Not relevant'});assert.equal(frm.doc.status,'Dropped');assert.equal(frm.note.note,'Dropped: Not relevant');assert.equal(frm.saved,true);
 console.log('PASS: three choices, 24-hour display, read-only closed state, required drop note, no premature close, existing Opportunity mapping.');
})().catch(e=>{console.error(e);process.exitCode=1});

