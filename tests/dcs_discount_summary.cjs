const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('bsgroup/bs_group/doctype/deal_cost_sheet/deal_cost_sheet.js','utf8');
const start=src.indexOf('function dcsLiveCalc('),end=src.indexOf('\nfunction ',start+1);
const code=src.slice(start,end);
const sandbox={flt:x=>Number(x||0),cint:x=>Number(x||0),format_currency:x=>Number(x).toFixed(2),
    frappe:{format:x=>Number(x).toFixed(2)},dcs_money_precision:()=>2};
vm.createContext(sandbox);vm.runInContext(code,sandbox);
const wrapper={innerHTML:''};
const doc={currency:'AED',custom_dcs_revision_no:2,custom_working_total_selling:218000,
    custom_working_total_cost:174609,custom_working_margin_percent:19.90412844,
    items:[{qty:1,cost_rate:174609,selling_rate:240419.33}],
    addtional_charges:[{amount:0,selling_amount:1370}]};
sandbox.dcsLiveCalc({doc,fields_dict:{commercial_summary_html:{wrapper}}},false);
assert(wrapper.innerHTML.includes('241789.33'));
assert(wrapper.innerHTML.includes('-23789.33'));
assert(wrapper.innerHTML.includes('218000.00'));
assert(wrapper.innerHTML.includes('174609.00'));
assert(wrapper.innerHTML.includes('Additional Charges'));
assert.equal(doc.items[0].cost_rate,174609);
console.log('PASS: customs, gross subtotal, discount, net margin and unchanged costs');
