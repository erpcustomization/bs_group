const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.resolve(__dirname,'../bsgroup/public/js/oman_quotation_flow.js'),'utf8');
async function setup({dirty=false,rows=[],issues=[],canWrite=true}={}) {
 const handlers={},buttons=new Map(),calls=[],messages=[],alerts=[]; let saves=0,primary;
 const data={enabled:true,editable:true,can_write:canWrite,can_print:true,save_feedback:true,client_descriptions:true,ready_to_convert:!issues.length,pdf_issues:issues,revision:0};
 const frappe={ui:{form:{on(dt,h){handlers[dt]=h;}}},
  call:async opts=>{calls.push(opts);return {message:data};},model:{async set_value(dt,name,values){Object.assign(rows.find(r=>r.name===name),values);dirty=true;}},
  utils:{escape_html:s=>String(s).replaceAll('<','&lt;')},show_alert:v=>alerts.push(v),msgprint:v=>messages.push(v)};
 vm.runInNewContext(source,{frappe,__:s=>s,window:{}});
 const fields_map=Object.fromEntries(['description','custom_oman_client_description','custom_oman_use_costing_description','custom_oman_use_co_description','qty','rate','amount'].map(fieldname=>[fieldname,{fieldname,label:fieldname,read_only:0}]));
 const grid={fields_map,update_docfield_property(name,key,value){fields_map[name][key]=value;},setup_user_defined_columns(){},reset_grid(){}};
 const frm={doc:{name:'Q-1',docstatus:0,modified:'M1',items:rows},fields_dict:{items:{grid}},
  is_new:()=>false,is_dirty:()=>dirty,dirty:()=>dirty=true,
  save(){saves++;return new Promise(()=>{});},set_df_property(){},set_intro(){},dashboard:{set_headline(){}},
  add_custom_button:(name,fn)=>buttons.set(name,fn),remove_custom_button:name=>buttons.delete(name),
  page:{btn_primary:{},set_primary_action:(label,fn)=>primary={label,fn},clear_primary_action:()=>primary=null}};
 await handlers.Quotation.refresh(frm);
 return {frm,buttons,calls,messages,alerts,get primary(){return primary;},get saves(){return saves;},setDirty:v=>dirty=v};
}
(async()=>{
 const legacy={doctype:'Quotation Item',name:'legacy',custom_oman_use_costing_description:0,custom_oman_use_co_description:0};
 const co={doctype:'Quotation Item',name:'co',custom_oman_use_costing_description:0,custom_oman_use_co_description:1,custom_oman_client_description:'Client wording'};
 let r=await setup({rows:[legacy,co]});
 assert.equal(legacy.custom_oman_use_costing_description,1);assert.equal(legacy.custom_oman_use_co_description,0);
 assert.equal(co.custom_oman_use_costing_description,0);assert.equal(co.custom_oman_client_description,'Client wording');
 assert(r.frm.is_dirty());assert.equal(r.primary.label,'Save');
 // Even a native save promise that never resolves cannot leave a second button spinner.
 assert.equal(r.primary.fn(),undefined);assert.equal(r.saves,1);
 r=await setup({dirty:true});const save=r.primary.fn;r.setDirty(false);save();
 assert.equal(r.saves,0);assert.equal(r.primary.label,'Convert to PDF');assert.equal(r.alerts.length,1);
 r=await setup({issues:['Complete the required quotation fields.']});
 assert.equal(r.primary.label,'Convert to PDF');assert(r.buttons.has('Convert to PDF'));
 await r.primary.fn();assert.equal(r.messages.length,1);assert.match(r.messages[0].message,/required quotation fields/);
 assert(!r.calls.some(c=>c.method.endsWith('.convert_pdf')),'Other required fields still block a customer PDF');
 r=await setup({canWrite:false,rows:[{name:'read-only'}]});assert(!r.frm.is_dirty());
 console.log('PASS UAE saved-state actions, optional CO defaults, explicit CO preservation, read-only isolation, PDF blockers, and nonsettling native-save regression');
})().catch(e=>{console.error(e);process.exitCode=1;});
