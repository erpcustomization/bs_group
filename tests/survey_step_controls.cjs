const fs = require('fs'), vm = require('vm'), assert = require('assert');
let handlers;
const elements = () => ({style:{}, listeners:{}, addEventListener(event,fn){this.listeners[event]=fn;}});
const frm = {doc:{custom_presales_required:1,custom_elv_site_survey_required:1,custom_survey_step:0},fields_dict:{},saves:[],
  set_df_property(){},toggle_display(){},trigger(){},is_dirty(){return false;},is_new(){return !!this.newRecord;},
  async set_value(k,v){this.doc[k]=v;}, async save(){this.saves.push(this.doc.custom_survey_step);}
};
for (const name of ['custom_survey_step','custom_survey_instructions','custom_survey_location','custom_survey_contact_name','custom_survey_contact_phone']) {
  const wrapper = {button:null,querySelector(){return this.button;},append(button){this.button=button;}};
  const jq = {0:wrapper,events:{},off(e){delete this.events[e];return this;},on(e,selector,fn){this.events[e]=fn;return this;}};
  frm.fields_dict[name] = {$wrapper:jq,get_value(){return this.inputValue || '';},set_focus(){this.focused=true;}};
  // Deliberately no $input: Frappe has not created the hidden control yet.
}
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../bsgroup/public/js/opportunity_survey_steps.js'),'utf8'),{
  document:{createElement:elements},__:(v)=>v,
  frappe:{ui:{form:{on(type,events){handlers=events;}}},show_alert(){},msgprint(){}}
});
async function run(){
  handlers.refresh(frm);
  const instructions=frm.fields_dict.custom_survey_instructions;
  instructions.inputValue='Inspect the equipment';
  instructions.$wrapper.events['input.bsi_survey']();
  assert.equal(instructions.$wrapper[0].button.hidden,false);
  await instructions.$wrapper[0].button.onclick();
  assert.equal(frm.doc.custom_survey_step,1);
  const location=frm.fields_dict.custom_survey_location;
  location.inputValue='Dubai Silicon Oasis';
  location.$wrapper.events['input.bsi_survey']();
  assert.equal(location.$wrapper[0].button.hidden,false,'lazy location input must reveal OK');
  await location.$wrapper[0].button.onclick();
  assert.equal(frm.doc.custom_survey_step,2);
  const phone=frm.fields_dict.custom_survey_contact_phone, contact=frm.fields_dict.custom_survey_contact_name;
  phone.inputValue='+971501234567';
  phone.$wrapper.events['input.bsi_survey']();
  assert.equal(phone.$wrapper[0].button.hidden,true,'name is also required');
  contact.inputValue='Site manager';
  contact.$wrapper.events['input.bsi_survey_contact']();
  assert.equal(phone.$wrapper[0].button.hidden,false);
  await phone.$wrapper[0].button.onclick();
  assert.equal(frm.doc.custom_survey_contact_name,'Site manager');
  assert.deepEqual(frm.saves,[1,2,3]);
  frm.newRecord = true;
  frm.doc.custom_survey_step = 0;
  handlers.refresh(frm);
  await instructions.$wrapper[0].button.onclick();
  await location.$wrapper[0].button.onclick();
  await phone.$wrapper[0].button.onclick();
  assert.equal(frm.doc.custom_survey_step,3);
  assert.deepEqual(frm.saves,[1,2,3],'new Opportunity OK steps must never create a record');
  console.log('PASS lazy input OK buttons, existing saves, and new draft confirmation without creation');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
