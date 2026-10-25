const fs=require('fs'), vm=require('vm'), assert=require('node:assert/strict');
const {parseHTML}=require('./bs_procurement/ui/node_modules/linkedom');
const {document,window}=parseHTML('<html><body><main></main></body></html>');
const root=document.querySelector('main');
function tab(name){const pane=document.createElement('div');pane.className='tab-pane';root.append(pane);return {df:{fieldname:name},wrapper:[pane],tab_link:{find:()=>({text(){}})},refresh(){},is_active:()=>name==='__details',set_active(){}};}
const tabs=['__details','activities_tab','notes_tab','bsi_ai_tab','custom_bsi_status_tab','dashboard_tab'].map(tab);
const fields_dict={};
for(const [name,i,type] of [['first_name',0,'Data'],['email_id',0,'Data'],['company',0,'Link'],['annual_revenue',0,'Currency'],['open_activities_html',1,'HTML'],['all_activities_html',1,'HTML'],['notes_html',2,'HTML'],['notes',2,'Table'],['bsi_ai_summary',3,'Text']]){
 const section=document.createElement('div');section.className='form-section';const node=document.createElement('div');node.className='frappe-control';const input=document.createElement('input');node.append(input);section.append(node);tabs[i].wrapper[0].append(section);fields_dict[name]={df:{fieldname:name,fieldtype:type,reqd:name==='company'?1:0},$wrapper:[node],tab:tabs[i]};
}
let edits=0;const email=fields_dict.email_id.$wrapper[0];email.firstChild.addEventListener('change',()=>edits++);
const frm={wrapper:root,layout:{tabs},fields_dict,doc:{name:'L1'},is_new:()=>false};
const ctx={document,__:x=>x,frappe:{ui:{form:{on(){}}},datetime:{str_to_user:x=>x},call:({callback})=>callback({message:{tasks:[{date:'2026-10-28'}],events:[{starts_on:'2026-10-27 11:00:00'}]}})}};vm.createContext(ctx);vm.runInContext(fs.readFileSync('bsgroup/public/js/lead_details.js','utf8')+';this.focus=bsi_lead_focus;',ctx);
ctx.focus.refresh(frm);ctx.focus.refresh(frm);
assert.deepEqual(tabs.filter(x=>!x.df.hidden).map(x=>x.df.fieldname),['__details','custom_bsi_status_tab']);
assert.equal(tabs[4].label,'Additional details');
assert.equal(root.querySelectorAll('.bsi-contact-card').length,1);
assert.equal(root.querySelector('.bsi-contact-card .frappe-control input'),fields_dict.first_name.$wrapper[0].firstChild);
assert.ok(tabs[4].wrapper[0].contains(fields_dict.company.$wrapper[0]));assert.equal(fields_dict.company.df.reqd,1);assert.equal(fields_dict.company.tab,tabs[4]);
assert.ok(root.querySelector('.bsi-follow-card').contains(fields_dict.open_activities_html.$wrapper[0]));assert.ok(root.querySelector('.bsi-notes-card').contains(fields_dict.notes_html.$wrapper[0]));
assert.equal(fields_dict.notes_html.tab,tabs[0]);assert.equal(fields_dict.all_activities_html.tab,tabs[4]);
assert.equal(root.querySelector('.bsi-next-follow-date').textContent,'2026-10-27 11:00:00');
email.firstChild.dispatchEvent(new window.Event('change'));assert.equal(edits,1);
console.log('PASS: two tabs, native contact/follow-up/notes controls preserved, required fields retained, validation navigation, earliest date, repeat refresh.');
