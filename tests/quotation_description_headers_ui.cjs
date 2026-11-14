const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let source=fs.readFileSync(require('node:path').join(__dirname,'../bsgroup/public/js/oman_quotation_flow.js'),'utf8');
source=source.slice(0,source.lastIndexOf('})();'))+'window.test={descriptionHeaders,selectAllDescriptions};})();';
const headers={},handlers={},rows=[{doctype:'Quotation Item',name:'a',custom_oman_use_costing_description:1},{doctype:'Quotation Item',name:'b',custom_oman_use_costing_description:0,custom_oman_use_co_description:1,custom_oman_client_description:'Keep this wording'}];
const $=()=>({attrs:{},props:{},events:{},attr(k,v){this.attrs[k]=v;return this},prop(k,v){this.props[k]=v;return this},on(k,v){this.events[k]=v;return this}});
const wrapper={find(selector){if(selector==='.bs-description-select-all')return {remove(){for(const k of Object.keys(headers))delete headers[k]}};return {length:1,prepend(node){headers[selector.includes('use_costing')?'costing':'co']=node}}}};
const frappe={ui:{form:{on(dt,h){handlers[dt]=h}}},get_doc:(dt,name)=>rows.find(r=>r.name===name),model:{async set_value(dt,name,values){Object.assign(rows.find(r=>r.name===name),values)}},utils:{}};
const window={};vm.runInNewContext(source,{frappe,window,$,__:s=>s});
const frm={doc:{items:rows},__oman_client_descriptions:true,__bs_description_editable:true,fields_dict:{items:{grid:{wrapper}}},refresh_field(){window.test.descriptionHeaders(frm)},remove_custom_button(){},page:{set_primary_action(){}}};
(async()=>{
window.test.descriptionHeaders(frm);assert(headers.costing.props.indeterminate);assert(headers.co.props.indeterminate);
await headers.costing.events.change.call({checked:true});assert(rows.every(r=>r.custom_oman_use_costing_description===1&&r.custom_oman_use_co_description===0));assert(headers.costing.props.checked);
await headers.co.events.change.call({checked:true});assert(rows.every(r=>r.custom_oman_use_co_description===1&&r.custom_oman_use_costing_description===0));assert.equal(rows[1].custom_oman_client_description,'Keep this wording');
rows[0].custom_oman_use_costing_description=1;await handlers['Quotation Item'].custom_oman_use_costing_description(frm,'Quotation Item','a');assert(headers.costing.props.indeterminate);assert(headers.co.props.indeterminate);
await headers.co.events.change.call({checked:false});assert(rows.every(r=>r.custom_oman_use_costing_description===1));
rows.push({doctype:'Quotation Item',name:'new'});await handlers['Quotation Item'].items_add(frm,'Quotation Item','new');assert.equal(rows[2].custom_oman_use_costing_description,1);
frm.__bs_description_editable=false;window.test.descriptionHeaders(frm);assert(headers.costing.props.disabled);await window.test.selectAllDescriptions(frm,false);assert(rows.every(r=>r.custom_oman_use_costing_description===1));
console.log('PASS bulk selection, mixed headings, row override, new-row default, wording preservation and read-only protection');
})().catch(e=>{console.error(e);process.exitCode=1});
