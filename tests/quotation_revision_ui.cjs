const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../bsgroup/public/js/oman_quotation_flow.js'),'utf8');
async function setup(dirty=false) {
 const handlers={},buttons=new Map(),calls=[],routes=[],messages=[];let dialog,fail=false;
 const data={enabled:true,editable:true,can_write:true,revision:0,statuses:[]};
 const frappe={ui:{form:{on:(dt,h)=>handlers[dt]=h},Dialog:class {
  constructor(opts){Object.assign(this,opts);dialog=this;}show(){}hide(){this.hidden=true;}
 }},call:async args=>{calls.push(args);if(args.method.endsWith('.begin')){
  if(fail)throw Error('revision failed');return {message:{dcs:'D-1',quotation:'Q-1'}};
 }return {message:data};},set_route:async(...args)=>routes.push(args),show_alert(){},msgprint:s=>messages.push(s),utils:{escape_html:s=>s}};
 vm.runInNewContext(source,{frappe,__:s=>s,window:{}});
 const frm={doc:{name:'Q-1',modified:'M1',items:[]},is_new:()=>false,is_dirty:()=>dirty,
  set_df_property(){},set_intro(){},dashboard:{set_headline(){}},page:{set_primary_action(){},clear_primary_action(){}},
  add_custom_button:(s,fn)=>buttons.set(s,fn),remove_custom_button:s=>buttons.delete(s)};
 await handlers.Quotation.refresh(frm);
 return {buttons,calls,routes,messages,get dialog(){return dialog;},fail:()=>fail=true};
}
(async()=>{
 for(const choice of ['Yes','No']) {
  const t=await setup();t.buttons.get('Revise Quotation')();
  assert.equal(t.dialog.fields[0].label,'Do you want Presales to work on this?');
  await t.dialog.primary_action({presales:choice});
  const request=t.calls.find(x=>x.method.endsWith('.begin'));
  assert.equal(request.args.presales,choice);assert.equal(request.args.expected_modified,'M1');
  assert.equal(t.routes[0].join('/'),'Form/Deal Cost Sheet/D-1');assert(t.dialog.hidden);
 }
 const dirty=await setup(true);dirty.buttons.get('Revise Quotation')();assert(!dirty.dialog);assert.equal(dirty.messages.length,1);
 const failure=await setup();failure.buttons.get('Revise Quotation')();failure.fail();
 await assert.rejects(failure.dialog.primary_action({presales:'Yes'}),/revision failed/);
 assert.equal(failure.routes.length,0);assert(!failure.dialog.hidden);assert(!failure.dialog.__saving);
 console.log('PASS Yes/No routing, saved-version guard, unsaved warning and recoverable server errors');
})().catch(error=>{console.error(error);process.exitCode=1;});
