const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const source=fs.readFileSync(path.resolve(__dirname,'../bsgroup/public/js/oman_quotation_flow.js'),'utf8');
(async()=>{
 const handlers={},calls=[],opened=[],dialogs=[];let dirty=false,primary,fail=false;
 const frappe={ui:{form:{on(dt,h){handlers[dt]=h;}},Dialog:class{
  constructor(config){this.config=config;dialogs.push(this);}show(){this.shown=true;}hide(){this.hidden=true;}
  disable_primary_action(){this.disabled=true;}enable_primary_action(){this.disabled=false;}
 }},utils:{escape_html:String},msgprint(){},call:async opts=>{
  calls.push(opts);
  if(opts.method.endsWith('.pdf_templates'))return{message:{templates:['Template A','Template B'],selected:'Template A'}};
  if(opts.method.endsWith('.convert_pdf')){if(fail)throw Error('PDF failed');return{message:{file_url:'/private/files/test.pdf'}};}
  return{message:{enabled:true,editable:true,can_write:true,can_print:true,save_feedback:true,choose_pdf_template:true,pdf_issues:[]}};
 }};
 vm.runInNewContext(source,{frappe,__:s=>s,window:{open:(...args)=>opened.push(args)}});
 const frm={doc:{name:'Q1',modified:'M1',items:[]},is_new:()=>false,is_dirty:()=>dirty,
  add_custom_button(){},remove_custom_button(){},set_df_property(){},set_intro(){},dashboard:{set_headline(){}},
  page:{set_primary_action:(label,fn)=>primary=fn}};
 await handlers.Quotation.refresh(frm);await primary();
 assert.equal(dialogs.length,1);assert(dialogs[0].shown);
 assert(!calls.some(c=>c.method.endsWith('.convert_pdf')),'Opening/cancelling chooser cannot issue a PDF');
 const dialog=dialogs[0];assert.equal(dialog.config.fields[0].reqd,1);
 await dialog.config.primary_action({template:'Template B'});
 assert.equal(calls.find(c=>c.method.endsWith('.convert_pdf')).args.template,'Template B');
 assert.equal(opened[0][0],'/private/files/test.pdf');assert(dialog.hidden);assert(!dialog.disabled);
 await primary();fail=true;
 await assert.rejects(dialogs[1].config.primary_action({template:'Template A'}),/PDF failed/);
 assert(!dialogs[1].disabled);assert(!dialogs[1].hidden,'Failure leaves the chooser available');
 dirty=true;const before=calls.length;await primary();assert.equal(calls.length,before);
 console.log('PASS Oman template chooser, exact selected format, no premature issue, error recovery and unsaved protection');
})().catch(e=>{console.error(e);process.exitCode=1;});
