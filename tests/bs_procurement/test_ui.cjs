/* Executes the actual page in a DOM with controlled server responses. No ERP writes. */
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm");
const {parseHTML}=require("./ui/node_modules/linkedom");
const {document,Event}=parseHTML("<html><body><main></main></body></html>");
const calls=[],messages=[],checks=[];
const clone=x=>JSON.parse(JSON.stringify(x));
const tick=()=>new Promise(resolve=>setTimeout(resolve,5));
const check=(name,value)=>{assert.ok(value,name);checks.push(name);console.log("PASS",name);};
const summary={id:"PR-OLD",company:"QC Company",project:"",person:"buyer@example.com",
  currency:"AED",approval:"Approved",purchasing:"Partially ordered",items:[{qty:4,cost:100}],orders:[],
  approver:{name:"Mohan Babu",user:"mohan@bitssecureit.com"}};
let po={id:"PO-OLD",request:"PR-OLD",company:"QC Company",supplier:"Supplier A",currency:"AED",
  companyCurrency:"AED",conversionRate:1,status:"Draft",erpStatus:"Draft",modified:"v1",docstatus:0,
  editable:true,canApprove:false,canCancel:true,approver:summary.approver,group:"Hardware",delivery:"2026-10-30",terms:"30 days",
  net:180,grand:180,taxes:0,na:true,explanation:"Single source",selectionReason:"",selectedQuote:null,
  history:[],lineReasons:{},quotes:[{supplier:"Supplier A",file:"",rates:{ROW:90}},
  {supplier:"Supplier B",file:"",rates:{ROW:95}},{supplier:"Supplier C",file:"",rates:{ROW:100}}],
  items:[{sourceId:"ROW",item_code:"QC-ITEM",description:"QC scope",qty:2,rate:90,cost:100,
  uom:"Nos",conversionFactor:1,uoms:["Nos","Box"],uomFactors:{Nos:1,Box:2}}]};
let failSave=null,lastDialog=null,uploads=[],saved=null,manual=null;
const paymentOrder={id:"PI-QC",supplier:"Supplier A",company:"QC Company",bill:"BILL-QC",
  date:"2026-10-20",due:"2026-11-20",approval:"Pending Approval",status:"Draft",docstatus:0,
  currency:"AED",outstandingCurrency:"AED",total:90,net:90,taxes:0,outstanding:null,
  orders:["PO-OLD"],requests:["PR-OLD"],items:[],receipts:{records:[],restricted:false},
  payments:{records:[],restricted:false},actions:[],canPay:false,approver:summary.approver};
const detail=()=>manual?clone(manual):({...clone(summary),history:[],actions:[],canPrepare:true,orders:[clone(po)],
  items:[{...po.items[0],qty:4,cost:100,available:2,reserved:2,ordered:0}]});
