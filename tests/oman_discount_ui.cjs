const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const code=fs.readFileSync(path.join(__dirname,'../bsgroup/public/js/oman_quotation_flow.js'),'utf8');
async function refresh({enabled=true,editable=true,canWrite=true,basis='Grand Total',policy=true}={}){
  const handlers={},changes=[],properties=[],primary=[],buttons=new Map();let dirty=false;
  const data={enabled,editable,can_write:canWrite,can_print:true,ready_to_convert:true,discount_before_vat:policy};
  const frappe={ui:{form:{on(dt,h){handlers[dt]=h;}}},call:async()=>({message:data}),utils:{escape_html:s=>s}};
  vm.runInNewContext(code,{frappe,__:s=>s,window:{}});
  const frm={doc:{name:'TEST-Q',docstatus:editable?0:1,apply_discount_on:basis,custom_pipeline_stage:'Draft'},
    is_new:()=>false,is_dirty:()=>dirty,
    async set_value(key,value){changes.push([key,value]);this.doc[key]=value;dirty=true;},
    set_df_property:(...args)=>properties.push(args),set_intro:()=>{},dashboard:{set_headline:()=>{}},
    add_custom_button:(label,fn)=>buttons.set(label,fn),remove_custom_button:label=>buttons.delete(label),
    page:{set_primary_action:label=>primary.push(label),clear_primary_action:()=>{}}};
  await handlers.Quotation.refresh(frm);return {frm,changes,properties,primary,buttons};
}
(async()=>{
  let r=await refresh();assert.equal(r.frm.doc.apply_discount_on,'Net Total');assert.equal(r.changes.length,1);
  assert(r.properties.some(p=>p[0]==='apply_discount_on'&&p[1]==='read_only'&&p[2]===1));
  assert.equal(r.primary.at(-1),'Save');assert(!r.buttons.has('Convert to PDF'));
  r=await refresh({basis:'Net Total'});assert.equal(r.changes.length,0);assert.equal(r.primary.at(-1),'Convert to PDF');
  for(const opts of [{enabled:false},{editable:false},{canWrite:false},{policy:false}]){
    r=await refresh(opts);assert.equal(r.changes.length,0);assert.equal(r.frm.doc.apply_discount_on,'Grand Total');
  }
  console.log('PASS Oman discount basis, native field update, Save/PDF states, read-only access, historical and UAE isolation');
})().catch(e=>{console.error(e);process.exitCode=1;});
