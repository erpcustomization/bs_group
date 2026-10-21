/* Sample workflow only. PDF rendering uses a read-only server call; no business records or persistent preview storage. */
/* Pure allocation rules shared by the preview and regression checks. */
var BSProcurementRules = {
  reserved(r, sourceId, excludeId) {
    return r.orders.filter(p=>p.id!==excludeId && p.status!=="Cancelled")
      .flatMap(p=>p.items).filter(x=>x.sourceId===sourceId).reduce((s,x)=>s+Number(x.qty||0),0);
  },
  approvedQty(r, sourceId) {
    return r.orders.filter(p=>p.status==="Approved").flatMap(p=>p.items)
      .filter(x=>x.sourceId===sourceId).reduce((s,x)=>s+Number(x.qty||0),0);
  },
  remaining(r, sourceId, excludeId) {
    const line=r.items.find(x=>x.sourceId===sourceId);
    return line ? Math.max(0,line.qty-this.reserved(r,sourceId,excludeId)) : 0;
  },
  allocationErrors(r,p) {
    const errors=[],seen=new Set();
    for(const x of p.items) {
      const source=r.items.find(y=>y.sourceId===x.sourceId);
      if(!source||seen.has(x.sourceId)){errors.push("Each PO line must reference a different approved PR line.");continue;}
      seen.add(x.sourceId);
      if(!Number.isFinite(+x.qty)||x.qty<=0)errors.push("Quantity for "+source.description+" must be a number greater than zero.");
      else if(x.qty>this.remaining(r,x.sourceId,p.id)+1e-9)errors.push("Quantity for "+source.description+" exceeds the unallocated PR quantity. Available: "+this.remaining(r,x.sourceId,p.id)+".");
      if(x.cost!==source.cost||x.uom!==source.uom||x.description!==source.description)errors.push("Item description, DCS cost and UOM must match the approved PR.");
    }
    return errors;
  },
  status(r) {
    if(r.status!=="On Process")return "Not started";
    const ordered=r.items.map(x=>this.approvedQty(r,x.sourceId));
    if(r.items.length&&r.items.every((x,i)=>ordered[i]>=x.qty-1e-9))return "Fully ordered";
    if(ordered.some(x=>x>0))return "Partially ordered";
    if(r.orders.some(p=>p.status==="Pending Approval"))return "Awaiting PO approval";
    if(r.orders.some(p=>p.status!=="Cancelled"))return "Sourcing / PO preparation";
    return "Ready for procurement";
  },
  approval(r){return r.status==="On Process"?"Approved":r.status==="New"||r.status==="Not sent"?"Not requested":r.status;},
  validatePO(r,p) {
    const errors=this.allocationErrors(r,p);
    if(r.status!=="On Process")errors.push("PR approval is required before submitting or approving a PO.");
    for(const [key,label] of Object.entries({group:"Purchase material group",supplier:"Supplier",contact:"Contact person",email:"Email",phone:"Phone",address:"Address",terms:"Payment terms"}))if(!p[key].trim())errors.push(label+" is required.");
    if(p.email&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(p.email))errors.push("Enter a valid email address.");
    if(p.terms==="Custom"&&!p.customTerms.trim())errors.push("Explain the custom payment terms.");
    if(!p.items.length)errors.push("At least one item is required.");
    if(p.items.some(x=>!x.description.trim()||!x.uom.trim()||!Number.isFinite(+x.qty)||+x.qty<=0||!Number.isFinite(+x.rate)||+x.rate<=0))errors.push("Each line needs a description, UOM, positive quantity and positive price.");
    if(p.na&&!p.explanation.trim())errors.push("Explain why three supplier quotations are not available.");
    if(!p.na&&(p.quotes.length!==3||p.quotes.some(q=>!q.file||!q.supplier.trim()||p.items.some(x=>!Number.isFinite(+q.rates[x.sourceId])||+q.rates[x.sourceId]<=0))))errors.push("Provide three supplier quotations with supplier, amount and sample attachment, or mark N/A and explain.");
    if(!p.na&&new Set(p.quotes.map(q=>q.supplier.trim().toLowerCase())).size!==3)errors.push("Use three different suppliers for the quotation comparison.");
    if(!p.na&&p.selectedQuote===null)errors.push("Choose a supplier from the comparison.");
    const chosen=p.selectedQuote===null?null:p.quotes[p.selectedQuote];
    if(p.selectedQuote!==null&&(!Number.isInteger(p.selectedQuote)||!chosen||p.supplier.trim()!==chosen.supplier.trim()))errors.push("The selected supplier must match the chosen quotation.");
    const overDCS=p.items.some(x=>x.rate>x.cost+1e-9),negotiated=chosen&&p.items.some(x=>Math.abs(x.qty*(x.rate-Number(chosen.rates[x.sourceId]||0)))>.005);
    if((overDCS||negotiated)&&!p.selectionReason.trim())errors.push("Explain any line above DCS cost or any line-price difference from the chosen quotation.");
    return errors;
  },
  quotationBasis(p){
    if(p.na)return "Quotation exception";
    const complete=(p.quotes||[]).filter(q=>q.supplier?.trim()&&q.file&&p.items.length&&p.items.every(x=>Number.isFinite(+q.rates?.[x.sourceId])&&+q.rates[x.sourceId]>0)).length;
    if(complete===3)return "Three quotations";
    const started=(p.quotes||[]).some(q=>q.supplier?.trim()||q.file||Object.values(q.rates||{}).some(x=>Number(x)>0));
    return started?"Quotations incomplete ("+complete+"/3)":"Not provided";
  },
  orderLines(p){return p.items.length?p.items.map(x=>x.sourceId+": "+x.qty).join(", ")+(p.status==="Cancelled"?" (released)":""):"No line items";},
  orderCounts(r){const active=r.orders.filter(p=>p.status!=="Cancelled");return {active:active.length,cancelled:r.orders.length-active.length,approved:active.filter(p=>p.status==="Approved").length};},
  orderSummary(r){const c=this.orderCounts(r);return c.active+" active · "+c.cancelled+" cancelled";},
  snapshot(p){
    const fields=["group","supplier","contact","trn","email","phone","address","terms","customTerms","delivery","na","explanation","selectedQuote","selectionReason","items","quotes"];
    return structuredClone(Object.fromEntries(fields.map(key=>[key,p[key]])));
  },
  submissionValues(s){
    const values={};
    for(const [key,label] of Object.entries({group:"Material group",supplier:"Supplier",contact:"Contact",trn:"TRN / VAT",email:"Email",phone:"Phone",address:"Address",terms:"Payment terms",customTerms:"Custom terms",delivery:"Delivery date",na:"Quotation exception",explanation:"Exception explanation",selectionReason:"Selection / negotiation notes"}))values[label]=s[key]??"";
    values["Chosen quotation"]=s.selectedQuote===null?"None":"Quotation "+(s.selectedQuote+1);
    for(const x of s.items||[])for(const [key,label] of Object.entries({description:"item",qty:"quantity",uom:"UOM",rate:"unit price",cost:"DCS unit cost"}))values[x.sourceId+" "+label]=x[key];
    (s.quotes||[]).forEach((q,i)=>{values["Quote "+(i+1)+" supplier"]=q.supplier;values["Quote "+(i+1)+" attachment"]=q.file;for(const [line,rate]of Object.entries(q.rates||{}))values["Quote "+(i+1)+" "+line+" rate"]=rate;});
    return values;
  },
  recordSubmission(p,at,actor){
    p.submissions??=[];
    const snapshot=this.snapshot(p),previous=p.submissions.at(-1),before=previous?this.submissionValues(previous.snapshot):{},after=this.submissionValues(snapshot);
    const changes=previous?[...new Set([...Object.keys(before),...Object.keys(after)])].filter(key=>before[key]!==after[key]).map(field=>({field,before:before[field]??null,after:after[field]??null})):[];
    const entry={version:p.submissions.length+1,at,actor,snapshot,changes,decision:{status:"Pending Approval",at:"",actor:"",reason:""}};
    p.submissions.push(entry);return entry;
  },
  recordDecision(p,status,at,actor,reason=""){const entry=p.submissions?.at(-1);if(entry)entry.decision={status,at,actor,reason};},
  net(p){return p.items.reduce((s,x)=>s+Number(x.qty||0)*Number(x.rate||0),0);},
  quoteTotal(p,q){return p.items.reduce((s,x)=>s+x.qty*Number(q.rates[x.sourceId]||0),0);},
  scopeBudget(p){return p.items.reduce((s,x)=>s+Number(x.qty||0)*x.cost,0);}
};
if(typeof module!=="undefined"&&module.exports)module.exports=BSProcurementRules;

