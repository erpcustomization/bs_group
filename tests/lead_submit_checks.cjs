const fs=require('fs'),vm=require('vm'),assert=require('assert');
let handlers,row,saves=0,isNew=true,dirty=true,finish;
const note={value:'Call tomorrow'};
const status={style:{},querySelector:()=>row,prepend:r=>row=r};
const root={querySelector:s=>s==='.bsi-lead-outcome'?status:note};
const frm={wrapper:root,doc:{company_name:'Example',first_name:'Contact',custom_requirement:''},fields_dict:{},perm:[{create:1,write:1}],
    page:{clear_primary_action(){}},is_new:()=>isNew,is_dirty:()=>dirty,toggle_reqd(){},refresh_field(){},
    async set_value(k,v){this.doc[k]=v;},add_child(k,v){(this.doc[k] ||= []).push(v);},
    async save(){saves++;await new Promise(r=>finish=r);isNew=false;dirty=false;}};
for(const name of ['company_name','first_name','custom_requirement'])frm.fields_dict[name]={df:{fieldname:name,fieldtype:'Data',reqd:1},get_status:()=> 'Write',get_value:()=>frm.doc[name]};
const jq={off(){return this;},on(){return this;}};
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../bsgroup/public/js/lead_submit.js'),'utf8'),{
    document:{createElement:()=>({style:{},listeners:{},append(c){this.button=c;},querySelector(){return this.button;},addEventListener(e,f){this.listeners[e]=f;}})},
    $:()=>jq,__ :v=>v,setTimeout,clearTimeout,
    frappe:{ui:{form:{on(dt,h){handlers=h;}}},utils:{escape_html:v=>v},session:{user:'test'},datetime:{now_datetime:()=> '2026-10-26 12:00:00'},show_alert(){},throw(m){throw Error(m);}}
});
(async()=>{
    handlers.refresh(frm);assert(row.hidden,'missing requirement must hide submit');
    frm.doc.custom_requirement='Networking';handlers.bsi_lead_submission_changed(frm);assert(!row.hidden);
    assert.throws(()=>handlers.validate(frm),/Submit Lead/);
    const saving=row.button.listeners.click();
    await new Promise(r=>setTimeout(r,0));
    await row.button.listeners.click();assert.equal(saves,1);
    assert.equal(frm.doc.status,'Open');assert.equal(frm.doc.notes.length,1);
    assert.equal(frm.doc.opportunity_amount,undefined);handlers.validate(frm);
    finish();await saving;assert(row.hidden);assert.equal(row.button.textContent,'Save Changes');
    note.value='New follow-up';handlers.bsi_lead_submission_changed(frm);assert(!row.hidden);
    console.log('PASS required completion, explicit submission, Open status, pending notes, no value prompt and duplicate protection');
})().catch(e=>{console.error(e);process.exitCode=1;});
