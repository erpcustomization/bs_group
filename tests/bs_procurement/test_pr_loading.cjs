const fs=require('fs'), vm=require('vm'), assert=require('assert');
const source=fs.readFileSync('bsgroup/bs_group/page/bs_procurement/bs_procurement.js','utf8');
async function test(approved) {
 const target={innerHTML:''}, root={dataset:{},innerHTML:'',querySelector:s=>s==='.bsp-view'?target:null,querySelectorAll:()=>[],addEventListener(){}};
 const calls=[],errors=[];
 const request={id:'MR-QC',approval:approved?'Approved':'Pending Approval',company:'QC',currency:'AED',actions:[],history:[],orders:[],items:[{sourceId:'ROW',item_code:'Generic',item_name:'Generic',description:'24 port managed network switch',qty:2,available:2,cost:100}],canPrepare:approved,prepareReason:approved?'':'Mohan must approve this PR before a Purchase Order can be created.'};
 const frappe={pages:{'bs-procurement':{}},route_options:{bsp_request:'MR-QC'},utils:{escape_html:s=>s},ui:{make_app_page:()=>({main:{append(){}}})},call:async ({method})=>{calls.push(method);return {message:method.endsWith('get_payment_orders')?{invoices:[],canReadRequests:true}:method.endsWith('get_request')?request:{requests:[{id:'MR-QC',items:[],orders:[]}]}}}};
 vm.runInNewContext(source,{frappe,document:{createElement:()=>root},console:{error:e=>errors.push(e)},Intl,crypto:require('crypto').webcrypto,Uint8Array});
 frappe.pages['bs-procurement'].on_page_load({});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(errors.length,0); assert(target.innerHTML.includes('24 port managed network switch'));
 assert(target.innerHTML.includes('Create Purchase Order'));
 assert(!calls.some(x=>x.endsWith('get_requests')));
 assert.equal(target.innerHTML.includes('disabled title="Mohan'),!approved);
 console.log('PASS direct PR load, description, and PO visibility: '+request.approval);
}
(async()=>{await test(false);await test(true)})().catch(e=>{console.error(e);process.exit(1)});
