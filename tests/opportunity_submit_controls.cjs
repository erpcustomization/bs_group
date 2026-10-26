const fs=require('fs'),vm=require('vm'),assert=require('assert');
let handlers,row,saveCount=0,newRecord=true,releaseSave;
const root={querySelector(selector){return selector==='.bsi-opportunity-status'?status:row;}};
const status={before(element){row=element;}};
const frm={wrapper:root,doc:{custom_business_type:'Supply',party_name:'Customer',custom_subject:'Supply request',opportunity_amount:100},fields_dict:{},
  page:{hide_primary_action(){}},is_new(){return newRecord;},is_dirty(){return false;},
  async save(){saveCount++;await new Promise(resolve=>{releaseSave=resolve;});newRecord=false;}
};
for(const name of ['custom_business_type','party_name','custom_subject','opportunity_amount'])frm.fields_dict[name]={df:{fieldname:name,fieldtype:'Data',reqd:1},get_value:()=>frm.doc[name]};
const jq={off(){return this;},on(){return this;}};
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../bsgroup/public/js/opportunity_submit.js'),'utf8'),{
  document:{createElement(){return {style:{},listeners:{},append(child){this.button=child;},addEventListener(event,fn){this.listeners[event]=fn;}};}},
  $:()=>jq,__:(v)=>v,setTimeout,clearTimeout,
  frappe:{ui:{form:{on(type,events){handlers=events;}}},throw(message){throw Error(message);},show_alert(){},msgprint(){}}
});
async function run(){
  frm.doc.opportunity_amount=0;handlers.refresh(frm);assert(row.hidden);
  frm.doc.opportunity_amount=100;handlers.bsi_update_submit(frm);assert(!row.hidden);
  assert.throws(()=>handlers.validate(frm),/Submit Opportunity/);
  frm.doc.custom_presales_required=1;frm.doc.custom_elv_site_survey_required=1;frm.doc.custom_survey_step=2;
  handlers.bsi_update_submit(frm);assert(row.hidden,'incomplete survey cannot submit');
  Object.assign(frm.doc,{custom_survey_step:3,custom_survey_instructions:'Inspect',custom_survey_location:'Office',custom_survey_contact_name:'Contact',custom_survey_contact_phone:'1234567'});
  handlers.bsi_update_submit(frm);assert(!row.hidden);
  const pending=row.button.listeners.click();
  await row.button.listeners.click();assert.equal(saveCount,1,'double click cannot create twice');
  handlers.validate(frm);releaseSave();await pending;
  assert(row.hidden,'creation button disappears after success');
  console.log('PASS required fields, survey completion, explicit submission, and double-click protection');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
