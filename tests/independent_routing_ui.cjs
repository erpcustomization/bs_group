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
    console.log('PASS both forms show independent required choices; survey does not enable presales');
})();
