const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync(require('path').join(__dirname, '../bsgroup/public/js/personal_column_widths.js'), 'utf8');
let nativeCalls = 0, saved = {}, calls = [];
class ListView {
  constructor() { this.doctype = 'Opportunity'; this.columns = [{df:{fieldname:'name'}}]; this.column_max_widths = {}; }
  before_render() {}
  save_column_width() { nativeCalls++; }
}
const frappe = {views:{ListView}, get_user_settings:()=>saved,
  model:{user_settings:{save:(dt,key,value)=>{calls.push({dt,key,value}); saved={...value}; return Promise.resolve();}}}};
vm.runInNewContext(source, {frappe});
const first = new ListView();
first.save_column_width('name', 300);
assert.equal(nativeCalls, 0);
assert.equal(calls[0].key, 'bs_column_widths');
const reopened = new ListView();
reopened.before_render();
assert.equal(reopened.columns[0].df.width, 300);
assert.equal(reopened.column_max_widths.name, 300);
saved = {}; // a different user's settings
const other = new ListView(); other.before_render();
assert.equal(other.columns[0].df.width, undefined);
other.list_filter={active_layout_name:'shared-layout'};
other.save_column_width('name', 350);
assert.equal(nativeCalls, 1); // existing named-layout permission checks retained
console.log('PASS: personal persistence, restoration, isolation and named-layout delegation');
