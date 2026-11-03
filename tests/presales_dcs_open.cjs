const fs=require('fs'),vm=require('vm'),assert=require('assert');
let submit, routes=[];
const frm={doc:{name:'PR1'}};
const context={window:{cur_frm:frm},frappe:{ui:{form:{on:(dt,handlers)=>{submit=handlers.on_submit;}}},
call:async()=>({message:'DCS1'}),set_route:(...args)=>routes.push(args)}};
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../bsgroup/public/js/presales_dcs_handoff.js'),'utf8'),context);
(async()=>{
 await submit(frm); assert.deepStrictEqual(routes,[['Form','Deal Cost Sheet','DCS1']]);
 routes=[]; context.window.cur_frm={}; await submit(frm); assert.equal(routes.length,0);
 context.window.cur_frm=frm; context.frappe.call=async()=>({message:null}); await submit(frm); assert.equal(routes.length,0);
 console.log('PASS: opens returned DCS after submit; no redirect after navigation or without a valid link');
})().catch(e=>{console.error(e);process.exitCode=1;});