if(typeof frappe!=="undefined")frappe.pages["bs-procurement"].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: "BS Procurement", single_column: true});
  const root = document.createElement("div");
  root.className = "bsp";
  root.dataset.build="20261020-qc4";
  page.main.append(root);
  const esc = value => frappe.utils.escape_html(String(value ?? ""));
  const money = value => new Intl.NumberFormat("en-AE", {minimumFractionDigits:2, maximumFractionDigits:2}).format(Number(value) || 0);
  const stamp = () => new Date().toLocaleString("en-GB", {day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"});
  const sampleItems = [
    [{description:"TEST Switch 24-port PoE (dummy)",qty:2,uom:"Nos",cost:1000},{description:"TEST CAT6 305m cable box (dummy)",qty:3,uom:"Box",cost:400}],
    [{description:"TEST Access control equipment (dummy)",qty:10,uom:"Nos",cost:3500},{description:"TEST Installation services (dummy)",qty:1,uom:"Job",cost:6000}],
    [{description:"TEST Microsoft 365 licences (dummy)",qty:20,uom:"Nos",cost:200},{description:"TEST Migration services (dummy)",qty:1,uom:"Job",cost:1000}]
  ];
  function seed() {
    return ["Paul","Gopinath Sundaram","Raj"].map((person,i)=>({
      id:"DEMO-PRQ-2026-000"+(i+1),person,
      project:["QA TEST 2 – DCS approval + Purchase Request flow","ZZ TEST – Access control upgrade, Silicon Oasis office","ZZ TEST – Microsoft 365 licences and migration"][i],
      customer:"ZZ-TEST-QA-DoNotUse",quotation:"SAL-QTN-2026-"+(1243+i).toString().padStart(5,"0"),
      customerPO:["ZZ-PO-7781","ZZ-PO-7790","ZZ-PO-7802"][i],dcs:"DCS-ZZTESTQADoNotUse-0"+(13+i),
      revision:"R2",items:structuredClone(sampleItems[i]).map((x,n)=>({...x,sourceId:"L"+(n+1)})),status:"New",requested:"",approved:"",reason:"",orders:[]
    }));
  }
  let requests=seed(), role="Procurement", view="list", active=0, tab="Requisition", query="", events=[];
  let quotationWon=false, quotationPO="", poIndex=0, picks={};
  const rules=BSProcurementRules;
  let orderQuery="";
  const currentPO=()=>current().orders[poIndex];
  const prStatus=r=>rules.status(r);
  const approvalStatus=r=>rules.approval(r);
  const pendingEvents=()=>["detail","po","pdf"].includes(view)?events.filter(x=>x.pr===current().id):events;
  function creationEvents(){return requests.filter(r=>r.status!=="Not sent").map(r=>({at:stamp(),actor:"Sales ("+r.person+")",pr:r.id,text:"Sent "+r.quotation+" with customer PO and deal cost sheet. Created "+r.id+"."}));}
  events=creationEvents();
  const current = () => requests[active];
  const budget = r => r.items.reduce((s,x)=>s+x.qty*x.cost,0);
  const total = p => p.items.reduce((s,x)=>s+Number(x.qty||0)*Number(x.rate||0),0);
  const log = text => events.unshift({at:stamp(),actor:role+" (preview)",pr:current().id,text});
  const badge = status => `<span class="bsp-badge ${status==="Approved"||status==="On Process"?"good":status==="Rejected"?"bad":""}">${esc(status)}</span>`;
  const button=(label,action,attrs="",primary=false)=>`<button type="button" class="bsp-button ${primary?"primary":""}" data-action="${action}" ${attrs}>${label}</button>`;
  function reset(replay=false) {
    requests=seed();events=[];active=0;role=replay?"Sales":"Procurement";view=replay?"quotation":"list";tab="Requisition";query="";quotationWon=false;quotationPO="";poIndex=0;picks={};
    if(replay) requests[0].status="Not sent";
    orderQuery="";events=creationEvents();
    log(replay?"Quotation preview started.":"Sample requisitions reset.");render();
  }
  function actions(r,index) {
    const attr=`data-index="${index}"`;
    if(view!=="detail")return button("Open PR","detail",attr);
    if(r.status==="Not sent")return '<span class="muted">Not handed over</span>';
    if(["New","Rejected"].includes(r.status)&&role==="Procurement")return button(r.status==="Rejected"?"Request approval again":"Request approval","request",attr);
    if(r.status==="Pending Approval"&&role==="Manager")return button("Approve PR","approve",attr,true)+" "+button("Reject PR","reject",attr);
    return '<span class="muted">'+(r.status==="Pending Approval"?"Awaiting manager":r.status==="On Process"?"PR approved for procurement":"Approval not requested")+"</span>";
  }
  function prProgress(r) {
    const orders=r.orders.filter(x=>x.status!=="Cancelled"),approved=orders.filter(x=>x.status==="Approved").length;
    const stages=[
      ["Quotation won",r.status==="Not sent"?"Not handed over":"Customer PO uploaded",r.status!=="Not sent"],
      ["Approval requested",r.requested?"Requested":"Not requested yet",!!r.requested],
      ["PR approval",approvalStatus(r),r.status==="On Process"],
      ["Purchase orders",rules.orderSummary(r),orders.length>0],
      ["PO approval",approved+" of "+orders.length+" approved",orders.length>0&&approved===orders.length],
      ["PO PDFs ready",approved+" ready for download",orders.length>0&&approved===orders.length]
    ];
    return '<div class="bsp-rail" aria-label="Process stages for '+esc(r.id)+'">'+stages.map((s,i)=>`<div class="bsp-stage ${s[2]?"done":""}"><strong>${String(i+1).padStart(2,"0")} ${s[2]?"✓":""} ${esc(s[0])}</strong><small>${esc(s[1])}</small></div>`).join("")+"</div>";
  }
  function activityItems(){return pendingEvents().map(x=>`<li><time>${esc(x.at)}</time><strong>${esc(x.actor)}</strong><span>${esc(x.text)}</span></li>`).join("")||"<li>No preview activity yet.</li>";}
  function renderActivity(){
    const list=root.querySelector(".bsp-activity ul"),count=root.querySelector('[data-action="activity"] b');
    if(list)list.innerHTML=activityItems();
    if(count)count.textContent=events.length;
  }
  function render() {
    root.innerHTML = `<aside class="bsp-side"><div class="bsp-brand"><span>B</span><div>BS Procurement<small>BS Group</small></div></div><nav aria-label="Procurement navigation">${button("⌕ &nbsp; Search","search")}${button("Notification <b>"+events.length+"</b>","activity")}${button("Purchase Requisition <b>"+requests.filter(r=>r.status!=="Not sent").length+"</b>","list",view==="list"||view==="detail"?'aria-current="page"':"")}${button("Purchase Order <b>"+requests.reduce((n,r)=>n+r.orders.filter(p=>p.status!=="Cancelled").length,0)+"</b>","orders",view==="orders"||view==="po"?'aria-current="page"':"")}${button("Service Entry Sheet","services",view==="services"?'aria-current="page"':"")}</nav><div class="bsp-profile">Screen preview<small>Sample roles · no ERP permissions changed</small></div></aside><div class="bsp-main"><header class="bsp-top"><span>BS Procurement / <strong>${view==="po"||view==="orders"||view==="pdf"?"Purchase Order":view==="services"?"Service Entry Sheet":view==="quotation"?"Quotation":"Purchase Requisition"}</strong></span><div class="bsp-roles"><span>Preview as</span>${["Sales","Procurement","Manager"].map(x=>button(x,"role",`data-role="${x}" aria-pressed="${role===x}"`)).join("")}</div></header><section class="bsp-body"><div class="bsp-preview"><strong>Interactive screen preview</strong> · Sample records only. Nothing here creates or changes ERP transactions. Refreshing resets this preview.<div>${button("Start from quotation (as Paul)","replay")}${button("Reset sample requisitions","reset")}</div></div><div class="bsp-view"></div><section class="bsp-activity" aria-label="Activity"><h3>Activity <small>Preview events</small></h3><ul>${activityItems()}</ul></section></section></div>`;
    const target=root.querySelector(".bsp-view");
    if(view==="list")target.innerHTML=list();
    if(view==="detail")target.innerHTML=detail();
    if(view==="orders")target.innerHTML=orders();
    if(view==="po")target.innerHTML=poForm();
    if(view==="quotation")target.innerHTML=quotation();
    if(view==="pdf")target.innerHTML=pdf();
    if(view==="services")target.innerHTML='<h2>Service Entry Sheet</h2><div class="bsp-empty">Service acceptance will follow in a later phase.</div>';
    if(view==="list") {const input=root.querySelector('[data-search]');input.value=query;filterRows();}
    if(view==="orders"){root.querySelector("[data-order-search]").value=orderQuery;filterOrderRows();}
  }
  function list() {
    const visible=requests.filter(r=>r.status!=="Not sent");
    return `<div class="bsp-heading"><div><h2>Purchase Requisition <small>${visible.length} records</small></h2><p class="muted">Review each sales handover, then request manager approval.</p></div><input data-search type="search" aria-label="Search requisitions" placeholder="Search requisitions…"></div><div class="bsp-tablewrap"><table><thead><tr>${["ID","Sales person","Project","PR status","PR approval / Open","Customer","Quotation","Customer PO","Budget (AED)","Requested"].map(x=>"<th>"+x+"</th>").join("")}</tr></thead><tbody>${requests.map((r,i)=>r.status==="Not sent"?"":`<tr data-search-text="${esc([...Object.values(r).filter(x=>typeof x==="string"),prStatus(r),approvalStatus(r)].join(" ").toLowerCase())}"><td>${button(esc(r.id),"detail",`data-index="${i}"`)}</td><td>${esc(r.person)}</td><td class="project">${esc(r.project)}</td><td>${badge(prStatus(r))}</td><td class="actions">${badge(approvalStatus(r))} ${actions(r,i)}</td><td>${esc(r.customer)}</td><td>${esc(r.quotation)}</td><td>${esc(r.customerPO)}</td><td class="amount">${money(budget(r))}</td><td>${esc(r.requested||"Not requested")}</td></tr>`).join("")}</tbody></table><p class="bsp-no-results" hidden>No requisitions match your search.</p></div><p class="muted">Open a requisition to review its quotation, customer PO and deal cost sheet. Each requisition is approved separately.</p>`;
  }
  function filterRows() {
    let count=0;root.querySelectorAll("[data-search-text]").forEach(row=>{row.hidden=!row.dataset.searchText.includes(query.toLowerCase());if(!row.hidden)count++;});
    root.querySelector(".bsp-no-results").hidden=!!count;
  }
  const facts=items=>'<div class="bsp-facts">'+items.map(([k,v])=>`<div><small>${esc(k)}</small><strong>${esc(v||"—")}</strong></div>`).join("")+"</div>";
  function itemsTable(items,purchasing=false) {
    return '<div class="bsp-tablewrap"><table><thead><tr><th>Description</th><th>Qty</th><th>UOM</th><th>'+ (purchasing?"Unit price":"DCS cost rate")+'</th><th>Amount (AED)</th></tr></thead><tbody>'+items.map(x=>`<tr><td>${purchasing?esc(x.sourceId)+" · ":""}${esc(x.description)}</td><td>${x.qty}</td><td>${esc(x.uom)}</td><td>${money(purchasing?x.rate:x.cost)}</td><td>${money(x.qty*(purchasing?x.rate:x.cost))}</td></tr>`).join("")+"</tbody></table></div>";
  }
  function allocationTable(r) {
    const canPrepare=r.status==="On Process"&&role==="Procurement";
    return `<section class="bsp-card"><h3>PR line items and purchasing progress</h3><p class="muted">Select the lines for one supplier PO. Draft and pending POs reserve quantities; only approved POs count as ordered. Each new PO has its own three supplier quotations and DCS comparison.</p><div class="bsp-tablewrap"><table><thead><tr><th>Select</th><th>PR line / Description</th><th>PR qty</th><th>Approved PO qty</th><th>Reserved in other POs</th><th>Available</th><th>Qty for new PO</th><th>DCS unit cost</th></tr></thead><tbody>${r.items.map(x=>{
      const available=rules.remaining(r,x.sourceId), ordered=rules.approvedQty(r,x.sourceId);
      return `<tr><td><input type="checkbox" aria-label="Select ${x.sourceId}" data-pick="${x.sourceId}" ${picks[x.sourceId]!==undefined?"checked":""} ${!canPrepare||available<=0?"disabled":""}></td><td>${esc(x.sourceId)} · ${esc(x.description)}<small> ${esc(x.uom)}</small></td><td>${x.qty}</td><td>${ordered}</td><td>${rules.reserved(r,x.sourceId)-ordered}</td><td>${available}</td><td><input aria-label="PO quantity ${x.sourceId}" type="number" min="0.001" max="${available}" step="any" data-pick-qty="${x.sourceId}" value="${picks[x.sourceId]??available}" ${!canPrepare||available<=0?"disabled":""}></td><td>${money(x.cost)}</td></tr>`;
    }).join("")}</tbody></table></div>${canPrepare?button("Create PO from selected lines","create-po","",true):""}<p class="bsp-total">Full PR DCS budget <strong>AED ${money(budget(r))}</strong></p></section>`;
  }
  function linkedOrders(r) {
    return `<section class="bsp-card"><h3>Purchase orders for this PR · ${rules.orderSummary(r)}</h3>${r.orders.length?ordersTable([{r,i:active}]):'<p class="muted">No supplier POs yet. After PR approval, select the lines for the first supplier.</p>'}</section>`;
  }
  function ordersTable(entries,searchable=false) {
    return '<div class="bsp-tablewrap"><table><thead><tr><th>PO</th><th>PR</th><th>Supplier</th><th>PR lines</th><th>PO approval status</th><th>Quotation basis</th><th>Active DCS allocation</th><th>Active PO net</th><th>Variance</th></tr></thead><tbody>'+entries.map(({r,i})=>r.orders.map((p,n)=>`<tr ${searchable?'data-po-search-text="'+esc([p.id,r.id,p.supplier,p.status,p.na?"Quotation exception":""].join(" ").toLowerCase())+'"':""} class="${p.status==="Cancelled"?"bsp-cancelled":""}"><td>${button(esc(p.id),"open-po",`data-index="${i}" data-po-index="${n}"`)}</td><td>${esc(r.id)}</td><td>${esc(p.supplier||"Not selected")}</td><td>${esc(rules.orderLines(p))}</td><td>${badge(p.status)}</td><td>${p.na?badge("Quotation exception"):esc(rules.quotationBasis(p))}</td><td>${p.status==="Cancelled"?"—":money(rules.scopeBudget(p))}</td><td>${p.status==="Cancelled"?"—":poPriced(p)?money(total(p)):"Not priced"}</td><td>${p.status!=="Cancelled"&&poPriced(p)?money(total(p)-rules.scopeBudget(p)):"—"}</td></tr>`).join("")).join("")+"</tbody></table></div>";
  }
  function filterOrderRows(){let count=0;root.querySelectorAll("[data-po-search-text]").forEach(row=>{row.hidden=!row.dataset.poSearchText.includes(orderQuery.toLowerCase());if(!row.hidden)count++;});root.querySelector(".bsp-no-orders").hidden=!!count;}
  function detail() {
    const r=current();
    const statusCard=`<section class="bsp-card bsp-pr-status"><h3>PR status and approval</h3>${facts([["PR status",prStatus(r)],["PR approval status",approvalStatus(r)],["Approval requested by / on",r.requested],["Approved by / on",r.approved],["Last rejection reason",r.reason],["Purchase orders",rules.orderSummary(r)]])}<div class="bsp-pr-progress"><h4>Process progress</h4>${prProgress(r)}</div></section>`;
    let content="";
    if(tab==="Requisition") content=`<p class="bsp-callout">${r.status==="On Process"?"PR approved. Procurement can obtain three quotations, compare them with the DCS cost, and prepare separate POs for different suppliers.":r.status==="Pending Approval"?"Waiting for PR approval. Supplier PO preparation is locked.":r.status==="Rejected"?"PR rejected: "+esc(r.reason):"Review the handover documents, then request approval inside this PR."}</p><section class="bsp-card"><h3>Request</h3>${facts([["Sales person",r.person],["Project",r.project],["Customer",r.customer],["Quotation",r.quotation],["Customer PO",r.customerPO],["Deal Cost Sheet",r.dcs+" · "+r.revision]])}</section>${allocationTable(r)}${linkedOrders(r)}`;
    else content=`<section class="bsp-card"><div class="bsp-document-label">DEMONSTRATION DOCUMENT · NOT AN ORIGINAL FILE</div><h3>${esc(tab)}</h3>${facts([["Reference",tab==="Quotation"?r.quotation:tab==="Customer PO"?r.customerPO:r.dcs],["Customer",r.customer],["Project",r.project],["Revision",r.revision]])}${tab==="Quotation"?'<p class="bsp-callout">Cost reference for this handover. Customer selling prices and the original quotation are not loaded in this preview.</p>':""}${itemsTable(r.items)}<p class="muted">Illustrative document layout. Original ERP attachments are not loaded in this preview.</p></section>`;
    return `<div class="bsp-heading"><div><small>Sales person: ${esc(r.person)}</small><h2>${esc(r.id)} ${badge(prStatus(r))}</h2><p class="muted">${esc(r.project)}</p></div><div>${button("All requisitions","list")}${actions(r,active)}</div></div>${statusCard}<div class="bsp-tabs" role="tablist">${["Requisition","Quotation","Customer PO","Deal Cost Sheet"].map(t=>`<button role="tab" aria-selected="${t===tab}" data-action="tab" data-tab="${t}">${t}</button>`).join("")}</div>${content}`;
  }
  function orders() {
    return '<div class="bsp-heading"><h2>Purchase Order</h2><input data-order-search type="search" aria-label="Search purchase orders" placeholder="Search PO, PR, supplier or status…"></div>'+ordersTable(requests.map((r,i)=>({r,i})),true)+'<p class="bsp-no-orders muted" hidden>No purchase orders match your search.</p><p class="muted">Cancelled orders remain in history. Active amounts exclude cancelled orders.</p>';
  }
  function createPO(r) {
    const items=r.items.filter(x=>picks[x.sourceId]!==undefined).map(x=>({...x,qty:Number(picks[x.sourceId]),rate:0}));
    const p={id:r.id.replace("PRQ","PO-DXB")+"-"+String(r.orders.length+1).padStart(2,"0"),status:"Draft",group:"",supplier:"",contact:"",trn:"",email:"",phone:"",address:"",terms:"",customTerms:"",delivery:"",na:false,explanation:"",reason:"",approved:"",selectedQuote:null,selectionReason:"",submissions:[],items,
      quotes:[0,1,2].map(i=>({supplier:"",file:"",rates:Object.fromEntries(items.map(x=>[x.sourceId,0]))}))};
    const errors=rules.allocationErrors(r,p);
    if(!items.length)errors.push("Select at least one PR line.");
    if(errors.length){frappe.msgprint(errors.map(esc).join("<br>"));return false;}
    r.orders.push(p);poIndex=r.orders.length-1;picks={};return true;
  }
  const hasPrice=value=>Number.isFinite(+value)&&+value>0;
  const poPriced=p=>p.items.length>0&&p.items.every(x=>hasPrice(x.qty)&&hasPrice(x.rate));
  const quotePriced=(p,q)=>p.items.length>0&&p.items.every(x=>hasPrice(x.qty)&&hasPrice(q.rates[x.sourceId]));
  const quoteTotal=(p,q)=>p.items.reduce((s,x)=>s+x.qty*Number(q.rates[x.sourceId]||0),0);
  function comparison(p,editable) {
    return `<section class="bsp-card"><h3>Cost comparison · selected PO scope</h3><p class="muted">Compare the same PR lines and quantities across all three suppliers. All amounts are AED, excluding VAT. Positive variance means above DCS cost.</p><div class="bsp-tablewrap"><table><thead><tr><th>PR line / Item</th><th>Qty</th><th>DCS unit cost</th>${p.quotes.map((q,i)=>`<th data-quote-heading="${i}">${esc(q.supplier||"Supplier "+(i+1))} unit price</th>`).join("")}<th>Selected PO unit price</th><th>PO vs DCS</th></tr></thead><tbody>${p.items.map(x=>`<tr><td>${esc(x.sourceId)} · ${esc(x.description)}</td><td data-comparison-qty="${x.sourceId}">${x.qty}</td><td>${money(x.cost)}</td>${p.quotes.map((q,i)=>`<td><input aria-label="Quotation ${i+1} rate ${x.sourceId}" type="number" min="0.01" step="any" data-quote-rate="${i}" data-source="${x.sourceId}" value="${q.rates[x.sourceId]||""}" ${editable?"":"disabled"}></td>`).join("")}<td data-selected-rate="${x.sourceId}">${money(x.rate)}</td><td data-line-variance="${x.sourceId}">${hasPrice(x.rate)?money(x.qty*(x.rate-x.cost)):"—"}</td></tr>`).join("")}</tbody><tfoot><tr><th>Net total</th><td></td><td data-scope-budget>${money(rules.scopeBudget(p))}</td>${p.quotes.map((q,i)=>`<td data-quote-total="${i}">${quotePriced(p,q)?money(quoteTotal(p,q)):"Not priced"}</td>`).join("")}<td data-selected-total>${poPriced(p)?money(total(p)):"Not priced"}</td><td data-total-variance>${poPriced(p)?money(total(p)-rules.scopeBudget(p)):"—"}</td></tr><tr><th>Variance against DCS</th><td></td><td>—</td>${p.quotes.map((q,i)=>`<td data-quote-variance="${i}">${quotePriced(p,q)?money(quoteTotal(p,q)-rules.scopeBudget(p)):"—"}</td>`).join("")}<td colspan="2">Selected PO compared with its allocated DCS budget</td></tr></tfoot></table></div><label>Supplier selection / negotiation notes<textarea data-field="selectionReason" ${editable?"":"disabled"}>${esc(p.selectionReason)}</textarea></label></section>`;
  }
  function poForm() {
    const r=current(),p=currentPO(), editable=role==="Procurement"&&(p.status==="Draft"||p.status==="Rejected");
    const disabled=editable?"":"disabled";
    const field=(key,label,type="text")=>`<label>${label}<input data-field="${key}" type="${type}" value="${esc(p[key])}" ${disabled}></label>`;
    const select=(key,label,options)=>`<label>${label}<select data-field="${key}" ${disabled}><option value="">Select…</option>${options.map(x=>`<option ${p[key]===x?"selected":""}>${esc(x)}</option>`).join("")}</select></label>`;
    let controls=button("Back to PR","detail",`data-index="${active}"`)+button("All purchase orders","orders");
    if(editable) controls+=button("Cancel PO","cancel-po")+button("Send for Manager Approval","send-po","",true);
    if(role==="Manager"&&p.status==="Pending Approval")controls+=button("Reject","reject-po")+button("Approve","approve-po","",true);
    if(p.status==="Approved")controls+=button("View PDF preview","pdf","",true);
    return `<div class="bsp-heading"><div><small>Against ${esc(r.id)}</small><h2>${esc(p.id)} ${badge(p.status)}</h2></div><div>${controls}</div></div>${p.na?'<p class="bsp-callout bsp-exception"><strong>Quotation exception — manager review</strong><br>'+esc(p.explanation||"Explanation required before submission.")+"</p>":""}${p.status==="Rejected"?'<p class="bsp-callout">Rejected: '+esc(p.reason)+" Procurement may revise and resubmit.</p>":""}${p.status==="Pending Approval"?'<p class="bsp-callout">Waiting for manager approval. The form is locked.</p>':""}<div class="bsp-errors" role="alert" hidden></div><section class="bsp-card"><h3>Order</h3><div class="bsp-grid"><label>Company<strong>Bits Secure IT Infrastructure LLC – Dubai</strong></label>${select("group","Purchase material group *",["Hardware","Software","Professional Services"])}<label>Currency<strong>AED</strong></label></div></section><section class="bsp-card"><h3>Supplier</h3><div class="bsp-grid">${field("supplier","Selected supplier name *")}${field("contact","Contact person *")}${field("trn","TRN / VAT no.")}${field("email","Email *","email")}${field("phone","Phone *","tel")}${field("address","Address *")}</div></section><section class="bsp-card"><h3>Line items *</h3><div class="bsp-tablewrap"><table><thead><tr><th>Description</th><th>Qty</th><th>UOM</th><th>Unit price (AED)</th><th>Amount</th><th>DCS cost</th><th></th></tr></thead><tbody>${p.items.map((x,i)=>`<tr><td><input aria-label="Description ${i+1}" data-line="${i}" data-key="description" value="${esc(x.description)}" disabled></td><td><input aria-label="Quantity ${i+1}" type="number" min="0.001" step="any" data-line="${i}" data-key="qty" value="${x.qty}" ${disabled}></td><td><input aria-label="UOM ${i+1}" data-line="${i}" data-key="uom" value="${esc(x.uom)}" disabled></td><td><input aria-label="Unit price ${i+1}" type="number" min="0.01" step="any" data-line="${i}" data-key="rate" value="${x.rate||""}" ${disabled}></td><td data-amount="${i}">${money(x.qty*x.rate)}</td><td>${x.cost===null?"New line":money(x.cost)} <span class="bsp-over" data-over="${i}">${x.cost===null||x.rate>x.cost?"▲":""}</span></td><td>${editable?button("Remove","remove-line",`data-line-index="${i}" aria-label="Remove line ${i+1}"`):""}</td></tr>`).join("")}</tbody></table></div><div class="bsp-totals"></div><p class="muted">▲ marks a unit price above the DCS cost. VAT is illustrated at 5% for this preview.</p></section><section class="bsp-card"><h3>Payment terms *</h3><div class="bsp-grid">${select("terms","Terms *",["100% advance","50% advance, 50% on delivery","30 days from invoice","45 days from invoice","60 days from invoice","PDC 30 days","Custom"])}${field("delivery","Expected delivery","date")}<div class="bsp-custom-terms" ${p.terms!=="Custom"?"hidden":""}>${field("customTerms","Custom payment terms *")}</div></div></section><section class="bsp-card"><h3>Supplier quotations · 3 required <small>(${p.quotes.filter(q=>q.file).length}/3)</small></h3><p class="muted">Use sample attachment buttons to test this screen. No files are uploaded.</p><div class="bsp-grid">${p.quotes.map((q,i)=>`<div class="bsp-quote"><h4>Quotation ${i+1} ${badge(q.file?"Attached":"Missing")}</h4><label>Supplier<input aria-label="Quotation ${i+1} supplier" data-quote="${i}" data-key="supplier" value="${esc(q.supplier)}" ${disabled}></label><label>Net total for selected PO lines<strong data-card-quote-total="${i}">${quotePriced(p,q)?"AED "+money(quoteTotal(p,q)):"Not priced"}</strong></label><p>${esc(q.file||"No attachment")}</p>${editable?button(q.file?"Remove sample attachment":"Attach sample quotation","attachment",`data-quote-index="${i}"`)+button(p.selectedQuote===i?"Selected supplier":"Choose this supplier","use-quote",`data-quote-index="${i}"`,p.selectedQuote===i):""}</div>`).join("")}</div><label class="bsp-check"><input type="checkbox" data-field="na" ${p.na?"checked":""} ${disabled}> Three quotations not available — mark N/A</label><label class="bsp-explanation" ${p.na?"":"hidden"}>Explanation *<textarea data-field="explanation" ${disabled}>${esc(p.explanation)}</textarea></label></section>${comparison(p,editable)}${submissionHistory(p)}${p.approved?'<section class="bsp-card"><h3>Approval</h3>'+facts([["Approved by","Manager (preview)"],["Approved on",p.approved]])+"</section>":""}`;
  }
  function auditValue(value){return value===null||value===undefined?"—":typeof value==="boolean"?(value?"Yes":"No"):String(value)||"—";}
  function submissionHistory(p){
    if(!p.submissions?.length)return "";
    return '<section class="bsp-card"><h3>Submission history</h3><p class="muted">Each submission preserves its values and the manager decision. Preview history resets on refresh.</p>'+p.submissions.slice().reverse().map(v=>`<details class="bsp-version"><summary>Version ${v.version} · ${esc(v.at)} · ${esc(v.decision.status)}</summary><p>${esc(v.actor)}${v.decision.at?" · "+esc(v.decision.actor)+" · "+esc(v.decision.at):""}</p>${v.decision.reason?"<p><strong>Decision reason:</strong> "+esc(v.decision.reason)+"</p>":""}${v.version>1?(v.changes.length?'<div class="bsp-tablewrap"><table><thead><tr><th>Changed field</th><th>Previous submission</th><th>This submission</th></tr></thead><tbody>'+v.changes.map(c=>"<tr><td>"+esc(c.field)+"</td><td>"+esc(auditValue(c.before))+"</td><td>"+esc(auditValue(c.after))+"</td></tr>").join("")+"</tbody></table></div>":"<p>No purchasing fields changed.</p>"):"<p>Initial submission.</p>"}<details><summary>Submitted values</summary><div class="bsp-tablewrap"><table><tbody>${Object.entries(rules.submissionValues(v.snapshot)).map(([k,value])=>"<tr><th>"+esc(k)+"</th><td>"+esc(auditValue(value))+"</td></tr>").join("")}</tbody></table></div></details></details>`).join("")+"</section>";
  }
  function updateTotals(){
    const p=currentPO();if(!p||view!=="po")return;
    root.querySelector(".bsp-totals").innerHTML=facts([["PO net total","AED "+money(total(p))],["VAT 5%","AED "+money(total(p)*.05)],["Grand total","AED "+money(total(p)*1.05)],["DCS budget for this PO","AED "+money(rules.scopeBudget(p))]]);
    p.items.forEach((x,i)=>{
      root.querySelector('[data-amount="'+i+'"]').textContent=money(x.qty*x.rate);
      root.querySelector('[data-over="'+i+'"]').textContent=x.rate>x.cost?"▲":"";
      root.querySelector('[data-selected-rate="'+x.sourceId+'"]').textContent=money(x.rate);
      root.querySelector('[data-line-variance="'+x.sourceId+'"]').textContent=hasPrice(x.rate)?money(x.qty*(x.rate-x.cost)):"—";
      root.querySelector('[data-comparison-qty="'+x.sourceId+'"]').textContent=x.qty;
    });
    root.querySelector("[data-scope-budget]").textContent=money(rules.scopeBudget(p));
    root.querySelector("[data-selected-total]").textContent=poPriced(p)?money(total(p)):"Not priced";
    root.querySelector("[data-total-variance]").textContent=poPriced(p)?money(total(p)-rules.scopeBudget(p)):"—";
    p.quotes.forEach((q,i)=>{
      root.querySelector('[data-quote-total="'+i+'"]').textContent=quotePriced(p,q)?money(quoteTotal(p,q)):"Not priced";
      root.querySelector('[data-card-quote-total="'+i+'"]').textContent=quotePriced(p,q)?"AED "+money(quoteTotal(p,q)):"Not priced";
      root.querySelector('[data-quote-heading="'+i+'"]').textContent=(q.supplier||"Supplier "+(i+1))+" unit price";
      root.querySelector('[data-quote-variance="'+i+'"]').textContent=quotePriced(p,q)?money(quoteTotal(p,q)-rules.scopeBudget(p)):"—";
    });
  }
  function validatePO(p) { return rules.validatePO(current(),p); }
  function quotation() {
    return `<h2>${esc(current().quotation)} ${badge(quotationWon?"Won":"Quoted")}</h2><p class="muted">Sales handover demonstration · Paul</p><section class="bsp-card">${facts([["Project",current().project],["Customer",current().customer],["Deal Cost Sheet",current().dcs]])}${itemsTable(current().items)}<label>Customer PO reference<input data-customer-po value="${esc(quotationPO)}" placeholder="Example: ZZ-PO-7781" ${role!=="Sales"||quotationWon?"disabled":""}></label><p>Customer PO attachment: ${quotationPO?"Sample Customer-PO.pdf (simulated)":"Not attached"}</p>${button("Mark quotation Won","win",role!=="Sales"||quotationWon?"disabled":"")}${button("Send to Procurement","handover",role!=="Sales"||!quotationWon||current().status!=="Not sent"?"disabled":"",true)}</section>`;
  }
  function pdf() {
    const r=current(),p=currentPO();
    return `<div class="bsp-heading"><h2>Purchase order PDF preview</h2><div>${button("Back to PO","back-po")}${button("Download sample PDF","download-pdf","",true)}</div></div><div class="bsp-download" role="status">${pdfLinks(p)}</div><div class="bsp-paper"><div class="bsp-document-label">SAMPLE — NOT VALID FOR PURCHASE</div><h2>Purchase Order</h2><h3>Bits Secure IT Infrastructure LLC – Dubai</h3>${facts([["PO number",p.id],["Supplier",p.supplier],["Requisition",r.id],["Contact",p.contact],["Address",p.address],["Email",p.email],["Phone",p.phone],["TRN / VAT",p.trn],["Material group",p.group],["Supplier quotation",p.selectedQuote===null?"N/A exception":p.id+"/Q"+(p.selectedQuote+1)+" · "+p.quotes[p.selectedQuote].file],["Submission version",String(p.submissions?.length||1)]])}${itemsTable(p.items,true)}${facts([["Net total","AED "+money(total(p))],["VAT 5%","AED "+money(total(p)*.05)],["Grand total","AED "+money(total(p)*1.05)],["Payment terms",p.terms==="Custom"?p.customTerms:p.terms],["Expected delivery",p.delivery?new Date(p.delivery+"T00:00:00").toLocaleDateString("en-GB",{day:"2-digit",month:"short",year:"numeric"}):""],["Approved",p.approved]])}<p>This is a demonstration generated by the BS Procurement screen preview. It is not an issued ERPNext Purchase Order.</p></div>`;
  }
  function pdfLinks(p){
    const ready=p.preparedPDF;
    if(!ready||ready.expires_at*1000<=Date.now())return '<p class="muted">Download sample PDF prepares the document for saving or printing.</p>';
    return '<p><a class="bsp-button primary" href="'+esc(ready.download_url)+'" download>Download prepared PDF</a> <a class="bsp-button" href="'+esc(ready.view_url)+'" target="_blank" rel="noopener noreferrer">Open PDF / Print</a></p><p class="muted">Links expire after five minutes. Prepare the PDF again if needed. Printing uses the same generated PDF.</p>';
  }
  async function downloadSamplePDF(r,p,b){
    b.disabled=true;b.textContent="Preparing PDF…";
    try{
      const response=await frappe.call({method:"bsgroup.bs_group.page.bs_procurement.bs_procurement.download_sample_pdf",type:"POST",args:{payload:JSON.stringify({pr:r.id,po:p.id,status:p.status,supplier:p.supplier,contact:p.contact,email:p.email,phone:p.phone,address:p.address,trn:p.trn,group:p.group,terms:p.terms==="Custom"?p.customTerms:p.terms,delivery:p.delivery,approved:p.approved,version:p.submissions?.length||1,quote:p.selectedQuote===null?"N/A exception: "+p.explanation:p.id+"/Q"+(p.selectedQuote+1)+" - "+p.quotes[p.selectedQuote].file,items:p.items})}});
      const result=response.message;
      if(!result?.download_url||!result?.view_url)throw new Error("The PDF service returned no file link.");
      // Ignore a completed request if the demonstration was reset while it ran.
      if(!requests.includes(r)||!r.orders.includes(p))return;
      p.preparedPDF={download_url:result.download_url,view_url:result.view_url,expires_at:result.expires_at};
      events.unshift({at:stamp(),actor:"System (preview)",pr:r.id,text:"Generated sample PDF for "+p.id+"."});
      renderActivity();
      if(view==="pdf"&&current()===r&&currentPO()===p){
        const destination=root.querySelector(".bsp-download");
        destination.innerHTML=pdfLinks(p);
        destination.querySelector("a[download]").click();
      }
      frappe.show_alert({message:"Sample PDF ready. The save and print links are available below.",indicator:"green"});
    }catch(error){frappe.msgprint("The sample PDF could not be generated. "+esc(error.message||"Please retry."));}
    finally{b.disabled=false;b.textContent="Download sample PDF";}
  }
  function reject(action){
    const r=current(),p=currentPO();const isPO=action==="reject-po";
    frappe.prompt([{fieldname:"reason",fieldtype:"Small Text",label:"Reason for rejection",reqd:1}],values=>{
      if(role!=="Manager"||(isPO?p.status:r.status)!=="Pending Approval")return;
      if(!values.reason.trim())return;
      if(isPO){p.status="Rejected";p.reason=values.reason;rules.recordDecision(p,"Rejected",stamp(),"Manager (preview)",values.reason);}else{r.status="Rejected";r.reason=values.reason;}
      log("Rejected "+(isPO?p.id:r.id)+": "+values.reason);render();updateTotals();
    },"Reject "+(isPO?p.id:r.id),"Reject");
  }
  root.addEventListener("input",event=>{
    const t=event.target;
    if(t.hasAttribute("data-order-search")){orderQuery=t.value;filterOrderRows();return;}
    if(t.hasAttribute("data-search")){query=t.value;filterRows();return;}
    if(t.hasAttribute("data-customer-po")){if(role==="Sales"&&!quotationWon)quotationPO=t.value;return;}
    if(t.dataset.pick!==undefined){
      if(current().status!=="On Process"||role!=="Procurement")return;
      if(t.checked)picks[t.dataset.pick]=Number(root.querySelector('[data-pick-qty="'+t.dataset.pick+'"]').value);else delete picks[t.dataset.pick];return;
    }
    if(t.dataset.pickQty!==undefined){
      if(current().status==="On Process"&&role==="Procurement"&&picks[t.dataset.pickQty]!==undefined)picks[t.dataset.pickQty]=Number(t.value);return;
    }
    const p=currentPO();if(!p||view!=="po"||role!=="Procurement"||!["Draft","Rejected"].includes(p.status))return;
    if(t.dataset.field){p[t.dataset.field]=t.type==="checkbox"?t.checked:t.value;
      if(t.dataset.field==="na")root.querySelector(".bsp-explanation").hidden=!p.na;
      if(t.dataset.field==="terms")root.querySelector(".bsp-custom-terms").hidden=p.terms!=="Custom";
    }
    if(t.dataset.line!==undefined){p.items[+t.dataset.line][t.dataset.key]=["qty","rate"].includes(t.dataset.key)?Number(t.value):t.value;updateTotals();}
    if(t.dataset.quote!==undefined){p.quotes[+t.dataset.quote][t.dataset.key]=t.value;if(p.selectedQuote===+t.dataset.quote){p.supplier=t.value;root.querySelector('[data-field="supplier"]').value=t.value;}updateTotals();}
    if(t.dataset.quoteRate!==undefined){p.quotes[+t.dataset.quoteRate].rates[t.dataset.source]=Number(t.value);updateTotals();}
  });
  root.addEventListener("click",event=>{
    const b=event.target.closest("[data-action]");if(!b||b.disabled)return;
    const action=b.dataset.action;if(b.dataset.index!==undefined)active=+b.dataset.index;
    if(b.dataset.poIndex!==undefined)poIndex=+b.dataset.poIndex;
    const r=current(),p=currentPO();
    if(action==="role"){role=b.dataset.role;}
    else if(action==="reset"||action==="replay"){frappe.confirm("Reset this demonstration? Unsaved preview changes will be discarded.",()=>reset(action==="replay"));return;}
    else if(action==="search"){view="list";render();root.querySelector("[data-search]").focus();return;}
    else if(action==="activity"){root.querySelector(".bsp-activity").scrollIntoView({behavior:"smooth"});return;}
    else if(["list","orders","services"].includes(action))view=action;
    else if(action==="detail"){view="detail";tab="Requisition";picks={};}
    else if(action==="tab")tab=b.dataset.tab;
    else if(action==="request"&&role==="Procurement"&&["New","Rejected"].includes(r.status)){r.status="Pending Approval";r.requested="Procurement · "+stamp();r.approved="";log("Requested manager approval for "+r.id+".");view="detail";}
    else if(action==="approve"&&role==="Manager"&&r.status==="Pending Approval"){r.status="On Process";r.approved="Manager · "+stamp();log("Approved "+r.id+". Status On Process.");}
    else if((action==="reject"||action==="reject-po")&&role==="Manager"){reject(action);return;}
    else if(action==="create-po"&&role==="Procurement"&&r.status==="On Process"){if(!createPO(r))return;view="po";log("Started "+currentPO().id+" for selected lines of "+r.id+".");}
    else if(action==="open-po"||action==="back-po"){if(p)view="po";}
    else if(action==="cancel-po"&&role==="Procurement"&&["Draft","Rejected"].includes(p?.status)){p.status="Cancelled";log("Cancelled "+p.id+"; its quantities are available for another PO.");view="detail";tab="Requisition";picks={};}
    else if(action==="remove-line"&&role==="Procurement"&&["Draft","Rejected"].includes(p?.status)){p.items.splice(+b.dataset.lineIndex,1);}
    else if(action==="attachment"&&role==="Procurement"&&["Draft","Rejected"].includes(p?.status)){const q=p.quotes[+b.dataset.quoteIndex];q.file=q.file?"":"DEMO-Supplier-Quotation-"+(+b.dataset.quoteIndex+1)+".pdf";}
    else if(action==="use-quote"&&role==="Procurement"&&["Draft","Rejected"].includes(p?.status)){
      const i=+b.dataset.quoteIndex,q=p.quotes[i];p.selectedQuote=i;p.supplier=q.supplier;p.items.forEach(x=>x.rate=Number(q.rates[x.sourceId]||0));log("Selected quotation "+(i+1)+" for "+p.id+".");
    }
    else if(action==="send-po"&&role==="Procurement"&&["Draft","Rejected"].includes(p?.status)){
      const errors=validatePO(p);if(errors.length){const box=root.querySelector(".bsp-errors");box.hidden=false;box.innerHTML="<strong>Please complete the order</strong><ul>"+errors.map(x=>"<li>"+esc(x)+"</li>").join("")+"</ul>";box.scrollIntoView({behavior:"smooth",block:"center"});return;}
      const submission=rules.recordSubmission(p,stamp(),"Procurement (preview)");
      if(submission.version>1)log("Revised "+p.id+" for submission "+submission.version+": "+(submission.changes.map(c=>c.field+": "+auditValue(c.before)+" → "+auditValue(c.after)).join("; ")||"No purchasing fields changed."));
      p.status="Pending Approval";log("Sent "+p.id+" for manager approval"+(p.na?" with a quotation exception.":"."));
    }
    else if(action==="approve-po"&&role==="Manager"&&p?.status==="Pending Approval"){const errors=validatePO(p);if(errors.length){frappe.msgprint(errors.map(esc).join("<br>"));return;}p.status="Approved";p.approved=stamp();rules.recordDecision(p,"Approved",p.approved,"Manager (preview)");log("Approved "+p.id+". PDF preview available.");}
    else if(action==="pdf"&&p?.status==="Approved")view="pdf";
    else if(action==="download-pdf"&&p?.status==="Approved"){downloadSamplePDF(r,p,b);return;}
    else if(action==="win"&&role==="Sales"){if(!quotationPO.trim()){frappe.msgprint("Enter a customer PO reference. A sample attachment is simulated for this preview.");return;}quotationWon=true;log("Marked quotation Won with sample customer PO.");}
    else if(action==="handover"&&role==="Sales"&&quotationWon&&quotationPO.trim()&&r.status==="Not sent"){r.status="New";r.customerPO=quotationPO;log("Sent "+r.quotation+" to Procurement. Created "+r.id+".");view="list";}
    render();updateTotals();
  });
  render();
};
