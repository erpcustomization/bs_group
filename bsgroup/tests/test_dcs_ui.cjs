const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'../bs_group/doctype/deal_cost_sheet/deal_cost_sheet.js'),'utf8');
let dialog;
const context = {
  __:x=>x, flt:(x,p)=>p === undefined ? Number(x)||0 : Number((Number(x)||0).toFixed(p)),
  cint:x=>Number(x)||0, format_currency:x=>'AED '+Number(x).toFixed(2), format_number:x=>Number(x).toFixed(2),
  frappe:{
    ui:{form:{on(){}},Dialog:class {
      constructor(options) {
        Object.assign(this,options); this.values={}; this.fields_dict={};
        for(const f of options.fields) {
          this.values[f.fieldname]=f.default === undefined ? f.data : f.default;
          this.fields_dict[f.fieldname]={$wrapper:{html:v=>{this.fields_dict[f.fieldname].html=v;}}};
        }
        dialog=this;
      }
      get_value(name){return this.values[name];} show(){} hide(){}
    }},
    defaults:{get_default:()=> 'AED'}, utils:{escape_html:x=>String(x||''),get_form_link:()=> '#'},
    user:{has_role:()=>true}, datetime:{str_to_user:x=>x,comment_when:x=>x},
    call(){},msgprint(){},set_route(){}
  }
};
vm.createContext(context);
vm.runInContext(source.slice(source.indexOf('// Presentation only; server services')),context);
function fixture(extra={}) {
  const indicators=[],buttons={};
  const frm={
    doc:{name:'ZZTEST-UI',docstatus:1,currency:'AED',total_cost:14800,total_selling:16900,margin_value:2100,...extra},
    page:{set_inner_btn_group_as_primary:g=>{frm.group=g;},set_primary_action:(label,handler)=>{frm.primary={label,handler};}},
    dashboard:{add_indicator:(label,color)=>indicators.push({label,color}),set_headline:h=>{frm.headline=h;}},
    add_custom_button:(label,handler)=>{buttons[label]=handler;},is_dirty:()=>false,
    fields_dict:{},get_field:()=>null,
    indicators,buttons
  };
  return frm;
}
function sheet(extra={}) {
  return {ok:1,projection:'commercial',living:{revision_no:0,total_cost:0,total_selling:0},
    states:{customer_award:'Not Awarded',delivery_release:'Not Applicable'},
    authority:{can_record_award:1,can_reconcile_po:1,can_set_delivery_owner:1},conditions:{open_blockers:0},...extra};
}
const negotiator={ok:1,capability:{can_customer_side:1,can_vendor_side:1,can_negotiate:1}};
test('legacy Vendor Revision opens at actual AED 14800, with movement preview',()=>{
  const frm=fixture();context.dcs_buttons(frm,negotiator,{},sheet());frm.buttons['Vendor Revision']();
  assert.equal(dialog.values.new_total_cost,14800);
  assert.match(dialog.fields_dict.preview.html,/14800.00/);
});
test('legacy Customer Revision opens at actual AED 16900',()=>{
  const frm=fixture();context.dcs_buttons(frm,negotiator,{},sheet());frm.buttons['Customer Revision']();
  assert.equal(dialog.values.new_total_selling,16900);
});
test('initialised zero buying cost remains zero instead of reverting to saved BOQ cost',()=>{
  const p=context.dcs_effective_position(fixture(),sheet({living:{revision_no:2,total_cost:0,total_selling:16900}}));
  assert.equal(p.cost,0);
});
test('unpriced sheet reports Not evaluated and Not priced rather than approval clearance',()=>{
  const frm=fixture({total_selling:0});
  assert.equal(context.dcs_approval_presentation(frm,sheet()).label,'Not evaluated');
  context.dcs_headline(frm,sheet());
  assert.match(frm.headline,/Not priced/);assert.doesNotMatch(frm.headline,/No sign-off required/);
});
test('legacy below-floor sheet cannot advertise no sign-off',()=>{
  const frm=fixture();context.dcs_headline(frm,sheet());
  assert.match(frm.headline,/Not evaluated/);assert.doesNotMatch(frm.headline,/No sign-off required/);
});
test('zero handover conditions before award stays neutral',()=>{
  const frm=fixture();context.dcs_indicators(frm,sheet());
  assert.ok(frm.indicators.some(x=>x.label==='Handover not evaluated'&&x.color==='gray'));
  assert.ok(!frm.indicators.some(x=>x.label.includes('No open')&&x.color==='green'));
});
test('failed evaluation never produces a green handover clearance',()=>{
  const frm=fixture();context.dcs_indicators(frm,{ok:0,load_failed:1});
  context.dcs_headline(frm,{ok:0,load_failed:1,error:'Unavailable'});
  assert.match(frm.headline,/not available/);
  assert.ok(!frm.indicators.some(x=>x.color==='green'));
});
test('CC sees only server-permitted Endorse and Return actions',()=>{
  const frm=fixture(),s5=sheet({living:{revision_no:2,total_cost:1250,total_selling:1500,approval_required:'Managing Director',approval_state:'Pending Endorsement'}});
  context.dcs_buttons(frm,negotiator,{ok:1,actions:[{key:'Endorse',label:'Endorse to Managing Director'},{key:'Return for Rework',label:'Return for Rework',needs_reason:1}]},s5);
  assert.ok(frm.buttons.Endorse);assert.ok(frm.buttons['Return for Rework']);
  assert.equal(frm.buttons.Approve,undefined);assert.equal(frm.buttons.Reject,undefined);
  assert.equal(frm.primary.label,'Endorse to Managing Director');
});
test('rejection directs next action to BOQ revision and never offers another final decision',()=>{
  const frm=fixture(),s5=sheet({living:{revision_no:2,total_cost:1250,total_selling:1500,approval_required:'Managing Director',approval_state:'Rejected'}});
  context.dcs_buttons(frm,negotiator,{ok:1,actions:[]},s5);
  assert.equal(frm.buttons.Approve,undefined);assert.equal(frm.buttons.Reject,undefined);
  assert.equal(frm.primary.label,'Revise BOQ');
});
test('Approve dialog shows the server consequence and respects optional reason',()=>{
  const frm=fixture(),s5=sheet({living:{revision_no:2,total_cost:1250,total_selling:1500,approval_required:'Managing Director',approval_state:'Pending Endorsement'}});
  context.dcs_buttons(frm,negotiator,{ok:1,actions:[{key:'Approve',label:'Approve',needs_reason:0}],consequences:{approved:'Recorded MD exception; delivery remains separate.'}},s5);
  frm.buttons.Approve();
  assert.equal(dialog.fields.find(f=>f.fieldname==='reason').reqd,0);
  assert.match(dialog.fields.find(f=>f.fieldname==='why').options,/Recorded MD exception/);
});
test('technical view has no award, reversal, PO or release actions',()=>{
  const frm=fixture(),s5={ok:1,projection:'technical',states:{customer_award:'Awarded'},authority:{can_record_award:0,can_release:0,can_override:0}};
  context.dcs_buttons(frm,{ok:0},{ok:0},s5);
  for(const name of ['Record Award','Reverse Award','Reconcile Customer PO','Set Delivery Owner','Release to Delivery'])assert.equal(frm.buttons[name],undefined);
});
test('cancelled sheet offers no mutating actions',()=>{
  const frm=fixture({docstatus:2});context.dcs_buttons(frm,negotiator,{ok:1,actions:[{key:'Approve'}]},sheet());
  assert.equal(Object.keys(frm.buttons).length,0);assert.equal(frm.primary,undefined);
});
test('fully authorised current position selects Record Award as primary action',()=>{
  const frm=fixture(),s5=sheet({living:{revision_no:2,total_cost:1200,total_selling:1500,approval_required:'None',approval_state:'In Negotiation',authorised_position:1}});
  context.dcs_buttons(frm,negotiator,{ok:1,actions:[]},s5);
  assert.equal(frm.primary.label,'Record Award');
});
test('MD-approved below-floor position stays explicit about the margin exception',()=>{
  const p=context.dcs_approval_presentation(fixture(),sheet({living:{revision_no:2,total_cost:1250,total_selling:1500,approval_required:'Managing Director',approval_state:'Approved',authorised_position:1}}));
  assert.equal(p.label,'MD approved');assert.match(p.note,/Below the 20%/);
});
test('charges contribute buying, selling and GP to BOQ preview',()=>{
  const totals=context.dcs_boq_totals([{qty:1,cost_rate:1000,selling_rate:1500}],[],[{amount:100,selling_amount:150}]);
  assert.equal(totals.cost,1100);assert.equal(totals.selling,1650);assert.equal(totals.gp,550);
  assert.ok(Math.abs(totals.margin-100/3)<1e-8);
});
test('rendered BOQ dialog includes charge selling in its real preview',()=>{
  const frm=fixture({items:[{name:'row1',item_code:'ZZTEST',qty:1,cost_rate:1000,selling_rate:1500}],resources:[],addtional_charges:[{amount:100,selling_amount:150}]});
  context.dcs_boq_revision_dialog(frm,negotiator.capability);
  assert.match(dialog.fields_dict.preview.html,/Selling: <b>AED 1650.00/);
  assert.match(dialog.fields_dict.preview.html,/GP: <b>AED 550.00/);
});
test('after award the next step is PO reconciliation, not release',()=>{
  const s5=sheet({states:{customer_award:'Awarded',delivery_release:'Blocked'},po:{reconciliation_state:'Not Started'},authority:{can_release:1,can_reconcile_po:1}});
  assert.equal(context.dcs_next_step(fixture(),negotiator,{},s5).key,'Reconcile Customer PO');
});
test('all named release prerequisites must pass before Release becomes primary',()=>{
  const s5=sheet({states:{customer_award:'Awarded',delivery_owner:'ZZTEST owner',delivery_release:'Pending'},
    po:{reconciliation_state:'Reconciled'},authority:{can_release:1},release_readiness:{commercially_aligned:1},conditions:{open_blockers:1}});
  assert.notEqual(context.dcs_next_step(fixture(),negotiator,{},s5).key,'Release to Delivery');
  s5.conditions.open_blockers=0;
  assert.equal(context.dcs_next_step(fixture(),negotiator,{},s5).key,'Release to Delivery');
});
test('unsaved edits keep the framework Save action intact',()=>{
  const frm=fixture();frm.is_dirty=()=>true;
  context.dcs_buttons(frm,negotiator,{},sheet());
  assert.equal(frm.primary,undefined);
});
test('five tabs retain every existing standard field without duplication',()=>{
  const definition=JSON.parse(fs.readFileSync(path.join(__dirname,'../bs_group/doctype/deal_cost_sheet/deal_cost_sheet.json'),'utf8'));
  assert.deepEqual(definition.fields.filter(f=>f.fieldtype==='Tab Break').map(f=>f.label),['Overview','Costing','Revisions','Approval','Award & Handover']);
  assert.equal(new Set(definition.field_order).size,definition.field_order.length);
  assert.equal(definition.field_order.length,definition.fields.length);
});

