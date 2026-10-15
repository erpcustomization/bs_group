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
  assert.equal(p.label,'Approved');assert.match(p.note,/Below the 20%/);
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
test('all tabs retain every existing standard field without duplication',()=>{
  const definition=JSON.parse(fs.readFileSync(path.join(__dirname,'../bs_group/doctype/deal_cost_sheet/deal_cost_sheet.json'),'utf8'));
  assert.deepEqual(definition.fields.filter(f=>f.fieldtype==='Tab Break').map(f=>f.label),['Overview','Costing','Revisions','Approval','Award & Handover','Deal & Scope']);
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

vm.runInContext(source.slice(source.indexOf('function render_summary_dashboard(frm) {'),source.indexOf('// Presentation only; server services')),context);
test('below-floor margin remains an exception color after MD approval',()=>{
  const frm=fixture(); let html;
  const current={cost:1250,selling:1500,gp:250,margin_percent:100/6};
  frm.fields_dict.custom_deal_summary_dashboard={$wrapper:{html:value=>{html=value;}}};
  frm.__dcs={s2:{ok:1,projection:'commercial',margin_bridge:{original:current,current,gp_impacts:{},gp_movement:0}},
    s3:negotiator,s4:{},s5:sheet({living:{revision_no:2,total_cost:1250,total_selling:1500,approval_required:'Managing Director',approval_state:'Approved',authorised_position:1}})};
  context.render_summary_dashboard(frm);
  assert.match(html,/Approved/);
  assert.match(html,/dcs-tone-danger">16.67%/);
  assert.doesNotMatch(html,/dcs-tone-success">16.67%/);
  assert.match(html,/Below the 20% floor/);
});
test('the redesigned overview never exposes figures in a reduced commercial projection',()=>{
  const frm=fixture();let html;
  frm.fields_dict.custom_deal_summary_dashboard={$wrapper:{html:value=>{html=value;}}};
  frm.__dcs={s2:{ok:1,projection:'reduced'},s5:{ok:0}};
  context.render_summary_dashboard(frm);
  assert.doesNotMatch(html,/14800|16900|Current selling|Gross profit/);
  assert.match(html,/not available/);
});
test('margin floor color handles exact 20%, negative and unpriced positions',()=>{
  assert.equal(context.dcs_margin_tone(20),'dcs-tone-success');
  assert.equal(context.dcs_margin_tone(19.999),'dcs-tone-danger');
  assert.equal(context.dcs_margin_tone(-2),'dcs-tone-danger');
  assert.equal(context.dcs_margin_tone(null),'dcs-tone-neutral');
});

test('current manager approval uses manager wording and keeps below-floor warning',()=>{
  const frm=fixture(),view=sheet({living:{revision_no:2,total_cost:1250,total_selling:1500,approval_required:'Manager',approval_state:'Approved',authorised_position:1}});
  const result=context.dcs_approval_presentation(frm,view);
  assert.equal(result.label,'Manager approved');assert.match(result.note,/Below the 20%/);
});
test('reportee routing headline contains manager identity and no commercial figures',()=>{
  const frm=fixture();frm.__dcs={s4:{projection:'approval-routing',deal:{approval_state:'Pending Manager'},manager_route:{approval_manager:'manager@example.com',approval_manager_name:'Immediate Manager'}}};
  context.dcs_headline(frm,{ok:0});
  assert.match(frm.headline,/Immediate Manager/);assert.doesNotMatch(frm.headline,/14800|16900|Gross profit/);
});
test('a reduced reportee projection offers only repair of its own missing route',()=>{
  const frm=fixture();context.frappe.session={user:'reportee@example.com'};
  frm.__dcs={s4:{manager_route:{changed_by:'reportee@example.com',approval_routing_error:'Set Reports To'}}};
  const next=context.dcs_next_step(frm,{}, {}, {ok:0});
  assert.equal(next.key,'Refresh Manager Routing');
  context.frappe.session={user:'someoneelse@example.com'};
  assert.notEqual(context.dcs_next_step(frm,{}, {}, {ok:0}).key,'Refresh Manager Routing');
  delete context.frappe.session;
});

test('reportee with a routed exception waits for the named manager',()=>{
  const frm=fixture();frm.__dcs={s4:{manager_route:{approval_manager_name:'Direct Manager'}}};
  const next=context.dcs_next_step(frm,{}, {deal:{approval_required:'Manager'}},sheet());
  assert.equal(next.label,'Await manager decision');assert.match(next.note,/Direct Manager/);assert.equal(next.key,undefined);
});
test('empty new draft never renders zero metrics or previous deal figures',()=>{
  const frm=fixture({docstatus:0,__islocal:1,total_cost:0,total_selling:0,items:[],resources:[],addtional_charges:[]});let html;
  frm.fields_dict.custom_deal_summary_dashboard={$wrapper:{html:v=>{html=v;}}};
  frm.__dcs={s2:{ok:1,projection:'commercial',margin_bridge:{original:{cost:3787.5,selling:7182.5},current:{cost:3787.5,selling:7182.5}}},s5:sheet()};
  context.render_summary_dashboard(frm);
  assert.match(html,/Enter customer and scope details first/);
  assert.doesNotMatch(html,/3787|7182|AED 0.00|Original|Current selling|AWARD|Not evaluated/);
  assert.equal(Object.keys(frm.__dcs).length,0);
});
test('draft headline figures use entered BOQ rows despite delayed document totals',()=>{
  const frm=fixture({docstatus:0,total_cost:0,total_selling:0,items:[{qty:1,cost_rate:3787.5,selling_rate:7182.5}],resources:[],addtional_charges:[]});let html;
  frm.fields_dict.custom_deal_summary_dashboard={$wrapper:{html:v=>{html=v;}}};
  frm.__dcs={s2:{ok:1,projection:'commercial',margin_bridge:{current:{cost:999,selling:999}}},s5:sheet()};
  context.render_summary_dashboard(frm);
  assert.match(html,/AED 7182.50/);assert.match(html,/AED 3787.50/);assert.match(html,/AED 3395.00/);assert.match(html,/47.27%/);
  assert.doesNotMatch(html,/Original|999.00|R0|new-deal/);
  frm.doc.items[0].selling_rate=8000;context.render_summary_dashboard(frm);
  assert.match(html,/AED 8000.00/);assert.match(html,/AED 4212.50/);assert.doesNotMatch(html,/7182.50/);
});
test('draft ignores inherited living revisions and shows estimate instead of approval clearance',()=>{
  const frm=fixture({docstatus:0,custom_dcs_revision_no:3,total_cost:0,total_selling:0,items:[{qty:2,cost_rate:100,selling_rate:150}]});
  const old=sheet({living:{revision_no:3,total_cost:9999,total_selling:19999,approval_required:'None',authorised_position:1}});
  const p=context.dcs_effective_position(frm,old);
  assert.equal(p.revision_no,0);assert.equal(p.cost,200);assert.equal(p.selling,300);
  assert.equal(context.dcs_approval_presentation(frm,old).label,'Draft estimate');
});
test('reduced draft view exposes selling only and never buying, GP or margin',()=>{
  const original=context.frappe.user.has_role;context.frappe.user.has_role=()=>false;
  try {
    const frm=fixture({docstatus:0,items:[{qty:1,cost_rate:987,selling_rate:1500}]});let html;
    frm.fields_dict.custom_deal_summary_dashboard={$wrapper:{html:v=>{html=v;}}};
    context.render_summary_dashboard(frm);
    assert.match(html,/AED 1500.00/);assert.doesNotMatch(html,/987|513|Buying|Gross profit|Gross margin/);
  } finally {context.frappe.user.has_role=original;}
});
test('draft load clears the prior record and makes no persisted-deal RPC calls',()=>{
  const frm=fixture({docstatus:0,__islocal:1,total_cost:0,total_selling:0});let calls=0;
  frm.__dcs={s2:{ok:1,projection:'commercial'}};frm.__dcs_load_id=5;
  const old=context.frappe.call;context.frappe.call=()=>{calls++;};
  try {context.dcs_load(frm);assert.equal(calls,0);assert.equal(frm.__dcs_load_id,6);assert.equal(Object.keys(frm.__dcs).length,0);assert.match(frm.headline,/Enter customer and scope details/);}
  finally {context.frappe.call=old;}
});
test('customer and scope entry precede draft summary and costing without losing fields',()=>{
  const d=JSON.parse(fs.readFileSync(path.join(__dirname,'../bs_group/doctype/deal_cost_sheet/deal_cost_sheet.json'),'utf8'));
  const order=d.field_order;
  assert.ok(order.indexOf('party')<order.indexOf('scope_overview'));
  assert.ok(order.indexOf('scope_overview')<order.indexOf('custom_deal_summary_dashboard'));
  assert.ok(order.indexOf('dcs_costing_tab')<order.indexOf('dcs_overview_tab'));
  assert.equal(order[0],'dcs_details_tab');
  assert.deepEqual(order.filter(n=>d.fields.find(f=>f.fieldname===n).fieldtype==='Tab Break').map(n=>d.fields.find(f=>f.fieldname===n).label),['Deal & Scope','Costing','Revisions','Approval','Award & Handover','Overview']);
  assert.equal(new Set(order).size,order.length);assert.equal(order.length,d.fields.length);
});
test('near-floor margin displays enough precision to explain the blocked gate',()=>{
  assert.equal(context.dcs_pct(19.996667),'19.9967%');
  assert.equal(context.dcs_pct(20),'20.00%');
});
test('changed award takes priority over customer PO reconciliation',()=>{
  const frm=fixture();
  const result=context.dcs_next_step(frm,negotiator,{},sheet({
    living:{revision_no:2,total_cost:1000,total_selling:1500,authorised:1},
    states:{customer_award:'Awarded'},release_readiness:{commercially_aligned:0}
  }));
  assert.equal(result.label,'Review changed award');
});
test('unpriced draft rows are identified without blocking draft work',()=>{
  const frm=fixture({docstatus:0,items:[{qty:1,cost_rate:1000,selling_rate:0}]});
  let html;
  context.dcs_render_draft_summary(frm,{$wrapper:{html:v=>html=v}});
  assert.match(html,/no selling price/);
  assert.match(html,/incomplete pricing estimate/);
});
test('timeline buying and selling labels state before to after and isolate direction',()=>{
  assert.match(source,/Buying: before → after/);
  assert.match(source,/dir="ltr" style="white-space:nowrap"/);
});
test('opportunity-derived customer field is never populated with a lead or organisation string',()=>{
  assert.doesNotMatch(source,/frm\.set_value\("customer", res\.message\.custom_organization_name\)/);
  assert.match(source,/customer:r\.opportunity_from === 'Customer' \? r\.party_name : ''/);
});

test('negative draft costs show an error instead of an inflated margin',()=>{
  const frm=fixture({docstatus:0,items:[{qty:10,cost_rate:1250,selling_rate:1500}],resources:[{no_of_persons:1,no_of_days:1,cost_rate:-2000}]});
  let html;
  context.dcs_render_draft_summary(frm,{$wrapper:{html:v=>html=v}});
  assert.match(html,/Correct invalid costing inputs/);
  assert.doesNotMatch(html,/Gross margin|30.00%/);
});
test('revision movement isolates currency values and preserves before / after DOM order',()=>{
  const html=context.dcs_revision_movement(fixture(),15000,14000,false);
  assert.ok(html.indexOf('15000')<html.indexOf('→'));
  assert.ok(html.indexOf('→')<html.indexOf('14000'));
  assert.equal((html.match(/<bdi dir="ltr">/g)||[]).length,2);
});
