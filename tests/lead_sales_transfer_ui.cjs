const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
let handlers,hasRole=true,calls=[],route,dialog,reloads=0;
const frm={doc:{name:'LEAD-1',modified:'now',lead_owner:'priya'},perm:[{write:1}],
 is_new:()=>false,is_dirty:()=>false,assign_to:{add(){}},
 add_custom_button(label,fn){this.button=fn;},reload_doc:async()=>{reloads++;}};
const ctx={__:x=>x,frappe:{user:{has_role:()=>hasRole},ui:{form:{on(dt,h){handlers=h;}},
 Dialog:function(opts){dialog=opts;this.show=()=>{};this.hide=()=>{};}},
 msgprint(){},show_alert(){},set_route:async(...args)=>{route=args;},
 call:async req=>{calls.push(req);return {message:req.method.endsWith('.choices')?
 [{value:'paul',label:'Paul'}]:{lead_owner:req.args.to_user,can_read:false}};}}};
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../bsgroup/public/js/lead_assignment.js'),'utf8'),ctx);
(async()=>{
 handlers.refresh(frm);
 assert.equal(frm.assign_to.add,frm.button,'native Assign To must use the controlled handover');
 await frm.assign_to.add();
 assert.equal(dialog.fields[0].options[1].value,'paul');
 await dialog.primary_action({person:'paul'});
 assert.equal(calls[1].args.to_user,'paul');
 assert.equal(calls[1].args.expected_modified,'now');
 assert.deepEqual(route,['List','Lead']);
 assert.equal(reloads,0,'must not reload a Lead the previous owner no longer has access to');
 calls=[];frm.is_dirty=()=>true;await frm._bsi_sales_transfer('paul');assert.equal(calls.length,0);
 hasRole=false;handlers.refresh(frm);assert.equal(frm._bsi_sales_transfer,null);
 console.log('PASS sales handover button and native assignment, selected recipient/stale guard, safe navigation after transfer, unsaved-change and role guards');
})().catch(e=>{console.error(e);process.exitCode=1;});