test('a priced legacy sheet offers baseline evaluation without a dummy commercial change',()=>{
  const frm=fixture();context.dcs_buttons(frm,negotiator,{},sheet());
  assert.equal(frm.primary.label,'Evaluate submitted BOQ');
  let request;context.frappe.call=options=>{request=options;};
  frm.primary.handler();assert.equal(request.args.source,'Internal');
  assert.equal(request.args.new_total_cost,undefined);assert.equal(request.args.new_total_selling,undefined);
});
test('an unverified action response cannot produce a Recorded success alert',()=>{
  let message,success=false;
  context.frappe.call=options=>options.callback({message:{}});
  context.frappe.msgprint=options=>{message=options;};
  context.frappe.show_alert=()=>{success=true;};
  context.dcs_run(fixture(),'dcs_apply_revision',{});
  assert.equal(success,false);assert.equal(message.title,'Action not recorded');
});

test('Presales commercial read data survives an Award Workspace refusal without gaining award authority',()=>{
  const s2={ok:1,projection:'commercial',negotiation_guard:{revision_no:2,approval_state:'Rejected',approval_required:'Managing Director',authorised_position:0},margin_bridge:{current:{cost:1250,selling:1500,margin_percent:16.666}},award:{state:'Not Awarded'}};
  const view=context.dcs_read_view(s2,{ok:0,projection:'denied'}),frm=fixture();
  assert.equal(view.living.total_cost,1250);assert.equal(view.living.approval_state,'Rejected');
  context.dcs_buttons(frm,{ok:1,capability:{can_vendor_side:1,can_negotiate:1}},{ok:0},view);
  assert.equal(frm.buttons['Record Award'],undefined);assert.equal(frm.primary.label,'Revise BOQ');
});
test('a reduced or technical projection cannot be upgraded to a commercial read view',()=>{
  const denied={ok:0,projection:'denied'};
  assert.equal(context.dcs_read_view({ok:0,projection:'reduced'},denied),denied);
  assert.equal(context.dcs_read_view({ok:1,projection:'technical'},denied),denied);
});

test('a no-op response is labelled No change, never Recorded',()=>{
  let alert;const frm=fixture();frm.reload_doc=()=>{};
  context.frappe.call=options=>options.callback({message:{ok:1,no_change:1}});
  context.frappe.show_alert=options=>{alert=options;};
  context.dcs_run(frm,'dcs_apply_revision',{});
  assert.equal(alert.message,'No change — no revision recorded');assert.equal(alert.indicator,'blue');
});
