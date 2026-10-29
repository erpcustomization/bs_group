const assert = require('node:assert/strict');
const fs = require('node:fs');
let handlers;
global.frappe = {ui:{form:{on:(_type, events)=>handlers=events}}};
global.__ = value => value;
eval(fs.readFileSync('bsgroup/public/js/opportunity_intake.js','utf8'));
(async()=>{
    for (const kind of ['Service','Supply and Installation']) {
        for (const support of ['No','Yes']) {
            const display = {}, required = {};
            const frm = {doc:{custom_business_type:kind, custom_presales_support:support, custom_service_survey:'Site Survey by ELV'},
                fields_dict:{custom_business_type:{}}, is_new:()=>true,
                layout:{refresh_dependency(){}},
                set_df_property(){}, toggle_display:(field,value)=>display[field]=value,
                toggle_reqd:(field,value)=>required[field]=value,
                set_value:async values=>Object.assign(frm.doc,values)};
            await handlers.refresh(frm);
            assert.equal(display.custom_service_survey,true);
            assert.equal(display.custom_presales_support,true);
            assert.equal(required.custom_presales_support,true);
            assert.equal(frm.doc.custom_elv_site_survey_required,1);
            assert.equal(frm.doc.custom_presales_required, support==='Yes' ? 1 : 0);
            assert.equal(display.custom_presales_required,false);
        }
    }
    // A new form first evaluates dependencies while its category is blank.
    const fields = Object.fromEntries(['custom_service_survey','custom_presales_support'].map(name=>[name,{hidden_due_to_dependency:true}]));
    const frm = {doc:{}, fields_dict:{custom_business_type:{}}, is_new:()=>true,
        set_df_property(name,key,value){if(fields[name]) fields[name][key]=value;},
        toggle_display(name,value){if(fields[name]) fields[name].hidden=!value;},
        toggle_reqd(){}, set_value:async values=>Object.assign(frm.doc,values),
        layout:{refresh_dependency(){
            for (const field of Object.values(fields)) {
                if (field.depends_on) field.hidden_due_to_dependency = !Function('doc', 'return '+field.depends_on.slice(5))(frm.doc);
            }
        }}};
    for (const kind of ['', 'Supply and Installation', 'Supply', 'Service', 'Supply and Installation']) {
        frm.doc.custom_business_type=kind;
        await handlers.refresh(frm);
        for (const field of Object.values(fields)) {
            assert.equal(!field.hidden && !field.hidden_due_to_dependency, ['Service','Supply and Installation'].includes(kind));
        }
    }
    console.log('PASS initially blank form and category switching update dependency visibility');
    console.log('PASS both forms show independent required choices; survey does not enable presales');
})();
