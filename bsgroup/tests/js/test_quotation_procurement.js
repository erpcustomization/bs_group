const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('bsgroup/public/js/quotation.js', 'utf8');
const handlers = [], calls = [], routes = [], messages = [];
let reads = 0, writes = 0, dialog, response, failure, checks = 0;
const check = (condition, label) => { assert.ok(condition, label); checks++; };
const frappe = {
    ui: {form: {on: (_dt, h) => handlers.push(h)}, Dialog: class {
        constructor(options) { this.options=options; this.disabled=false; dialog=this; }
        show() {} hide() { this.hidden=true; }
        disable_primary_action() { this.disabled=true; }
        enable_primary_action() { this.disabled=false; }
    }},
    db: {get_value: () => {reads++; return Promise.resolve({message:{customer_name:'Customer A'}});}},
    model: {can_read: () => false}, session: {user:'sales@example.com'},
    user: {has_role: () => true},
    utils: {escape_html: s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')},
    set_route: (...args) => routes.push({args, options:frappe.route_options}),
    call: async opts => {calls.push(opts); if(failure) throw failure; return {message:response};},
    msgprint: value => messages.push(value)
};
const context = vm.createContext({frappe, __: s => s, format_currency:(v,c)=>`${c} ${v}`});
vm.runInContext(source.slice(0, source.indexOf("frappe.ui.form.on('Quotation Item'")), context);
handlers[0].onload({doc:{}});
check(reads===0, 'No Employee lookup without read permission');
const start=source.indexOf('function set_lead_name(frm)');
vm.runInContext(source.slice(start, source.indexOf('function set_customer_item', start)), context);
context.set_lead_name({doc:{docstatus:1,party_name:'Customer A',quotation_to:'Customer'},set_value:()=>writes++});
check(reads===0 && writes===0, 'Submitted identity stays unchanged');
const marker='// The quotation\'s sales handover creates a standard Material Request.';
assert.ok(source.includes(marker));
vm.runInContext(source.slice(source.indexOf(marker)), context);
const flow=handlers.at(-1);
let buttons={},properties={};
const frm={doc:{docstatus:1,custom_deal_cost_sheet:'DCS-1',custom_pipeline_stage:'Won',name:'Q-1'},
    is_dirty:()=>false, set_df_property:(name,property,value)=>properties[name]=value,
    add_custom_button:(label,fn)=>buttons[label]=fn, reload_doc:async()=>{},set_intro:()=>{}};
(async()=>{
    flow.refresh(frm);
    check(!!buttons['Send to Procurement'],'Saved Won quotation exposes handover');
    response={dcs:'DCS-1',revision:'R1',customer_po:'<customer PO>',currency:'AED',required_by:'2026-10-27',
        warehouses:['Stores - AE'],resources:1,additional_charges:1,
        items:[{item_code:'<item>',qty:3,uom:'Nos',rate:100,is_stock_item:1}]};
    await buttons['Send to Procurement']();
    check(calls.length===1 && calls[0].method.endsWith('.handover_context') && routes.length===0,
        'Send previews the awarded source before creation');
    check(dialog.options.fields.find(f=>f.fieldname==='warehouse').reqd===1,
        'Stock handover requires a warehouse');
    check(dialog.options.fields.find(f=>f.fieldname==='schedule_date').reqd===1,
        'Handover requires a date');
    const summary=dialog.options.fields[0].options;
    check(summary.includes('&lt;item&gt;')&&summary.includes('&lt;customer PO&gt;'),
        'Source item and customer PO text are escaped');
    check(summary.includes('Only the Item lines below become purchasing lines'),
        'Non-item costs remain visible as attached evidence');
    response={name:'PR-1',doctype:'Material Request'};
    await dialog.options.primary_action({schedule_date:'2026-10-27',warehouse:'Stores - AE'});
    check(calls.at(-1).method.endsWith('.send_to_procurement')&&calls.at(-1).args.warehouse==='Stores - AE',
        'Creation carries source quotation, date and warehouse');
    check(routes.at(-1).args[0]==='bs-procurement'&&routes.at(-1).options.bsp_request==='PR-1',
        'Created standard PR opens in BS Procurement');
    check(dialog.hidden&&!dialog.disabled,'Creation closes dialog and restores action');
    buttons={};frm.is_dirty=()=>true;flow.refresh(frm);
    check(!buttons['Send to Procurement'],'Unsaved changes hide handover');
    frm.is_dirty=()=>false;buttons={};flow.refresh(frm);frm.is_dirty=()=>true;
    const before=calls.length;await buttons['Send to Procurement']();
    check(calls.length===before&&messages.length===1,'Changes after refresh also block sending');
    frm.is_dirty=()=>false;buttons={};frm.doc.custom_bsp_material_request='PR-1';flow.refresh(frm);
    check(!!buttons['View Purchase Requisition']&&!buttons['Send to Procurement'],
        'Existing PR exposes view without duplicate create');
    check(properties.custom_customer_po&&properties.custom_customer_po_reference,
        'Handed-over quotation source evidence is read only');
    buttons['View Purchase Requisition']();
    check(routes.at(-1).options.bsp_request==='PR-1','View returns to its own PR');
    delete frm.doc.custom_bsp_material_request;buttons={};flow.refresh(frm);
    response={existing:'PR-2'};await buttons['Send to Procurement']();
    check(routes.at(-1).options.bsp_request==='PR-2','Server-side replay opens existing PR');
    failure=new Error('Validation rejected');
    await assert.rejects(dialog.options.primary_action({schedule_date:'2026-10-27'}),/Validation rejected/);
    check(!dialog.disabled,'Failed create restores the dialog action');
    console.log(JSON.stringify({passed:checks,failed:0}));
})().catch(error=>{console.error(error);process.exitCode=1;});
