const fs=require('fs'), vm=require('vm'), assert=require('assert');
const source=fs.readFileSync('bsgroup/public/js/linked_site_survey.js','utf8');
let handlers={}, dialog, confirm, calls=0,reloads=0,buttons={};
const frappe={session:{user:'mohan@bitssecureit.com'},ui:{form:{on:(type,h)=>handlers[type]=h},Dialog:function(opts){dialog=opts;this.show=()=>{};this.hide=()=>{};this.get_primary_btn=()=>({prop:()=>{}});}},confirm:(text,yes)=>{confirm={text,yes};},call:async()=>{calls++;return {message:{created:true,name:'SSR-TEST'}}},msgprint:()=>{}};
vm.runInNewContext(source,{frappe,__:(s)=>s,DOMParser:function(){}});
const frm={doctype:'Opportunity',doc:{name:'OPP-TEST',docstatus:0,status:'Open',custom_technical_site_survey_required:1,custom_survey_instructions:'Keep these instructions',custom_survey_location:'Test location',custom_survey_contact_name:'Test contact',custom_survey_contact_phone:'000'},is_new:()=>false,is_dirty:()=>true,perm:[{write:1}],remove_custom_button:()=>{},add_custom_button:(label,fn)=>buttons[label]=fn,reload_doc:async()=>reloading(),layout:{tabs:[]}};
function reloading(){reloads++;}
(async()=>{
await handlers.Opportunity.refresh(frm);buttons['Request Site Survey']();
assert(confirm && !dialog);assert.equal(reloads,0);assert.equal(calls,0);
confirm.yes();assert(dialog);assert.equal(dialog.fields.find(f=>f.fieldname==='instructions').default,'Keep these instructions');
assert.equal(dialog.fields.find(f=>f.fieldname==='team').default,'Technical Team');
await dialog.primary_action({team:'Technical Team',instructions:'TEST',location:'TEST',contact_name:'TEST',contact_phone:'000'});
assert.equal(calls,1);assert.equal(reloads,1);
frappe.session.user='paul@bitssecureit.com';buttons={};await handlers.Opportunity.refresh(frm);assert.equal(Object.keys(buttons).length,0);
console.log('PASS: dirty form opens request after disclosure, carries entered details, saves once, reloads only after success, and remains Mohan-only');
})().catch(e=>{console.error(e);process.exitCode=1});
