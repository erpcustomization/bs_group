const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const root=path.resolve(__dirname,'..');
async function form(data,{dirty=false,doctype='Quotation',fresh=false,withGrid=false}={}){
 data={ready_to_convert:true,...data};
 const handlers={},calls=[],buttons=new Map(),primary=[];
 const frappe={ui:{form:{on(dt,h){handlers[dt]=h}}},call:async opts=>{calls.push(opts);return{message:data}},utils:{escape_html:s=>s},msgprint:()=>{},set_route:()=>{}};
 vm.runInNewContext(fs.readFileSync(path.join(root,'bsgroup/public/js/oman_quotation_flow.js'),'utf8'),{frappe,__:s=>s,window:{location:{reload(){}}}});
 const frm={doc:{name:'Q1',modified:'M1',custom_deal_cost_sheet:'DCS1',custom_pipeline_stage:'Delayed',items:[{}, {custom_oman_use_costing_description:1}],docstatus:doctype==='Quotation'?0:1},is_new:()=>fresh,is_dirty:()=>dirty,
  add_custom_button:(label,fn)=>buttons.set(label,fn),remove_custom_button:label=>calls.push(['remove',label]),set_df_property:()=>{},set_intro:()=>{},dashboard:{set_headline:()=>{}},
  page:{set_primary_action:(label,fn)=>primary.push(label),clear_primary_action:()=>primary.push('clear')}};
 let grid;
 if(withGrid){
  const fields_map=Object.fromEntries(['description','custom_oman_client_description','custom_oman_use_costing_description','custom_oman_use_co_description','qty','rate','amount'].map(fieldname=>[fieldname,{fieldname,label:fieldname==='description'?'Description':fieldname,read_only:0}]));
  grid={fields_map,update_docfield_property(name,key,value){fields_map[name][key]=value;},setup_user_defined_columns(){this.user_defined_columns=[fields_map.description];},reset_grid(){this.setup_user_defined_columns();}};
  frm.fields_dict={items:{grid}};
 }
 await handlers[doctype].refresh(frm);return{calls,buttons,primary,grid,frm};
}
(async()=>{
 let r=await form({enabled:false});assert.equal(r.buttons.size,0);assert.deepEqual(r.primary,[]);
 r=await form({enabled:true,editable:true,can_write:true,can_print:true,revision:1});assert(r.buttons.has('Convert to PDF'));assert(r.buttons.has('Change Status'));assert(r.buttons.has('Revise Costing Sheet'));assert.deepEqual(r.primary,['Convert to PDF']);
 r=await form({enabled:true,editable:true,can_write:true,can_print:true},{dirty:true});assert(!r.buttons.has('Convert to PDF'));assert.deepEqual(r.primary,['Save']);
 r=await form({enabled:true,editable:true,can_write:true,can_print:true,ready_to_convert:false});assert(!r.buttons.has('Convert to PDF'));assert.deepEqual(r.primary,['Save']);
 r=await form({enabled:true,editable:false,can_write:true,can_print:true});assert(!r.buttons.has('Change Status'));assert(!r.buttons.has('Revise Costing Sheet'));
 r=await form({enabled:true,editable:true,can_write:false,can_print:false});assert.equal(r.buttons.size,0);assert.deepEqual(r.primary,[]);
 r=await form({enabled:true,quotation:'Q1'},{doctype:'Deal Cost Sheet'});assert(r.buttons.has('View Linked Quotation'));assert(r.calls.some(c=>Array.isArray(c)&&c[1]==='Create Quotation'));
 r=await form({enabled:true,editable:true,can_write:true,can_print:true,client_descriptions:true},{withGrid:true});
 assert.equal(r.grid.fields_map.description.label,'Item Description (Costing)');assert.equal(r.grid.fields_map.description.read_only,1);
 assert.equal(r.frm.doc.items[0].custom_oman_use_co_description,1);assert.equal(r.frm.doc.items[1].custom_oman_use_co_description,0);
 assert.deepEqual(Array.from(r.grid.user_defined_columns,x=>x.fieldname),['custom_oman_use_costing_description','description','custom_oman_use_co_description','custom_oman_client_description','qty','rate','amount']);
 r=await form({enabled:false},{withGrid:true});assert.equal(r.grid.fields_map.custom_oman_client_description.hidden,1);assert.equal(r.grid.fields_map.description.read_only,0);
 r=await form({enabled:false},{fresh:true});assert.equal(r.calls.length,0);
 let renders=0;class ListView{get_args(){return{fields:['name']}}before_render(){renders++;return'original'}}
 const frappe={meta:{has_field:()=>true},views:{ListView}},settings={get_indicator:row=>['legacy','blue']};
 const list=Object.assign(new ListView(),{doctype:'Quotation',settings});const code=fs.readFileSync(path.join(root,'bsgroup/public/js/oman_quotation_flow_list.js'),'utf8');
 vm.runInNewContext(code,{frappe});vm.runInNewContext(code,{frappe});
 assert.equal(list.get_args().fields.length,3);assert.equal(list.before_render(),'original');assert.deepEqual(Array.from(settings.get_indicator({custom_oman_flow:1,custom_pipeline_stage:'Delayed'})).slice(0,2),['Delayed','orange']);assert.deepEqual(settings.get_indicator({custom_oman_flow:0}),['legacy','blue']);assert.equal(renders,1);
 list.settings={get_indicator:()=>['replacement','gray']};list.before_render();assert.equal(list.settings.get_indicator({custom_oman_flow:1,custom_pipeline_stage:'Won'})[0],'Won');
 const other=Object.assign(new ListView(),{doctype:'Customer',settings:{}});assert.equal(other.get_args().fields.length,1);other.before_render();assert.equal(other.settings.get_indicator,undefined);
 console.log('PASS Oman pilot form actions, Save/PDF states, frozen/read-only actions, DCS link, list indicators and legacy isolation');
})().catch(e=>{console.error(e);process.exitCode=1});
// Exercise the actual BOQ dialog's pilot and legacy field definitions.
// Choosing either checkbox always selects exactly one and invalidates the saved PDF action.
(async()=>{
 const handlers={},row={custom_oman_use_costing_description:1,custom_oman_use_co_description:1},actions=[];
 const frappe={ui:{form:{on(dt,h){handlers[dt]=h}}},get_doc:()=>row,model:{async set_value(dt,dn,values){Object.assign(row,values);}},utils:{},call:async()=>({})};
 vm.runInNewContext(fs.readFileSync(path.join(root,'bsgroup/public/js/oman_quotation_flow.js'),'utf8'),{frappe,__:s=>s,window:{}});
 const frm={__oman_client_descriptions:true,refresh_field:()=>{},remove_custom_button:x=>actions.push(x),page:{set_primary_action:x=>actions.push(x)}};
 await handlers['Quotation Item'].custom_oman_use_costing_description(frm,'Quotation Item','ROW1');
 assert.equal(row.custom_oman_use_co_description,0);assert.equal(row.custom_oman_use_costing_description,1);
 row.custom_oman_use_co_description=1;
 await handlers['Quotation Item'].custom_oman_use_co_description(frm,'Quotation Item','ROW1');
 assert.equal(row.custom_oman_use_costing_description,0);assert.equal(row.custom_oman_use_co_description,1);
 row.custom_oman_use_co_description=0;
 await handlers['Quotation Item'].custom_oman_use_co_description(frm,'Quotation Item','ROW1');
 assert.equal(row.custom_oman_use_costing_description,1);assert.equal(actions.at(-1),'Save');
 console.log('PASS mutually exclusive description choices and Save action');
})().catch(e=>{console.error(e);process.exitCode=1});
{
 const source=fs.readFileSync(path.join(root,'bsgroup/bs_group/doctype/deal_cost_sheet/deal_cost_sheet.js'),'utf8');
 const start=source.indexOf('function dcs_boq_revision_dialog('),end=source.indexOf('function dcs_refresh_draft(',start);
 let config;
 const context={__:s=>s,flt:v=>Number(v||0),cint:v=>Number(v||0),format_currency:String,dcs_money_precision:()=>3,dcs_boq_totals:()=>({cost:100,selling:150,margin:33.33}),
  frappe:{user:{has_role:()=>false},ui:{Dialog:class{constructor(c){config=c;this.fields_dict={preview:{$wrapper:{html(){}}}}}get_value(){return[]}show(){}}}}};
 vm.createContext(context);vm.runInContext(source.slice(start,end),context);
 for(const pilot of [true,false]){
  context.dcs_boq_revision_dialog({__oman_quotation_pilot:pilot,doc:{items:[],resources:[],custom_quotation:'Q1',currency:'OMR'}},{can_prepare_boq:1});
  const update=config.fields.find(f=>f.fieldname==='update_quotation'),review=config.fields.find(f=>f.fieldname==='acknowledge_quote_review');
  assert.equal(update.fieldtype,pilot?'HTML':'Check');assert.equal(review.hidden,pilot);
  if(pilot) assert.match(update.options,/same quotation updates automatically/);
 }
 console.log('PASS actual BOQ dialog forces automatic sync only for the Oman pilot');
}
