// Unit checks for the Quotation DCS alignment banner and mapping dialog (no browser, no server).
// Run: node bsgroup/tests/js/test_quotation_dcs_alignment.js
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('bsgroup/public/js/quotation.js', 'utf8');
const start = source.indexOf('// DCS draft / issue separation');
const end = source.indexOf('// Customer purchase order and sales-to-procurement handoff.');
assert.ok(start > 0 && end > start, 'alignment block sits before the procurement block');

const handlers = [], calls = [], set = [];
const escape = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const frappe = {
    ui: {form: {on: (_dt, h) => handlers.push(h)}},
    utils: {escape_html: escape},
    call: opts => calls.push(opts),
    model: {set_value: (dt, dn, f, v) => set.push([dn, f, v])},
    msgprint() {}, show_alert() {}, confirm() {}
};
const context = vm.createContext({frappe, __: (s, a) => a ? s.replace('{0}', a[0]) : s, format_currency: (v, c) => c + ' ' + Number(v).toFixed(2)});
vm.runInContext(source.slice(start, end), context);
let checks = 0;

// Banner: escaped, figures only when the server returned them, never cost.
const html = context.dcs_alignment_html({issuable: false, docstatus: 0, labels: ['Repriced', 'Bundled'], currency: 'AED',
    dcs_selling: 10000, quote_net: 10000, variance: 0, approval_state: 'Approved',
    problems: ['<img src=x onerror=alert(1)>'], actions: ['request_revision']});
assert.ok(!html.includes('<img'), 'problem text is escaped');
assert.match(html, /Draft - not for customer issue/);
assert.match(html, /Variance/);
assert.ok(!/cost|margin/i.test(html.replace(/Deal Cost Sheet/g, '')), 'no cost or margin wording');
checks++;
const hidden = context.dcs_alignment_html({issuable: false, docstatus: 0, labels: ['Repriced'], currency: 'AED', dcs_selling: null, problems: [], actions: []});
assert.ok(!hidden.includes('DCS selling'), 'figures withheld when not returned');
checks++;
assert.match(context.dcs_alignment_html({issuable: true, labels: ['Matching'], problems: [], actions: []}), /Ready to issue/);
checks++;

// Mapping problems: duplicates, uncovered rows and empty lines are all reported.
const rows = [{token: 'L1', label: 'Laptops'}, {token: 'I1', label: 'Installation'}];
let problems = context.dcs_mapping_problems({a: ['L1'], b: ['L1']}, rows);
assert.equal(problems.length, 2);
assert.ok(problems.some(p => p.includes('more than one line')));
assert.ok(problems.some(p => p.includes('Installation')));
problems = context.dcs_mapping_problems({a: ['L1', 'I1'], b: []}, rows);
assert.equal(problems.length, 1);
assert.match(problems[0], /no DCS source row/);
assert.equal(context.dcs_mapping_problems({a: ['L1', 'I1']}, rows).length, 0, 'an exact bundle has no problems');
checks++;

// Apply: only changed rows are written; untouched rows keep their value.
const frm = {doc: {items: [{doctype: 'Quotation Item', name: 'a', custom_dcs_source_rows: 'L1'},
    {doctype: 'Quotation Item', name: 'b', custom_dcs_source_rows: ''}]}, refresh_field() {}};
context.dcs_apply_mapping(frm, {a: ['L1'], b: ['I1']});
assert.deepEqual(set, [['b', 'custom_dcs_source_rows', 'I1']]);
checks++;

// Dialog HTML: existing mapping wins over a suggestion; labels are escaped; no cost is rendered.
const items = [{idx: 1, name: 'a', item_code: 'Generic', qty: 2, amount: 8000, custom_dcs_source_rows: 'L1'},
    {idx: 2, name: 'b', item_code: 'Generic', qty: 1, amount: 2000}];
const grid = context.dcs_mapping_html(items, {rows: [{token: 'L1', kind: 'item', label: '<b>Laptops</b>', qty: 2, selling_amount: 8000},
    {token: 'I1', kind: 'item', label: 'Install', qty: 1}], suggestions: {1: 'I1', 2: 'I1'}});
assert.ok(!grid.includes('<b>Laptops'), 'labels escaped');
assert.match(grid, /data-row="a"[^]*value="L1" selected/);
assert.match(grid, /data-row="b"[^]*value="I1" selected/);
assert.ok(!/cost/i.test(grid));
checks++;

// Buttons: drafts get Map DCS Rows; submitted and unsaved quotations do not.
const refresh = handlers[0].refresh;
function form(doc) {
    const buttons = [];
    return {doc, is_new: () => !doc.name, add_custom_button: (label) => buttons.push(label), buttons,
        dashboard: {set_headline_alert() {}}};
}
let f = form({name: 'Q-1', docstatus: 0, custom_deal_cost_sheet: 'DCS-1'});
refresh(f);
assert.deepEqual(f.buttons, ['Map DCS Rows']);
assert.equal(calls.at(-1).method, 'bsgroup.dcs.quote_alignment.alignment_summary');
f = form({name: 'Q-2', docstatus: 1, custom_deal_cost_sheet: 'DCS-1'});
refresh(f);
assert.deepEqual(f.buttons, []);
const before = calls.length;
refresh(form({docstatus: 0, custom_deal_cost_sheet: 'DCS-1'}));
refresh(form({name: 'Q-3', docstatus: 0}));
assert.equal(calls.length, before, 'no server call for unsaved or unlinked quotations');
checks++;

// Review action: offered only on drafts whose DCS revision moved, from the server's actions.
f = form({name: 'Q-4', docstatus: 0, custom_deal_cost_sheet: 'DCS-1'});
refresh(f);
calls.at(-1).callback({message: {issuable: false, actions: ['review_revision'], labels: ['Stale'], problems: []}});
assert.deepEqual(f.buttons, ['Map DCS Rows', 'Review DCS Revision']);
f = form({name: 'Q-5', docstatus: 0, custom_deal_cost_sheet: 'DCS-1'});
refresh(f);
calls.at(-1).callback({message: {issuable: false, actions: ['map_rows'], labels: ['Scope changed'], problems: []}});
assert.deepEqual(f.buttons, ['Map DCS Rows']);
checks++;

// Labels come from the server (row number, description, quantity, unit); Generic rows stay distinguishable.
const labelled = context.dcs_mapping_html([{idx: 1, name: 'a', item_code: 'Generic', qty: 1, amount: 1}], {suggestions: {},
    rows: [{token: 'L1', label: 'Row 1: Business laptop - 2 Nos'}, {token: 'I1', label: 'Row 2: Installation - 1 Nos'}]});
assert.match(labelled, /Row 1: Business laptop - 2 Nos/);
assert.match(labelled, /Row 2: Installation - 1 Nos/);
checks++;

console.log(checks + ' quotation DCS alignment UI checks passed');
