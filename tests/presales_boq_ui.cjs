const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(require('path').join(__dirname,
  '../bsgroup/bs_group/doctype/deal_cost_sheet/deal_cost_sheet.js'), 'utf8');
const section = (start, end) => source.slice(source.indexOf('function ' + start), source.indexOf('function ' + end));
let dialog, submitted, html = '', appended = '';
const context = {
  __: x => x, flt: x => Number(x || 0), cint: x => Number(x || 0),
  format_currency: x => String(x), dcs_money_precision: () => 2,
  dcs_boq_totals: () => ({cost: 10, selling: 20, margin: 50}),
  dcs_esc: x => String(x), dcs_panel: (title, body) => title + body,
  dcs_set_html: (frm, field, value) => {html = value;},
  dcs_run: (frm, action, values) => {submitted = values;},
  frappe: {
    utils: {get_form_link: (type, name) => '/app/' + name},
    call() {throw new Error('Rendering must not fetch a restricted child DocType');},
    user: {has_role: () => false},
    ui: {Dialog: function(options) {
      dialog = options;
      this.fields_dict = {preview: {$wrapper: {html() {}}}};
      this.get_value = () => [];
      this.show = () => {};
    }}
  }
};
vm.createContext(context);
vm.runInContext(section('dcs_render_award', 'dcs_render_handover') +
  section('dcs_boq_revision_dialog', 'dcs_refresh_draft'), context);
const frm = {doc: {name:'DCS-assigned', custom_quotation:'Q-sales', items:[], resources:[]},
  get_field: () => ({$wrapper: {append(value) {appended = value;}}})};
for (const state of [null, {ok:0, projection:'denied'}, {ok:1, projection:'technical'}]) {
  context.dcs_render_award(frm, state);
  assert.equal(html, '');
}
context.dcs_render_award(frm, {ok:1, projection:'commercial', award_reversals:[
  {name:'REV-1', reversal_no:1, reversal_reason:'Verified history', status:'Recorded'}]});
assert(appended.includes('Verified history'));
const cap = {can_prepare_boq:1, can_customer_side:0, can_vendor_side:1};
context.dcs_boq_revision_dialog(frm, cap);
const table = dialog.fields.find(f => f.fieldname === 'boq_items');
assert.equal(table.cannot_add_rows, false);
assert.equal(table.cannot_delete_rows, false);
for (const key of ['item_code','description','qty','cost_rate','selling_rate']) {
  assert.equal(table.fields.find(f => f.fieldname === key).read_only, 0, key);
}
assert.equal(cap.can_customer_side, 0, 'BOQ capability must not grant negotiation authority');
dialog.primary_action({source:'Technical', reason:'Changed scope', boq_items:[
  {item_code:'NEW', qty:2, cost_rate:10, selling_rate:20}], update_quotation:1});
assert.equal(submitted.items[0].selling_rate, 20);
assert.equal(submitted.items[0].qty, 2);
context.dcs_boq_revision_dialog(frm, {can_customer_side:0, can_vendor_side:1});
assert.equal(dialog.fields.find(f => f.fieldname === 'boq_items').cannot_add_rows, true);
assert.equal(dialog.fields.find(f => f.fieldname === 'boq_items').fields.find(f => f.fieldname === 'selling_rate').hidden, true);
console.log('PASS scoped BOQ controls and payload, unchanged negotiation/vendor controls, no restricted history request');