const frappe={
  pages:{"bs-procurement":{}},route_options:{},defaults:{get_user_default:()=>"QC Company"},
  datetime:{get_today:()=>"2026-10-20",add_days:()=>"2026-10-27"},
  utils:{escape_html:s=>s.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;")},
  ui:{make_app_page:()=>({main:document.querySelector("main")}),
    Dialog:class {constructor(o){this.options=o;lastDialog=this;}show(){}hide(){this.onhide?.();}},
    FileUploader:class {constructor(o){uploads.push(o);}}},
  msgprint:s=>messages.push(s),confirm:(_s,yes)=>yes(),show_alert:()=>{},set_route:()=>{},
  call:async({method,args})=>{
    calls.push({method,args});let data;
    if(method.endsWith("get_payment_orders"))data={invoices:[clone(paymentOrder)],has_more:false,user:"buyer@example.com",canReadRequests:true,canCreate:true};
    else if(method.endsWith("get_payment_order"))data=clone(paymentOrder);
    else if(method.endsWith("get_requests"))data={requests:[clone(summary)],has_more:true,user:"buyer@example.com",canCreate:true};
    else if(method.endsWith("get_orders"))data={orders:[clone(po)],has_more:!args.start};
    else if(method.endsWith("get_request"))data=detail();
    else if(method.endsWith("create_request")){
      const value=JSON.parse(args.payload);
      manual={...clone(summary),id:"PR-UTILITY",modified:"pr-v1",approval:"Draft",purchasing:"Not started",
        manual:true,canEditSupporting:true,canPrepare:false,orders:[],history:[],actions:["Send for Approval"],
        supporting:{...value.supporting,exception:false,explanation:"",invoices:[],
          quotes:[0,1,2].map(()=>({supplier:"",file:"",filename:"",url:""}))}};
      data=clone(manual);
    } else if(method.endsWith("save_request_evidence")){
      manual.supporting=JSON.parse(args.payload);manual.modified="pr-saved";data=clone(manual);
    } else if(method.endsWith("request_action")){
      assert.equal(args.modified,"pr-saved");manual.approval="Pending Approval";manual.canEditSupporting=false;
      manual.actions=[];manual.history=[{action:"Pending Approval",actor:"buyer@example.com",snapshot:{request_evidence:clone(manual.supporting)}}];
      data=clone(manual);
    }
    else if(method.endsWith("save_order")){
      if(failSave)throw failSave;
      saved=JSON.parse(args.payload);po={...po,...saved,lineReasons:saved.comparison.line_reasons};data=clone(po);
    } else throw Error("Unexpected call "+method);
    return {message:data};
  }
};
const context=vm.createContext({document,frappe,console:{error:()=>{}},Intl,crypto:require("node:crypto").webcrypto,
  Uint8Array,setTimeout,clearTimeout});
vm.runInContext(fs.readFileSync("bsgroup/bs_group/page/bs_procurement/bs_procurement.js","utf8"),context);
const wrapper={};
const find=s=>{const el=document.querySelector(s);assert.ok(el,"Element exists: "+s);return el;};
async function click(s){find(s).dispatchEvent(new Event("click",{bubbles:true}));await tick();}
async function input(s,value){const el=find(s);if(el.tagName==="SELECT"){
  for(const option of el.querySelectorAll("option"))option.selected=option.textContent===value;
}else el.value=value;el.dispatchEvent(new Event("input",{bubbles:true}));await tick();}
(async()=>{
  frappe.pages["bs-procurement"].on_page_load(wrapper);await tick();
  check("PR list loads real API summaries",document.body.textContent.includes("PR-OLD"));
  check("Status rail is inside a PR only",!document.querySelector(".bsp-rail"));
  await click('[data-action="orders"]');
  check("PO list queries its own paged endpoint",calls.some(c=>c.method.endsWith("get_orders")));
  await click('[data-action="more-orders"]');
  check("PO pagination uses loaded order count",calls.some(c=>c.method.endsWith("get_orders")&&c.args.start===1));
  await input("[data-search]","PO-OLD");await new Promise(r=>setTimeout(r,330));
  check("PO search reaches server for older records",calls.some(c=>c.method.endsWith("get_orders")&&c.args.search==="PO-OLD"));
  await click('[data-action="open-po"]');
  check("PO opens by fetching its source PR independently",calls.some(c=>c.method.endsWith("get_request")&&c.args.name==="PR-OLD"));
  check("PR and PO contain no invoice/payment detail panels",!document.body.textContent.includes("Matched receipts")&&!document.body.textContent.includes("Invoice allocation"));
  check("Approval action absent for another initiator",!document.querySelector('[data-value="Approve"]'));
  check("PO shows Mohan as designated approver",document.body.textContent.includes("Mohan Babu")&&document.body.textContent.includes("mohan@bitssecureit.com"));
  await input('[data-line-reason="ROW"]',"Freight applies to this specific purchase line.");
  await input('[data-key="uom"]',"Box");
  check("UOM change updates visible comparison budget",find('[data-comp-budget="0"]').textContent==="200.00");
  await click('[data-action="currency"]');
  lastDialog.options.primary_action({currency:"USD",rate:4});await tick();
  check("Exchange rate updates equivalent budget",find('[data-comp-budget="0"]').textContent==="50.00");
  await click('[data-action="save-po"]');
  check("Save carries line justification and purchasing basis",saved.currency==="USD"&&saved.conversionRate===4&&saved.items[0].uom==="Box"&&saved.comparison.line_reasons.ROW.includes("Freight"));
  await click('[data-action="upload"]');
  check("Quotation upload remains private and attached to PO",uploads[0].docname==="PO-OLD"&&!uploads[0].allow_toggle_private&&!uploads[0].allow_web_link);
  failSave={responseJSON:{_server_messages:'["Useful validation message"]'}};
  await click('[data-action="save-po"]');
  check("Server validation does not cause duplicate generic popup",messages.length===0);
  failSave=new Error("Connection lost");
  await click('[data-action="save-po"]');
  check("Transport error still gives user feedback",messages.length===1&&messages[0].includes("Connection lost"));
  failSave=null;
  await click('[data-action="back-pr"]');
  check("Each PR displays its own process rail",!!document.querySelector(".bsp-rail"));
  check("PR shows Mohan as designated approver",document.body.textContent.includes("Mohan Babu")&&document.body.textContent.includes("mohan@bitssecureit.com"));
  await click('[data-action="list"]');
  await click('[data-action="new-pr"]');
  check("Manual PR cannot choose arbitrary quotation or DCS budget",!lastDialog.options.fields.some(f=>["quotation","dcs"].includes(f.fieldname)));
  check("Manual PR offers utility/direct invoice type",lastDialog.options.fields.some(f=>f.fieldname==="request_type"&&f.options.includes("Utility bill")));
  check("Service PR does not require a warehouse in the dialog",!lastDialog.options.fields.find(f=>f.fieldname==="warehouse").reqd);
  lastDialog.options.primary_action({request_type:"Utility bill / direct invoice",company:"QC Company",title:"Electricity bill",items:[]});await tick();
  check("Utility PR displays its own invoice and quotation evidence section",document.body.textContent.includes("Invoice copies (required)")&&!!document.querySelector('[data-pr-field="exception"]'));
  await click('[data-action="pr-upload-invoice"]');
  const invoiceUpload=uploads.at(-1);
  check("Invoice uploader attaches private copies to the standard Material Request",
    invoiceUpload.doctype==="Material Request"&&invoiceUpload.docname==="PR-UTILITY"&&invoiceUpload.allow_multiple&&!invoiceUpload.allow_toggle_private&&!invoiceUpload.allow_web_link);
  invoiceUpload.on_success({name:"FILE-INVOICE",file_name:"Utility-October.pdf",file_url:"/private/files/Utility-October.pdf"});await tick();
  const exception=find('[data-pr-field="exception"]');exception.checked=true;exception.dispatchEvent(new Event("input",{bubbles:true}));await tick();
  await input('[data-pr-field="explanation"]',"Regulated electricity provider; three quotations are not applicable.");
  await click('[data-action="save-pr-supporting"]');
  check("Saving PR evidence retains invoice, exception and notes",
    manual.supporting.exception&&manual.supporting.explanation.includes("Regulated")&&manual.supporting.invoices[0].file==="FILE-INVOICE");
  await click('[data-action="pr-action"]');
  check("Sending PR saves current evidence before approval request",
    calls.at(-2).method.endsWith("save_request_evidence")&&calls.at(-1).method.endsWith("request_action"));
  check("Pending PR shows invoice links and locks exception fields",
    !!document.querySelector('a[href="/private/files/Utility-October.pdf"]')&&find('[data-pr-field="exception"]').hasAttribute("disabled")
    &&!document.querySelector('[data-action="pr-upload-invoice"]'));
  check("Approval history exposes supporting evidence and explanation",
    document.body.textContent.includes("Invoice copy")&&document.body.textContent.includes("Regulated electricity provider"));
  await click('[data-action="services"]');
  check("Payment Order remains third module section",document.body.textContent.includes("Supplier / vendor invoices, approvals and payments."));
  await click('[data-action="settlement"]');
  check("Payment Order displays Mohan and his approver account",
    document.body.textContent.includes("Mohan Babu")&&document.body.textContent.includes("mohan@bitssecureit.com"));
  check("Pending Payment Order hides payment and other-user approval actions",
    !document.querySelector('[data-action="record-payment"]')&&!document.querySelector('[data-value="Approve"]'));
  paymentOrder.docstatus=1;paymentOrder.approval="Approved";paymentOrder.canPay=true;
  paymentOrder.approvedBy="mohan@bitssecureit.com";paymentOrder.approvedOn="2026-10-20 19:00:00";
  await click('[data-action="settlement-list"]');await click('[data-action="settlement"]');
  check("Approved Payment Order shows approval evidence and payment action",
    document.body.textContent.includes("2026-10-20 19:00:00")&&!!document.querySelector('[data-action="record-payment"]'));
  console.log(JSON.stringify({passed:checks.length,tests:checks},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
