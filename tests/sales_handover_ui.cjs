const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('bsgroup/public/js/quotation.js','utf8').split('// The quotation\'s sales handover creates a standard Material Request.')[1];
function refresh(roles,{won=true,dirty=false,request=null}={}){
 const buttons=new Map(),routes=[];let handler;
 const frappe={ui:{form:{on:(dt,h)=>handler=h}},session:{user:'sales@example.com'},
  user:{has_role:wanted=>wanted.some(r=>roles.includes(r))},set_route:(...a)=>routes.push(a),utils:{escape_html:x=>x}};
 vm.runInNewContext(source,{frappe,__:x=>x});
 handler.refresh({doc:{docstatus:1,custom_pipeline_stage:won?'Won':'Sent',custom_deal_cost_sheet:'DCS-1',custom_bsp_material_request:request},
  toggle_reqd:()=>{},set_df_property:()=>{},is_dirty:()=>dirty,set_intro:()=>{},add_custom_button:(label,fn)=>buttons.set(label,fn)});
 return {buttons,routes};
}
for(const role of ['Sales User','BS Scoped Sales','Sales Manager','Commercial Controller','Managing Director']){
 assert(refresh([role]).buttons.has('Send to Procurement'),role);
 assert(!refresh([role],{dirty:true}).buttons.has('Send to Procurement'));
 assert(!refresh([role],{won:false}).buttons.has('Send to Procurement'));
}
for(const role of ['Employee','System Manager','Technical Engineer','Presales','BS Scoped Presales','Purchase User'])
 assert(!refresh([role]).buttons.has('Send to Procurement'),role);
for(const role of ['Sales User','BS Scoped Sales']){
 const r=refresh([role],{request:'MR-1'});r.buttons.get('View Purchase Requisition')();
 assert.deepEqual(r.routes,[['Form','Material Request','MR-1']]);
}
console.log('PASS all sales handover buttons, unsaved/unwon restrictions, non-sales denial and sender requisition route');
