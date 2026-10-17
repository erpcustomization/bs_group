const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('bsgroup/public/js/quotation.js', 'utf8');
const handlers = [];
let requests = 0, routes = 0, writes = 0;
const frappe = {
    ui: {form: {on: (_dt, h) => handlers.push(h)}},
    db: {get_value: () => {requests++; return Promise.resolve({message:{customer_name:'Customer A'}});}},
    model: {can_read: () => false},
    user: {has_role: () => true},
    utils: {escape_html: s => s},
    set_route: () => routes++,
    call: opts => {requests++;opts.callback({message:{name:'PR-1'}});},
    msgprint: () => {}
};
const context = vm.createContext({frappe, __: s => s});
vm.runInContext(source.slice(0, source.indexOf("frappe.ui.form.on('Quotation Item'")), context);
const onload = handlers[0].onload;
onload({doc:{}});
assert.equal(requests, 0, 'No Employee lookup without read permission');
const start = source.indexOf('function set_lead_name(frm)');
vm.runInContext(source.slice(start, source.indexOf('function set_customer_item', start)), context);
context.set_lead_name({doc:{docstatus:1,party_name:'Customer A',quotation_to:'Customer'},set_value:()=>writes++});
assert.equal(requests, 0, 'Submitted identity must not fetch and rewrite contact fields');
assert.equal(writes, 0);
vm.runInContext(source.slice(source.indexOf('// Customer purchase order and sales-to-procurement handoff.')),context);
const flow = handlers.at(-1);
let buttons = {};
const frm = {doc:{docstatus:1,custom_deal_cost_sheet:'DCS-1',custom_pipeline_stage:'Won',name:'Q-1'},
    is_dirty:()=>false, set_df_property:()=>{},add_custom_button:(label,fn)=>buttons[label]=fn,
    reload_doc:()=>{},set_intro:()=>{}};
flow.refresh(frm);
assert.ok(buttons['Send to Procurement'], 'Saved Won quotation exposes handoff');
buttons['Send to Procurement']();
assert.equal(requests,1);assert.equal(routes,1);
buttons={};frm.is_dirty=()=>true;flow.refresh(frm);
assert.equal(buttons['Send to Procurement'],undefined,'Unsaved changes cannot be forwarded');
buttons={};frm.is_dirty=()=>false;frm.doc.custom_purchase_request='PR-1';flow.refresh(frm);
assert.ok(buttons['View Purchase Request']);assert.equal(buttons['Send to Procurement'],undefined);
console.log('6 quotation UI checks passed');
