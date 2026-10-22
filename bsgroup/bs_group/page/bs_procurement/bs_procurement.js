/* Standard ERPNext Material Requests and Purchase Orders. No simulated records. */
frappe.pages["bs-procurement"].on_page_load = function (wrapper) {
  const page=frappe.ui.make_app_page({parent:wrapper,title:"BS Procurement",single_column:true});
  const root=document.createElement("div");root.className="bsp";root.dataset.build="20261020-payment-policy";page.main.append(root);
  const esc=v=>frappe.utils.escape_html(String(v??""));
  const money=(v,currency)=>{const digits=(currency||order()?.currency||req()?.currency)==="OMR"?3:2;return new Intl.NumberFormat("en-AE",{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(Number(v)||0);};
  const api=async(method,args={})=>(await frappe.call({method:"bsgroup.procurement."+method,args,freeze:true})).message;
  const accountApi=async(method,args={})=>(await frappe.call({method:"bsgroup.procurement_accounts."+method,args,freeze:true})).message;
  const glApi=async(method,args={})=>(await frappe.call({method:"bsgroup.procurement_gl."+method,args,freeze:true})).message;
  const btn=(label,action,attrs="",primary=false)=>`<button type="button" class="bsp-button ${primary?"primary":""}" data-action="${action}" ${attrs}>${label}</button>`;
  const badge=s=>`<span class="bsp-badge ${["Approved","Fully ordered"].includes(s)?"good":["Rejected","Cancelled"].includes(s)?"bad":""}">${esc(s)}</span>`;
  const facts=rows=>'<div class="bsp-facts">'+rows.map(([k,v])=>`<div><small>${esc(k)}</small><strong>${esc(v||"—")}</strong></div>`).join("")+"</div>";
  const key=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,"0")).join("");
  let poList=[],poMore=false,poLoaded=false,searchTimer=null,searchVersion=0;
  let requests=[],requestsLoaded=false,active=null,po=null,receipt=null,view="list",query="",canCreate=false,hasMore=false,user="",picks={},dirty=false,busy=false;
  let settlementOrders=[],settlement=null,settlementMore=false,settlementRestricted=false,canCreateInvoice=false,canReadRequests=true;
  async function refreshSettlement(name,more=false,draw=true){
    if(name)settlement=await accountApi("get_payment_order",{name});
    else{
      const data=await accountApi("get_payment_orders",{start:more?settlementOrders.length:0,page_length:50});
      settlementOrders=more?settlementOrders.concat(data.invoices):data.invoices;
      settlementMore=data.has_more;settlementRestricted=data.restricted;canCreateInvoice=data.canCreate;user=data.user;canReadRequests=data.canReadRequests;settlement=null;
    }
    if(draw)render();
  }
  async function refreshOrders(more=false){
    const version=++searchVersion,search=query;
    const data=await api("get_orders",{start:more?poList.length:0,page_length:50,search});
    if(version!==searchVersion||search!==query)return;
    poList=more?poList.concat(data.orders):data.orders;poMore=data.has_more;poLoaded=true;
    if(view==="orders")render();
  }
  const req=()=>requests.find(r=>r.id===active);
  const order=()=>req()?.orders.find(p=>p.id===po);
  const actions=(r)=>r.actions.map(a=>btn(esc(a),"pr-action",`data-value="${esc(a)}"`,a==="Approve")).join("");
  const fileLink=(url,label)=>url&&/^\/private\/files\//.test(url)?`<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>`:esc(label||"No attachment");
  function replace(r){const i=requests.findIndex(x=>x.id===r.id);if(i<0)requests.unshift(r);else requests[i]=r;}
  async function refresh(name){
    if(name)replace(await api("get_request",{name}));
    else {const result=await api("get_requests",{page_length:50});requests=result.requests;requestsLoaded=true;canCreate=result.canCreate;user=result.user;hasMore=result.has_more;}
    dirty=false;render();
  }
  function history(rows){
    if(!rows?.length)return "<p class='muted'>No approval activity yet.</p>";
    return '<ul>'+rows.slice().reverse().map(e=>`<li><time>${esc(e.at)}</time><strong>${esc(e.actor)} · ${esc(e.action)}</strong>${e.reason?`<p>${esc(e.reason)}</p>`:""}${e.snapshot?`<details><summary>Values recorded at this step</summary>${snapshotTable(e.snapshot)}</details>`:""}</li>`).join("")+"</ul>";
  }
  function snapshotTable(s){
    const labels={company:"Company",supplier:"Supplier",currency:"Currency",terms:"Payment terms",schedule_date:"Required by",customer:"Customer",quotation:"Quotation",dcs:"Deal Cost Sheet",customer_po:"Customer PO",group:"Material group",net_total:"Net total",taxes_total:"Taxes and charges",grand_total:"Grand total"};
    const comparison=s.comparison||{};
    return facts(Object.entries(labels).filter(([k])=>s[k]!==undefined).map(([k,v])=>[v,s[k]]))+
      `<div class="bsp-tablewrap"><table><thead><tr><th>Item</th><th>Quantity</th><th>UOM</th><th>Unit rate</th></tr></thead><tbody>${(s.items||[]).map(x=>`<tr><td>${esc(x.item_code)}</td><td>${x.qty}</td><td>${esc(x.uom)}</td><td>${money(x.rate)}</td></tr>`).join("")}</tbody></table></div>`+
      (s.comparison?facts([["Quotation basis",comparison.exception?"Exception":"Three quotations"],["Exception reason",comparison.explanation],["Selection / negotiation notes",comparison.selection_reason],["Selected quotation",comparison.selected===null||comparison.selected===undefined?"—":String(comparison.selected+1)]])+`<div class="bsp-tablewrap"><table><thead><tr><th>Quotation</th><th>Supplier</th><th>Quoted net total</th></tr></thead><tbody>${(comparison.quotes||[]).map((q,i)=>`<tr><td>${i+1}</td><td>${esc(q.supplier)}</td><td>${money((s.items||[]).reduce((sum,x)=>sum+x.qty*Number(q.rates?.[x.material_request_item||("additional:"+x.name)]||0),0))}</td></tr>`).join("")}</tbody></table></div>`:"")+
      (s.request_evidence?.kind?supportSnapshot(s.request_evidence):"");
  }
  function supportSnapshot(s){
    return facts([["Request type",s.kind==="direct_invoice"?"Utility bill / direct invoice":"Purchase"],
      ["Quotation requirement",s.exception?"No three quotations required":"Three quotations"],["Notes",s.explanation]])+
      (s.quotes||[]).filter(q=>q.file).map(q=>`<p>${esc(q.supplier)} · ${fileLink(q.url,q.filename)}</p>`).join("")+
      (s.invoices||[]).map(f=>`<p>Invoice copy · ${fileLink(f.url,f.filename)}</p>`).join("");
  }
  function prSupporting(r){
    if(!r.manual)return "";
    const s=r.supporting,editable=r.canEditSupporting,disabled=editable?"":"disabled";
    return `<section class="bsp-card"><h3>PR quotations and supporting invoices</h3>
      <p class="muted">Attach three supplier quotations, or select the exception and explain why. Utility bills and direct invoices require invoice copies, the exception and notes before approval.</p>
      <label>Request type<select data-pr-field="kind" ${disabled}><option value="purchase" ${s.kind==="purchase"?"selected":""}>Purchase</option><option value="direct_invoice" ${s.kind==="direct_invoice"?"selected":""}>Utility bill / direct invoice</option></select></label>
      <div class="bsp-grid">${s.quotes.map((q,i)=>`<div class="bsp-quote"><h4>Quotation ${i+1}</h4><strong>${esc(q.supplier||"Select supplier")}</strong><p>${fileLink(q.url,q.filename)}</p>${editable?btn("Select supplier","pr-quote-supplier",`data-index="${i}"`)+btn("Upload quotation","pr-upload-quote",`data-index="${i}"`)+(q.file?btn("Remove from draft","pr-remove-quote",`data-index="${i}"`):""):""}</div>`).join("")}</div>
      <label class="bsp-check"><input type="checkbox" data-pr-field="exception" ${s.exception?"checked":""} ${disabled}> No three quotations required</label>
      <label>Notes — explain why three quotations are not required<textarea data-pr-field="explanation" ${s.exception?"required":""} ${disabled}>${esc(s.explanation)}</textarea></label>
      <h4>Invoice copies ${s.kind==="direct_invoice"?"(required)":"(optional)"}</h4>
      ${(s.invoices||[]).map((f,i)=>`<p>${fileLink(f.url,f.filename)} ${editable?btn("Remove from draft","pr-remove-invoice",`data-index="${i}"`):""}</p>`).join("")||"<p class='muted'>No invoice copies attached.</p>"}
      ${editable?btn("Attach invoice copies","pr-upload-invoice")+btn("Save supporting documents","save-pr-supporting","",true):""}
      <p class="bsp-pr-save-status muted">${dirty&&editable?"Unsaved supporting documents / notes":"Supporting documents and notes saved in ERPNext"}</p>
      ${editable?"<p class='muted'>Send for Approval saves these details and sends the complete PR to Mohan. Missing evidence or notes will prevent submission.</p>":"<p class='muted'>Submitted evidence is locked. Earlier versions remain in the approval history.</p>"}
      </section>`;
  }
  function changedPR(){
    dirty=true;
    const status=root.querySelector(".bsp-pr-save-status");
    if(status)status.textContent="Unsaved supporting documents / notes";
  }
  async function savePR(){
    const r=req();
    if(!r.canEditSupporting)return r;
    const updated=await api("save_request_evidence",{name:r.id,modified:r.modified,payload:JSON.stringify(r.supporting)});
    replace(updated);dirty=false;return updated;
  }
  function render(){
    root.innerHTML=`<aside class="bsp-side"><div class="bsp-brand"><span>B</span><div>BS Procurement<small>BS Group</small></div></div><nav>${btn("Purchase Requisition","list",view==="list"||view==="detail"?'aria-current="page"':"")}${btn("Purchase Order","orders",view==="orders"||view==="po"?'aria-current="page"':"")}${btn("Payment Order","services",view==="services"?'aria-current="page"':"")}</nav><div class="bsp-profile">${esc(user)}<small>Your ERP permissions apply</small></div></aside><div class="bsp-main"><header class="bsp-top"><span>BS Procurement / <strong>${view==="services"?"Payment Order":view==="receipt"?"Purchase Receipt":["po","orders"].includes(view)?"Purchase Order":"Purchase Requisition"}</strong></span>${btn("Refresh","refresh")}</header><section class="bsp-body"><div class="bsp-view"></div></section></div>`;
    const target=root.querySelector(".bsp-view");
    if(view==="list")target.innerHTML=list();
    if(view==="detail")target.innerHTML=detail();
    if(view==="orders")target.innerHTML=`<div class="bsp-heading"><h2>Purchase Order</h2><input data-search type="search" aria-label="Search purchase orders" placeholder="Search PO, PR, supplier or status"></div>${ordersTable(poList)}${poMore?btn("Load more purchase orders","more-orders"):""}<p class="muted">Search checks all permitted BS purchase orders, including older records.</p>`;
    if(view==="po")target.innerHTML=poForm();
    if(view==="receipt")target.innerHTML=receiptForm();
    if(view==="services")target.innerHTML=settlementView();
    filter();
  }
  function filter(){
    const search=root.querySelector("[data-search]");if(search)search.value=query;
    let serial=0;
    root.querySelectorAll("[data-search-text]").forEach(el=>{
      el.hidden=!el.dataset.searchText.includes(query.toLowerCase());
      const cell=el.querySelector("[data-serial]");if(cell&&!el.hidden)cell.textContent=++serial;
    });
  }
  function list(){
    return `<div class="bsp-heading"><div><h2>Purchase Requisition <small>${requests.length} loaded</small></h2><p class="muted">Each requisition has its own approval, cost comparison and purchasing progress.</p></div><div>${canCreate?btn("New Purchase Requisition","new-pr","",true):""}<input data-search type="search" aria-label="Search requisitions" placeholder="Search requisitions"></div></div><div class="bsp-tablewrap"><table><thead><tr><th>No.</th><th>Purchase requisition</th><th>Company / project</th><th>Requested by</th><th>PR approval</th><th>Purchasing status</th><th>Budget</th></tr></thead><tbody>${requests.map((r,i)=>`<tr data-search-text="${esc([r.id,r.company,r.project,r.person,r.approval,r.purchasing].join(" ").toLowerCase())}"><td data-serial>${i+1}</td><td>${btn(esc(r.id),"open-pr",`data-id="${esc(r.id)}"`)}</td><td>${esc(r.company)}<small style="display:block">${esc(r.project)}</small></td><td>${esc(r.person)}</td><td>${badge(r.approval)}</td><td>${badge(r.purchasing)}</td><td>${esc(r.currency)} ${money(r.items.reduce((s,x)=>s+x.qty*x.cost,0),r.currency)}</td></tr>`).join("")||'<tr><td colspan="7">No BS requisitions yet. Create a requisition to begin.</td></tr>'}</tbody></table></div>${hasMore?btn("Load more requisitions","more"):""}`;
  }
  function rail(r){
    const submitted=r.history.some(e=>e.action==="Pending Approval"),orders=r.orders.filter(p=>p.status!=="Cancelled"),approved=orders.filter(p=>p.status==="Approved");
    const stages=[["PR created",r.id,true],["Approval requested",submitted?"Requested":"Not requested",submitted],["PR approval",r.approval,r.approval==="Approved"],["Purchase orders",`${orders.length} active · ${r.purchasing}`,r.purchasing==="Fully ordered"],["PO approval",`${approved.length} of ${orders.length} approved`,!!orders.length&&orders.length===approved.length],["PO PDFs",`${approved.length} ready`,!!approved.length]];
    return '<div class="bsp-rail">'+stages.map(([a,b,c],i)=>`<div class="bsp-stage ${c?"done":""}"><strong>${i+1} ${c?"✓":""} ${esc(a)}</strong><small>${esc(b)}</small></div>`).join("")+"</div>";
  }
  function detail(){
    const r=req();if(!r||!Array.isArray(r.actions))return "<p>Loading requisition details…</p>";
    return `<div class="bsp-heading"><div><h2>${esc(r.id)} ${badge(r.approval)}</h2><p class="muted">${esc(r.company)} · ${esc(r.project)}</p></div><div>${btn("←","list",'aria-label="Back to Purchase Requisitions" title="Back to Purchase Requisitions"')}${r.canEdit?btn("Edit draft PR","standard-mr"):""}${r.canClone?btn("Clone PR","clone-pr"):""}${r.canDelete?btn("Delete draft PR","delete-pr"):""}${btn("Create Purchase Order","create-po",r.canPrepare?"":`disabled title="${esc(r.prepareReason)}"`,true)}${actions(r)}</div></div>${r.prepareReason?`<p class="muted">${esc(r.prepareReason)}</p>`:""}<section class="bsp-card"><h3>PR status and approval</h3>${facts([["Approver",r.approver?.name], ["Approver account",r.approver?.user],["Approval status",r.approval],["Purchasing status",r.purchasing],["ERP status",r.erpStatus],["Latest decision reason",r.reason]])}${rail(r)}</section>${prSupporting(r)}<section class="bsp-card"><h3>Source documents</h3>${facts([["Requested by",r.person],["Customer",r.customer],["Customer PO",r.customerPO],["Quotation",r.quotation],["Deal Cost Sheet",r.dcs]])}<div>${r.quotation?btn("Open Quotation","source",`data-type="Quotation" data-name="${esc(r.quotation)}"`):""}${r.dcs?btn("Open Deal Cost Sheet","source",`data-type="Deal Cost Sheet" data-name="${esc(r.dcs)}"`):""}${fileLink(r.customerPOFile,r.customerPOFile?"Open Customer PO attachment":"")}</div><p class="muted">${r.handoverRevision?"Budget copied from awarded DCS revision "+esc(r.handoverRevision)+". Source quantities and budget are preserved.":"Budget rates come from this Material Request."}</p>${(r.handoverFiles||[]).map(f=>`<p>${fileLink(f.url,({quotation:"Awarded quotation",customer_po:"Customer PO",costing:"Awarded costing sheet"})[f.kind]||f.filename)}</p>`).join("")}${r.handoverResources||r.handoverCharges?`<p class="muted">${r.handoverResources} labour/resource rows and ${r.handoverCharges} additional charge rows remain in the costing evidence; purchasing lines contain the DCS Item rows.</p>`:""}</section><section class="bsp-card"><h3>PR line items and purchasing progress</h3><p class="muted">Draft and pending POs reserve quantities. Submitted POs count as ordered. Select PR items and quantities, or prepare a PO with additional items. Choose a supplier for each separate PO.</p><div class="bsp-tablewrap"><table><thead><tr><th>Select</th><th>Item</th><th>Requested</th><th>Ordered</th><th>Reserved, including ordered</th><th>Available</th><th>New PO qty</th><th>Budget rate (${esc(r.currency)})</th></tr></thead><tbody>${r.items.map(x=>`<tr><td><input type="checkbox" data-pick="${esc(x.sourceId)}" aria-label="Select ${esc(x.item_code)}" ${r.canPrepare&&x.available>0?"":"disabled"} ${picks[x.sourceId]!==undefined?"checked":""}></td><td>${esc(x.item_name||x.item_code)}<small style="display:block;white-space:pre-wrap">${esc(x.description)}</small></td><td>${x.qty} ${esc(x.uom)}</td><td>${x.ordered}</td><td>${x.reserved}</td><td>${x.available}</td><td><input type="number" data-pick-qty="${esc(x.sourceId)}" aria-label="New PO quantity ${esc(x.item_code)}" value="${picks[x.sourceId]??x.available}" min="0" max="${x.available}" step="any" ${r.canPrepare?"":"disabled"}></td><td>${money(x.cost)}</td></tr>`).join("")}</tbody></table></div>${r.canPrepare?btn("Create Purchase Order","create-po","",true):`<p class="muted">${esc(r.prepareReason)}</p>`}</section><section class="bsp-card"><h3>Linked Purchase Orders</h3>${ordersTable(r.orders)}</section><section class="bsp-activity"><h3>PR approval history</h3>${history(r.history)}</section>`;
  }
  function ordersTable(orders){
    return `<div class="bsp-tablewrap"><table><thead><tr><th>No.</th><th>Purchase Order</th><th>PR</th><th>Supplier</th><th>Approval</th><th>ERP status</th><th>Net total</th><th>Grand total</th></tr></thead><tbody>${orders.map((p,i)=>`<tr data-search-text="${esc([p.id,p.request,p.supplier,p.status,p.erpStatus].join(" ").toLowerCase())}"><td data-serial>${i+1}</td><td>${btn(esc(p.id),"open-po",`data-id="${esc(p.id)}" data-request="${esc(p.request)}"`)}</td><td>${esc(p.request)}</td><td>${esc(p.supplier)}</td><td>${badge(p.status)}</td><td>${esc(p.erpStatus)}</td><td>${p.status==="Cancelled"?"—":esc(p.currency)+" "+money(p.net,p.currency)}</td><td>${p.status==="Cancelled"?"—":esc(p.currency)+" "+money(p.grand,p.currency)}</td></tr>`).join("")||'<tr><td colspan="8">No Purchase Orders yet.</td></tr>'}</tbody></table></div>`;
  }
  function poForm(){
    const p=order();if(!p)return "<p>Open a Purchase Order.</p>";const disabled=p.editable?"":"disabled";
    return `<div class="bsp-heading"><div><small>Against ${esc(p.request)}</small><h2>${esc(p.id)} ${badge(p.status)}</h2><p class="muted">Standard Purchase Order · ${esc(p.erpStatus)}</p></div><div>${btn("Back to PR","back-pr")}${p.editable?btn("Save draft","save-po")+btn("Send for Approval","po-action",'data-value="Send for Approval"',true):""}${p.canApprove?btn("Reject","po-action",'data-value="Reject"')+btn("Approve","po-action",'data-value="Approve"',true):""}${p.canCancel?btn(p.docstatus===1?"Cancel submitted PO":"Withdraw PO","po-action",'data-value="Cancel"'):""}${p.canDelete?btn("Delete draft PO","delete-po"):""}${p.status==="Approved"?btn("Receive goods","create-receipt","",true):""}${p.status==="Approved"?`<a class="bsp-button" href="/api/method/bsgroup.procurement.pdf?name=${encodeURIComponent(p.id)}" target="_blank" rel="noopener">Open PO PDF</a>`:""}</div></div><p class="bsp-save-status muted">${dirty?"Unsaved changes":"Saved in ERPNext"}</p>${p.reason?`<p class="bsp-callout">Latest decision reason: ${esc(p.reason)}</p>`:""}${!p.editable?'<p class="bsp-callout">This order is locked. Rejected orders can be revised and resubmitted.</p>':""}<section class="bsp-card"><h3>Order</h3>${facts([["Company",p.company],["Currency",p.currency],["Supplier",p.supplier],["Approver",p.approver?.name],["Approver account",p.approver?.user]])}<div class="bsp-grid"><label>Purchase tax treatment *<select data-field="taxTemplate" ${disabled}><option value="">Select tax treatment…</option>${(p.taxTemplates||[]).map(x=>`<option value="${esc(x)}" ${p.taxTemplate===x?"selected":""}>${esc(x)}</option>`).join("")}</select></label><label>Purchase material group *<select data-field="group" ${disabled}><option value="">Select…</option>${["Hardware","Software","Professional Services","Utility","Others"].map(x=>`<option ${p.group===x?"selected":""}>${x}</option>`).join("")}</select></label><label>Expected delivery *<input type="date" data-field="delivery" value="${esc(p.delivery)}" ${disabled}></label></div></section><section class="bsp-card"><h3>Line items</h3>${p.editable?btn("Add additional item","add-po-item"):""}<p class="muted">Additional items stay linked to this PR through the PO. Include them in the supplier comparison and explain the addition for approval.</p><div class="bsp-tablewrap"><table><thead><tr><th>Item</th><th>Qty</th><th>UOM</th><th>Unit price (${esc(p.currency)})</th><th>Amount</th><th>PR budget rate</th><th></th></tr></thead><tbody>${p.items.map((x,i)=>`<tr><td>${esc(x.item_code)}${x.additional?'<small style="display:block">Additional item · outside PR list</small>':""}<small style="display:block">${esc(x.description)}</small></td><td><input type="number" aria-label="Quantity ${i+1}" data-line="${i}" data-key="qty" step="any" min="0" value="${x.qty}" ${disabled}></td><td>${p.editable?`<select aria-label="Purchase UOM ${i+1}" data-line="${i}" data-key="uom">${(x.uoms||[x.uom]).map(u=>`<option value="${esc(u)}" ${u===x.uom?"selected":""}>${esc(u)}</option>`).join("")}</select>`:esc(x.uom)}</td><td><input type="number" aria-label="Unit price ${i+1}" data-line="${i}" data-key="rate" step="any" min="0" value="${x.rate}" ${disabled}></td><td data-line-amount="${i}">${money(x.qty*x.rate)}</td><td data-budget-rate="${i}">${money(x.cost)}</td><td>${p.editable?btn("Remove","remove-line",`data-index="${i}"`):""}</td></tr>`).join("")}</tbody></table></div><div data-totals>${totals(p)}</div><p class="muted">Tax and grand totals are calculated by ERPNext when you save. No assumed VAT rate is added by this screen.</p></section><section class="bsp-card"><h3>Payment terms *</h3><textarea data-field="terms" ${disabled} style="width:100%;min-height:70px">${esc(p.terms)}</textarea></section><section class="bsp-card"><h3>Supplier quotations · three required</h3><p class="muted">Enter supplier prices in ${esc(p.currency)}, excluding taxes, for the same PO scope. Upload actual quotations as private attachments to this PO.</p><div class="bsp-grid">${p.quotes.map((q,i)=>`<div class="bsp-quote"><h4>Quotation ${i+1}</h4><strong>${esc(q.supplier||"Select supplier")}</strong><p>${fileLink(q.url,q.filename)}</p>${p.editable?btn("Select supplier","quote-supplier",`data-index="${i}"`)+btn("Upload quotation","upload",`data-index="${i}"`)+btn(p.selectedQuote===i?"Selected":"Choose this quotation","choose",`data-index="${i}"`,p.selectedQuote===i):""}</div>`).join("")}</div><label class="bsp-check"><input type="checkbox" data-field="na" ${p.na?"checked":""} ${disabled}> Three quotations unavailable — request an exception</label><label>Quotation exception explanation<textarea data-field="explanation" ${disabled}>${esc(p.explanation)}</textarea></label></section>${comparison(p)}<section class="bsp-activity"><h3>Submission and approval history</h3>${history(p.history)}</section>`;
  }
  function totals(p){
    return facts([["PO line total",p.currency+" "+money(p.items.reduce((s,x)=>s+x.qty*x.rate,0))],["Saved ERP net total",p.currency+" "+money(p.net,p.currency)],["Saved taxes and charges",p.currency+" "+money(p.taxes)],["Saved grand total",p.currency+" "+money(p.grand,p.currency)]]);
  }
  function receiptForm(){
    if(!receipt)return "<p>Loading Purchase Receipt…</p>";
    const x=receipt,disabled=x.editable?"":"disabled";
    return `<div class="bsp-heading"><div><small>Against ${esc(x.order)}</small><h2>${esc(x.id)} ${badge(x.status)}</h2><p class="muted">Standard Purchase Receipt · managed within BS Procurement</p></div><div>${btn("Back to PO","back-po")}${x.editable?btn("Save draft receipt","save-receipt")+btn("Submit receipt","submit-receipt","",true):""}</div></div><p class="bsp-save-status muted">${dirty?"Unsaved changes":"Saved in ERPNext"}</p><section class="bsp-card"><h3>Receipt</h3>${facts([["Company",x.company],["Supplier",x.supplier],["Receipt date",x.date],["ERP status",x.status]])}<p class="muted">Record accepted delivered quantities. Submitting this standard ERPNext receipt updates stock and makes the received goods available for the Payment Order.</p></section><section class="bsp-card"><h3>Received items</h3><div class="bsp-tablewrap"><table><thead><tr><th>Item</th><th>Quantity received</th><th>UOM</th><th>Receiving warehouse</th></tr></thead><tbody>${x.items.map((r,i)=>`<tr><td>${esc(r.item)}<small style="display:block">${esc(r.description)}</small></td><td><input data-receipt-qty="${i}" type="number" min="0" step="any" value="${esc(r.qty)}" ${disabled}></td><td>${esc(r.uom)}</td><td><input data-receipt-warehouse="${i}" value="${esc(r.warehouse)}" ${disabled}></td></tr>`).join("")}</tbody></table></div><p class="muted">Choose an existing warehouse for every stock item before submitting.</p></section>`;
  }
  function accountingView(s){
    const a=s.accounting;
    if(!a?.ready)return "";
    const ledger=s.ledger;
    return `<section class="bsp-card"><h3>Accounting codes</h3>${facts([["Journal code",a.journalCode||"Not specified"],["Supplier payable account",a.payable]])}
      <p class="muted">Journal code classifies this invoice and its accounting entries. Accounts are posted when Mohan approves the Payment Order.</p>
      <div class="bsp-tablewrap"><table><thead><tr><th>Item</th><th>GL code / account</th><th>Cost centre</th><th>Account selection</th></tr></thead><tbody>${a.lines.map(r=>`<tr><td>${esc(r.item)}</td><td>${esc(r.label||"Not set")}</td><td>${esc(r.costCenter||"—")}</td><td>${r.editable?"Invoice expense account":"From receipt / asset accounting"}</td></tr>`).join("")}</tbody></table></div>
      ${a.editable?btn("Edit accounting codes","edit-accounting","",true):'<p class="muted">Accounting codes are locked for approval. Corrections require a return for correction or amendment.</p>'}
      ${a.canViewLedger?btn(ledger?"Refresh accounting entries":"View accounting entries","view-accounting"):""}
      ${ledger?`<h4>Posted accounting entries · ${esc(ledger.currency)}</h4><div class="bsp-tablewrap"><table><thead><tr><th>GL code / account</th><th>Journal code</th><th>Debit</th><th>Credit</th><th>Cost centre / project</th></tr></thead><tbody>${ledger.records.map(r=>`<tr><td>${esc(r.label)}${r.cancelled?'<small style="display:block">Cancelled / reversal</small>':""}</td><td>${esc(r.journalCode||"—")}</td><td>${money(r.debit,ledger.currency)}</td><td>${money(r.credit,ledger.currency)}</td><td>${esc([r.costCenter,r.project].filter(Boolean).join(" / ")||"—")}</td></tr>`).join("")||'<tr><td colspan="5">No accounting entries available under your permissions.</td></tr>'}</tbody></table></div>`:""}</section>`;
  }
  function settlementView(){
    const amount=(value,currency)=>value===null?"—":esc(currency)+" "+money(value,currency);
    if(!settlement)return `<div class="bsp-heading"><div><h2>Payment Order</h2><p class="muted">Supplier / vendor invoices, approvals and payments.</p></div><div>${canCreateInvoice?btn("New Payment Order","new-payment-order","",true):""}<input data-search type="search" aria-label="Search payment orders" placeholder="Search invoice, supplier, PO or status"></div></div>${settlementRestricted?'<p class="bsp-callout">Purchase Invoice read permission is required to view payment orders.</p>':""}<div class="bsp-tablewrap"><table><thead><tr><th>No.</th><th>Payment Order / invoice</th><th>Supplier</th><th>Vendor invoice no.</th><th>Due date</th><th>Approval / payment status</th><th>Invoice total</th><th>Outstanding</th></tr></thead><tbody>${settlementOrders.map((o,i)=>`<tr data-search-text="${esc([o.id,o.supplier,o.bill,o.approval,o.status,...o.orders].join(" ").toLowerCase())}"><td data-serial>${i+1}</td><td>${btn(esc(o.id),"settlement",`data-id="${esc(o.id)}"`)}<small style="display:block">${esc(o.company)}</small></td><td>${esc(o.supplier)}</td><td>${esc(o.bill||"—")}</td><td>${esc(o.due||"—")}</td><td>${badge(o.approval||o.status)}<small style="display:block">${esc(o.status)}</small></td><td>${amount(o.total,o.currency)}</td><td>${amount(o.outstanding,o.outstandingCurrency)}</td></tr>`).join("")||'<tr><td colspan="8">No supplier invoices linked to BS Procurement yet.</td></tr>'}</tbody></table></div>${settlementMore?btn("Load more payment orders","settlement-more"):""}`;
    const s=settlement;
    const link=(type,id)=>type==="Purchase Receipt"?btn(esc(id),"open-receipt",`data-name="${esc(id)}"`):btn(esc(id),"source",`data-type="${esc(type)}" data-name="${esc(id)}"`);
    const notice=section=>section.restricted?'<p class="bsp-callout">Some linked records are restricted by your permissions.</p>':"";
    return `<div class="bsp-heading"><div><small>Payment Order · supplier invoice</small><h2>${esc(s.id)} ${badge(s.approval||s.status)}</h2><p class="muted">${esc(s.supplier)} · ${esc(s.company)}</p></div><div>${btn("All payment orders","settlement-list")}${btn("Open supplier invoice","source",`data-type="Purchase Invoice" data-name="${esc(s.id)}"`)}${s.actions.map(a=>btn(esc(a),"invoice-action",`data-value="${esc(a)}"`,a==="Approve")).join("")}${s.canPay?btn("Record payment","record-payment","",true):""}</div></div>
      <section class="bsp-card"><h3>Vendor invoice and approval</h3>${facts([["Approver",s.approver?.name],["Approver account",s.approver?.user],["Approved by",s.approvedBy],["Approved on",s.approvedOn],["Vendor invoice no.",s.bill],["Invoice date",s.date],["Due date",s.due],["Approval",s.approval],["Payment status",s.status],["Net amount",s.currency+" "+money(s.net,s.currency)],["Taxes and charges",s.currency+" "+money(s.taxes,s.currency)],["Invoice total",s.currency+" "+money(s.total,s.currency)],["Outstanding",s.outstanding===null?"—":s.outstandingCurrency+" "+money(s.outstanding,s.outstandingCurrency)]])}<p class="muted">This payment order uses the supplier invoice shown above. Supplier payments require this Payment Order to be approved by Mohan. Draft and cancelled invoices cannot be paid.</p></section>
      ${accountingView(s)}
      <section class="bsp-card"><h3>Purchase references and invoiced items</h3><div>${s.orders.map(id=>link("Purchase Order",id)).join("")}</div><div class="bsp-tablewrap"><table><thead><tr><th>Item</th><th>Quantity</th><th>Rate (${esc(s.currency)})</th><th>Amount (${esc(s.currency)})</th><th>Purchase Order</th><th>Receipt</th><th>Project</th></tr></thead><tbody>${s.items.map(r=>`<tr><td>${esc(r.item)}<small style="display:block">${esc(r.description)}</small></td><td>${esc(r.qty)} ${esc(r.uom)}</td><td>${money(r.rate,s.currency)}</td><td>${money(r.amount,s.currency)}</td><td>${esc(r.order)}</td><td>${esc(r.receipt||"—")}</td><td>${esc(r.project||"—")}</td></tr>`).join("")}</tbody></table></div></section>
      <section class="bsp-card"><h3>Matched receipts</h3>${notice(s.receipts)}<div class="bsp-tablewrap"><table><thead><tr><th>Receipt</th><th>Date</th><th>Status</th><th>Matched items</th></tr></thead><tbody>${s.receipts.records.map(d=>`<tr><td>${link("Purchase Receipt",d.id)}</td><td>${esc(d.date)}</td><td>${badge(d.status)}</td><td>${d.lines.map(r=>`${esc(r.item)}: ${esc(r.qty)} ${esc(r.uom)}${r.rejected?` · rejected ${esc(r.rejected)}`:""}`).join("<br>")}</td></tr>`).join("")||'<tr><td colspan="4">No receipts linked to this invoice. Non-stock services can be invoiced against their approved PO.</td></tr>'}</tbody></table></div></section>
      <section class="bsp-card"><h3>Payments</h3>${notice(s.payments)}<p class="muted">Amounts apply to this invoice only. Draft, cancelled and released allocations do not count as paid. Credits and other settlements are included in the invoice outstanding balance.</p><div class="bsp-tablewrap"><table><thead><tr><th>Payment Entry</th><th>Date</th><th>Status</th><th>Type</th><th>Invoice allocation</th></tr></thead><tbody>${s.payments.records.map(d=>`<tr><td>${link("Payment Entry",d.id)}${d.shared?'<small style="display:block">Payment also covers other documents</small>':""}</td><td>${esc(d.date)}</td><td>${badge(d.status)}${d.historical?'<small style="display:block">Previous allocation released</small>':""}</td><td>${esc(d.type)}</td><td>${d.historical?"—":amount(d.allocated,d.currency)}</td></tr>`).join("")||'<tr><td colspan="5">No payment allocations linked to this invoice.</td></tr>'}</tbody></table></div></section>`;
  }
  function comparison(p){
    return `<section class="bsp-card"><h3>Cost comparison · selected PO scope</h3><div class="bsp-tablewrap"><table><thead><tr><th>Item</th><th>Qty</th><th>PR budget rate</th>${p.quotes.map((q,i)=>`<th>${esc(q.supplier||"Quotation "+(i+1))} rate</th>`).join("")}<th>PO rate</th><th>PO vs budget</th><th>Reason for addition / price variance</th></tr></thead><tbody>${p.items.map((x,n)=>`<tr><td>${esc(x.item_code)}</td><td data-comp-qty="${n}">${x.qty}</td><td data-comp-budget="${n}">${money(x.cost)}</td>${p.quotes.map((q,i)=>`<td><input aria-label="Quotation ${i+1} rate ${n+1}" data-quote-rate="${i}" data-source="${esc(x.sourceId)}" type="number" min="0" step="any" value="${q.rates[x.sourceId]||""}" ${p.editable?"":"disabled"}></td>`).join("")}<td data-comp-rate="${n}">${money(x.rate)}</td><td data-comp-var="${n}">${money(x.qty*(x.rate-x.cost))}</td><td><textarea aria-label="Variance reason ${n+1}" data-line-reason="${esc(x.sourceId)}" minlength="15" ${p.editable?"":"disabled"}>${esc(p.lineReasons?.[x.sourceId]||"")}</textarea></td></tr>`).join("")}</tbody><tfoot data-comparison-total>${comparisonTotals(p)}</tfoot></table></div><label>Supplier selection / negotiation notes<textarea data-field="selectionReason" ${p.editable?"":"disabled"}>${esc(p.selectionReason)}</textarea></label><p class="muted">Give a reason of at least 15 characters for each additional item or price above the PR budget or different from the selected quotation. Budgets are converted to the selected PO currency and UOM. Positive variance is above budget.</p></section>`;
  }
  function comparisonTotals(p){
    return `<tr><th>Total (${esc(p.currency)})</th><td></td><td>${money(p.items.reduce((s,x)=>s+x.qty*x.cost,0))}</td>${p.quotes.map(q=>`<td>${p.items.every(x=>Number(q.rates[x.sourceId])>0)?money(p.items.reduce((s,x)=>s+x.qty*Number(q.rates[x.sourceId]),0)):"Not priced"}</td>`).join("")}<td>${money(p.items.reduce((s,x)=>s+x.qty*x.rate,0))}</td><td>${money(p.items.reduce((s,x)=>s+x.qty*(x.rate-x.cost),0))}</td><td></td></tr>`;
  }
  function changed(){
    dirty=true;const el=root.querySelector(".bsp-save-status");if(el)el.textContent="Unsaved changes";
    const p=order();if(!p)return;
    root.querySelector("[data-totals]").innerHTML=totals(p);
    root.querySelector("[data-comparison-total]").innerHTML=comparisonTotals(p);
    p.items.forEach((x,i)=>{
      root.querySelector(`[data-line-amount="${i}"]`).textContent=money(x.qty*x.rate);
      root.querySelector(`[data-comp-qty="${i}"]`).textContent=x.qty;
      root.querySelector(`[data-comp-rate="${i}"]`).textContent=money(x.rate);
      root.querySelector(`[data-budget-rate="${i}"]`).textContent=money(x.cost);
      root.querySelector(`[data-comp-budget="${i}"]`).textContent=money(x.cost);
      root.querySelector(`[data-comp-var="${i}"]`).textContent=money(x.qty*(x.rate-x.cost));
    });
  }
  const ask=(fields,title,primary="Continue")=>new Promise(resolve=>{
    const d=new frappe.ui.Dialog({title,fields,primary_action_label:primary,primary_action:values=>{resolve(values);d.hide();}});
    d.onhide=()=>resolve(null);d.show();
  });
  const additionalItemFields=()=>[
    {fieldname:"item_code",label:"Additional item",fieldtype:"Link",options:"Item",reqd:1,in_list_view:1,
      get_query:()=>({filters:{disabled:0,is_purchase_item:1}})},
    {fieldname:"qty",label:"Quantity",fieldtype:"Float",reqd:1,default:1,in_list_view:1},
    {fieldname:"rate",label:"Unit price",fieldtype:"Currency",default:0,in_list_view:1},
    {fieldname:"uom",label:"Purchase UOM",fieldtype:"Link",options:"UOM",
      description:"Leave blank to use the item's stock UOM."},
    {fieldname:"warehouse",label:"Receiving warehouse",fieldtype:"Link",options:"Warehouse",
      get_query:()=>({filters:{company:req().company,is_group:0,disabled:0}}),
      description:"Required for stock items."}
  ];
  async function save(){
    const p=order();
    const result=await api("save_order",{name:p.id,modified:p.modified,payload:JSON.stringify({
      supplier:p.supplier,group:p.group,delivery:p.delivery,terms:p.terms,taxTemplate:p.taxTemplate,items:p.items,currency:p.currency,conversionRate:p.conversionRate,
      comparison:{exception:p.na,explanation:p.explanation,selection_reason:p.selectionReason,line_reasons:p.lineReasons||{},
        selected:p.selectedQuote,quotes:p.quotes.map(q=>({supplier:q.supplier,file:q.file,rates:q.rates}))}
    })});
    req().orders[req().orders.findIndex(x=>x.id===p.id)]=result;dirty=false;return result;
  }
  async function createPR(){
    const values=await ask([
      {fieldname:"title",label:"Requisition title",fieldtype:"Data",reqd:1},
      {fieldname:"request_type",label:"Request type",fieldtype:"Select",options:"Purchase\nUtility bill / direct invoice",default:"Purchase",reqd:1},
      {fieldname:"company",label:"Company",fieldtype:"Link",options:"Company",reqd:1,default:frappe.defaults.get_user_default("Company")},
      {fieldname:"schedule_date",label:"Required by",fieldtype:"Date",reqd:1,default:frappe.datetime.add_days(frappe.datetime.get_today(),7)},
      {fieldname:"warehouse",label:"Receiving warehouse",fieldtype:"Link",options:"Warehouse",description:"Required for stock items; leave blank for non-stock services and utility bills."},
      {fieldname:"project",label:"Project",fieldtype:"Link",options:"Project"},
      {fieldname:"customer",label:"Customer",fieldtype:"Link",options:"Customer"},
      {fieldname:"customer_po",label:"Customer PO reference",fieldtype:"Data"},
      {fieldname:"items",label:"Requested items",fieldtype:"Table",reqd:1,in_place_edit:true,
        fields:[{fieldname:"item_code",label:"Item",fieldtype:"Link",options:"Item",reqd:1,in_list_view:1},
                {fieldname:"qty",label:"Quantity",fieldtype:"Float",reqd:1,in_list_view:1},
                {fieldname:"uom",label:"Purchase UOM",fieldtype:"Link",options:"UOM",in_list_view:1},{fieldname:"rate",label:"Budget per UOM",fieldtype:"Currency",in_list_view:1}]}
      ,{fieldname:"supporting_help",fieldtype:"HTML",options:"<p>Create the draft, then attach three quotations or select No three quotations required and enter notes. Utility bills / direct invoices also require invoice copies.</p>"}
    ],"New Purchase Requisition","Create draft");
    if(!values)return;values.key=key();values.supporting={kind:values.request_type==="Utility bill / direct invoice"?"direct_invoice":"purchase"};const r=await api("create_request",{payload:JSON.stringify(values)});replace(r);active=r.id;view="detail";picks={};dirty=false;render();
  }
  async function run(b){
    if(b.dataset.action==="edit-accounting"){
      const s=settlement;
      const rows=s.accounting.lines.filter(r=>r.editable);
      const fields=[{fieldname:"journal_code",label:"Journal code",fieldtype:"Data",default:s.accounting.journalCode,
        description:"Optional accounts-team classification, up to 40 letters, numbers, dots, hyphens, slashes or underscores."}];
      if(rows.length)fields.push({fieldname:"lines",label:"GL accounts by invoice item",fieldtype:"Table",in_place_edit:true,
        cannot_add_rows:true,cannot_delete_rows:true,data:rows.map(r=>({id:r.id,item:r.item,account:r.account})),
        fields:[{fieldname:"id",fieldtype:"Data",hidden:1},{fieldname:"item",label:"Item",fieldtype:"Data",read_only:1,in_list_view:1},
          {fieldname:"account",label:"GL code / account",fieldtype:"Link",options:"Account",reqd:1,in_list_view:1,
           get_query:()=>({filters:{company:s.company,is_group:0,disabled:0,root_type:"Expense"}})}]});
      fields.push({fieldname:"help",fieldtype:"HTML",options:"<p>Stock and fixed-asset accounts follow receipt and asset accounting. Saving codes keeps this Payment Order in draft until it is sent for approval.</p>"});
      const values=await ask(fields,"Payment Order accounting","Save accounting codes");
      if(!values)return;
      settlement=await glApi("save_accounting",{name:s.id,modified:s.modified,journal_code:values.journal_code||"",lines:JSON.stringify(values.lines||[])});
      render();return;
    }
    if(b.dataset.action==="view-accounting"){
      settlement.ledger=await glApi("get_ledger",{name:settlement.id});render();return;
    }
    if(b.dataset.action==="new-payment-order"){
      const values=await ask([
        {fieldname:"source_doctype",label:"Create from",fieldtype:"Select",options:"Purchase Receipt\nPurchase Order",default:"Purchase Receipt",reqd:1,
         description:"Use a submitted receipt for goods or assets. Purchase Order is for non-stock services."},
        {fieldname:"source_name",label:"Source document",fieldtype:"Dynamic Link",options:"source_doctype",reqd:1}
      ],"New Payment Order","Prepare supplier invoice");
      if(!values)return;
      const doc=await accountApi("prepare_payment_order",values);
      const synced=frappe.model.sync(doc);frappe.set_route("Form","Purchase Invoice",synced[0].name);return;
    }
    if(b.dataset.action==="record-payment"){
      const doc=await accountApi("prepare_payment",{name:settlement.id});
      const synced=frappe.model.sync(doc);frappe.set_route("Form","Payment Entry",synced[0].name);return;
    }
    if(b.dataset.action==="invoice-action"){
      settlement=await accountApi("invoice_action",{name:settlement.id,modified:settlement.modified,action:b.dataset.value});
      render();return;
    }

    const action=b.dataset.action,r=req(),p=order();
    if(action==="services"||action==="settlement-list"){view="services";query="";await refreshSettlement();return;}
    if(action==="settlement"){view="services";await refreshSettlement(b.dataset.id);return;}
    if(action==="settlement-more"){await refreshSettlement(null,true);return;}
    if(action==="refresh"&&view==="services"){await refreshSettlement(settlement?.id);return;}
    if(action==="orders"){view="orders";query="";await refreshOrders();return;}
    if(action==="more-orders"){await refreshOrders(true);return;}
    if(action==="refresh"&&view==="orders"){await refreshOrders();return;}
    if(["list"].includes(action)){
      if(!canReadRequests){frappe.msgprint("Material Request read permission is required to view requisitions and their linked orders.");return;}
      view=action;query="";if(!requestsLoaded)await refresh();else render();return;
    }
    if(action==="refresh"){await refresh(active&&["detail","po"].includes(view)?active:null);return;}
    if(action==="more"){const result=await api("get_requests",{start:requests.length,page_length:50});result.requests.forEach(replace);hasMore=result.has_more;render();return;}
    if(action==="new-pr"){await createPR();return;}
    if(action==="clone-pr"){
      const copied=await api("clone_request",{name:r.id,key:key()});
      replace(copied);active=copied.id;view="detail";dirty=false;picks={};render();
      frappe.msgprint("New draft PR created. Review the items and attach fresh quotations or invoice copies before sending for approval.");return;
    }
    if(action==="delete-pr"){
      const confirmed=await new Promise(resolve=>frappe.confirm("Delete this draft PR permanently?",()=>resolve(true),()=>resolve(false)));
      if(!confirmed)return;
      await api("delete_request",{name:r.id,modified:r.modified});
      active=null;view="list";dirty=false;picks={};await refresh();return;
    }
    if(action==="delete-po"){
      const confirmed=await new Promise(resolve=>frappe.confirm("Delete this draft PO permanently?",()=>resolve(true),()=>resolve(false)));
      if(!confirmed)return;
      await api("delete_order",{name:p.id,modified:p.modified});
      po=null;view="detail";dirty=false;picks={};await refresh(r.id);return;
    }
    if(action==="open-pr"){active=b.dataset.id;picks={};view="detail";await refresh(active);return;}
    if(action==="back-pr"){view="detail";picks={};await refresh(active);return;}
    if(action==="open-po"){
      active=b.dataset.request;po=b.dataset.id;view="po";dirty=false;
      await refresh(active);return;
    }
    if(action==="create-receipt"){
      receipt=await api("create_receipt",{order:p.id,modified:p.modified});view="receipt";dirty=false;render();return;
    }
    if(action==="back-po"){view="po";receipt=null;dirty=false;await refresh(active);return;}
    if(action==="save-receipt"){
      receipt=await api("save_receipt",{name:receipt.id,modified:receipt.modified,payload:JSON.stringify({items:receipt.items})});dirty=false;render();frappe.show_alert({message:"Purchase Receipt saved",indicator:"green"});return;
    }
    if(action==="submit-receipt"){
      if(dirty)receipt=await api("save_receipt",{name:receipt.id,modified:receipt.modified,payload:JSON.stringify({items:receipt.items})});
      receipt=await api("submit_receipt",{name:receipt.id,modified:receipt.modified});dirty=false;render();frappe.show_alert({message:"Purchase Receipt submitted",indicator:"green"});return;
    }
    if(action==="open-receipt"||(action==="source"&&b.dataset.type==="Purchase Receipt")){
      receipt=await api("get_receipt",{name:b.dataset.name});view="receipt";dirty=false;render();return;
    }
    if(["standard-mr","standard-po","source"].includes(action)){
      frappe.set_route("Form",action==="standard-mr"?"Material Request":action==="standard-po"?"Purchase Order":b.dataset.type,action==="standard-mr"?r.id:action==="standard-po"?p.id:b.dataset.name);return;
    }
    if(action==="pr-action"||action==="po-action"){
      const value=b.dataset.value;let reason="";
      if(value==="Reject"||value==="Cancel"){
        const answer=await ask([{fieldname:"reason",label:value==="Reject"?"Rejection reason":"Cancellation / withdrawal reason",fieldtype:"Small Text",reqd:1}],value+" "+(action==="pr-action"?r.id:p.id),value);
        if(!answer)return;reason=answer.reason;
      }
      if(action==="pr-action"){
        const fresh=value==="Send for Approval"?await savePR():r;
        replace(await api("request_action",{name:fresh.id,modified:fresh.modified,action:value,reason}));
      }
      else{
        const fresh=value==="Send for Approval"?await save():p;
        await api("order_action",{name:fresh.id,modified:fresh.modified,action:value,reason});
        replace(await api("get_request",{name:r.id}));
      }
      dirty=false;render();return;
    }
    if(action==="create-po"){
      if(!r.canPrepare){frappe.msgprint(r.prepareReason);return;}
      const selected=Object.keys(picks).length?picks:Object.fromEntries(r.items.filter(x=>x.available>0).map(x=>[x.sourceId,x.available]));
      const fields=[{fieldname:"supplier",label:"Supplier",fieldtype:"Link",options:"Supplier",reqd:1}];
      fields.push({fieldname:"additional_only",label:"Purchase only additional items outside the PR list",fieldtype:"Check",default:!Object.keys(selected).length});
      fields.push({fieldname:"additional_items",label:"Additional items (optional)",fieldtype:"Table",
        in_place_edit:true,fields:additionalItemFields(),
        description:"Selected PR lines will be included. If none were selected, all available PR quantities are included. You can continue preparing the draft in BS Procurement."});
      const answer=await ask(fields,"Create Purchase Order","Create Purchase Order");
      if(!answer)return;
      const newPO=await api("create_order",{request:r.id,modified:r.modified,supplier:answer.supplier,lines:JSON.stringify(answer.additional_only?{}:selected),
        additional_items:JSON.stringify(answer.additional_items||[]),key:key()});
      picks={};dirty=false;active=r.id;po=newPO.id;view="po";await refresh(active);return;
    }
    if(action==="tax-template"){
      const answer=await ask([{fieldname:"tax_template",label:"Purchase tax treatment",fieldtype:"Link",options:"Purchase Taxes and Charges Template",reqd:1,default:p.taxTemplate,
        get_query:()=>({filters:{company:p.company,disabled:0}}),description:"Select the applicable tax template, including a zero-tax treatment where VAT does not apply."}],"Purchase tax treatment","Use tax template");
      if(!answer)return;
      p.taxTemplate=answer.tax_template;changed();render();return;
    }
    if(action==="save-po"){await save();await refresh(r.id);frappe.show_alert({message:"Purchase Order saved",indicator:"green"});return;}
    if(action==="save-pr-supporting"){await savePR();render();frappe.show_alert({message:"PR supporting documents saved",indicator:"green"});return;}
    if(action.startsWith("pr-")&&r?.canEditSupporting){
      const s=r.supporting,index=+b.dataset.index;
      if(action==="pr-quote-supplier"){
        const answer=await ask([{fieldname:"supplier",label:"Supplier",fieldtype:"Link",options:"Supplier",reqd:1}],"Select PR quotation supplier");
        if(answer){s.quotes[index].supplier=answer.supplier;changedPR();render();}return;
      }
      if(action==="pr-remove-quote"){s.quotes[index]={supplier:s.quotes[index].supplier,file:"",filename:"",url:""};changedPR();render();return;}
      if(action==="pr-remove-invoice"){s.invoices.splice(index,1);changedPR();render();return;}
      if(action==="pr-upload-quote"||action==="pr-upload-invoice"){
        const invoice=action==="pr-upload-invoice";
        new frappe.ui.FileUploader({doctype:"Material Request",docname:r.id,make_attachments_public:false,
          allow_toggle_private:false,allow_web_link:false,allow_multiple:invoice,
          on_success:file=>{
            if(req()?.id!==r.id||!req()?.canEditSupporting)return;
            const support=req().supporting,value={file:file.name,filename:file.file_name,url:file.file_url};
            if(invoice)support.invoices.push(value);else support.quotes[index]={...support.quotes[index],...value};
            changedPR();render();frappe.show_alert({message:"File uploaded. Save the supporting documents or send the PR for approval.",indicator:"green"});
          }});return;
      }
    }
    if(!p?.editable)return;
    if(action==="add-po-item"){
      const values=await ask(additionalItemFields(),"Add additional item","Add item");
      if(!values)return;
      const fresh=dirty?await save():p;
      const updated=await api("add_order_item",{name:fresh.id,modified:fresh.modified,...values});
      r.orders[r.orders.findIndex(x=>x.id===p.id)]=updated;dirty=false;render();return;
    }
    if(action==="supplier-address"){
      const values=await ask([
        {fieldname:"mode",label:"Address option",fieldtype:"Select",options:"Use existing supplier address\nAdd new supplier address",default:"Use existing supplier address",reqd:1},
        {fieldname:"supplier_address",label:"Supplier address",fieldtype:"Link",options:"Address",
          description:"Select an address already linked to "+p.supplier+"."},
        {fieldname:"address_line1",label:"Address line 1",fieldtype:"Data"},
        {fieldname:"address_line2",label:"Address line 2",fieldtype:"Data"},
        {fieldname:"city",label:"City",fieldtype:"Data"},
        {fieldname:"country",label:"Country",fieldtype:"Link",options:"Country",default:"Oman"},
        {fieldname:"state",label:"State / region",fieldtype:"Data"},
        {fieldname:"pincode",label:"Postal code",fieldtype:"Data"},
        {fieldname:"phone",label:"Phone",fieldtype:"Data"},
        {fieldname:"email",label:"Email",fieldtype:"Data"}
      ],"Supplier address","Save address");
      if(!values)return;
      const adding=values.mode==="Add new supplier address";
      if(!adding&&!values.supplier_address){frappe.msgprint("Select a supplier address or choose Add new supplier address.");return;}
      if(adding&&(!values.address_line1||!values.city||!values.country)){frappe.msgprint("Enter address line 1, city and country.");return;}
      const updated=await api("set_order_supplier_address",{name:p.id,modified:p.modified,supplier_address:values.supplier_address||"",
        address:JSON.stringify({...values,mode:adding?"new":"existing"})});
      r.orders[r.orders.findIndex(x=>x.id===p.id)]=updated;dirty=false;render();return;
    }
    if(action==="currency"){
      const values=await ask([
        {fieldname:"currency",label:"PO and quotation currency",fieldtype:"Link",options:"Currency",reqd:1,default:p.currency},
        {fieldname:"rate",label:"Company currency per 1 PO currency unit",fieldtype:"Float",reqd:1,default:p.conversionRate,
         description:"Company currency: "+p.companyCurrency+". Use the approved transaction exchange rate."}
      ],"Currency and exchange rate");
      if(!values)return;
      if(!(Number(values.rate)>0)){frappe.msgprint("Enter a positive exchange rate.");return;}
      p.items.forEach(x=>x.cost=x.cost*Number(p.conversionRate||1)/Number(values.rate));
      p.currency=values.currency;p.conversionRate=Number(values.rate);dirty=true;render();return;
    }
    if(action==="supplier"||action==="quote-supplier"){
      const answer=await ask([{fieldname:"supplier",label:"Supplier",fieldtype:"Link",options:"Supplier",reqd:1}],action==="supplier"?"Select PO supplier":"Select quotation supplier");
      if(!answer)return;
      if(action==="supplier")p.supplier=answer.supplier;
      else{p.quotes[+b.dataset.index].supplier=answer.supplier;if(p.selectedQuote===+b.dataset.index)p.supplier=answer.supplier;}
      dirty=true;render();return;
    }
    if(action==="choose"){
      const i=+b.dataset.index,q=p.quotes[i];p.selectedQuote=i;p.supplier=q.supplier;p.items.forEach(x=>x.rate=Number(q.rates[x.sourceId]||0));dirty=true;render();return;
    }
    if(action==="remove-line"){
      if(p.items.length<=1){frappe.msgprint("Keep at least one PO line. Withdraw the PO to release all quantities.");return;}
      p.items.splice(+b.dataset.index,1);dirty=true;render();return;
    }
    if(action==="upload"){
      const index=+b.dataset.index;
      new frappe.ui.FileUploader({doctype:"Purchase Order",docname:p.id,make_attachments_public:false,allow_toggle_private:false,allow_web_link:false,allow_multiple:false,
        on_success:file=>{
          if(order()?.id!==p.id)return;
          p.quotes[index].file=file.name;p.quotes[index].filename=file.file_name;p.quotes[index].url=file.file_url;
          dirty=true;render();frappe.show_alert({message:"Quotation uploaded. Save the draft to link it to the comparison.",indicator:"green"});
        }});
    }
  }
  root.addEventListener("input",e=>{
    const t=e.target;
    if(view==="receipt"&&receipt&&t.dataset.receiptQty!==undefined){receipt.items[+t.dataset.receiptQty].qty=Number(t.value)||0;dirty=true;root.querySelector(".bsp-save-status").textContent="Unsaved changes";return;}
    if(view==="receipt"&&receipt&&t.dataset.receiptWarehouse!==undefined){receipt.items[+t.dataset.receiptWarehouse].warehouse=t.value;dirty=true;root.querySelector(".bsp-save-status").textContent="Unsaved changes";return;}
    if(t.hasAttribute("data-search")){query=t.value;if(view==="orders"){clearTimeout(searchTimer);searchTimer=setTimeout(()=>refreshOrders().catch(console.error),300);}else filter();return;}
    if(t.dataset.pick!==undefined){if(t.checked)picks[t.dataset.pick]=Number(root.querySelector(`[data-pick-qty="${t.dataset.pick}"]`).value);else delete picks[t.dataset.pick];return;}
    if(t.dataset.pickQty!==undefined){if(picks[t.dataset.pickQty]!==undefined)picks[t.dataset.pickQty]=Number(t.value);return;}
    if(t.dataset.prField&&view==="detail"&&req()?.canEditSupporting){
      req().supporting[t.dataset.prField]=t.type==="checkbox"?t.checked:t.value;
      changedPR();if(t.dataset.prField!=="explanation")render();return;
    }
    const p=order();if(view!=="po"||!p?.editable)return;
    if(t.dataset.lineReason){(p.lineReasons??={})[t.dataset.lineReason]=t.value;changed();return;}
    if(t.dataset.field)p[t.dataset.field]=t.type==="checkbox"?t.checked:t.value;
    if(t.dataset.line!==undefined){
      const row=p.items[+t.dataset.line];
      if(t.dataset.key==="uom"){
        const factor=row.uomFactors[t.value];row.cost=row.cost*factor/row.conversionFactor;
        row.conversionFactor=factor;row.uom=t.value;
      }else row[t.dataset.key]=Number(t.value);
    }
    if(t.dataset.quoteRate!==undefined)p.quotes[+t.dataset.quoteRate].rates[t.dataset.source]=Number(t.value);
    changed();
  });
  root.addEventListener("click",async e=>{
    const b=e.target.closest("[data-action]");if(!b||b.disabled||busy)return;
    const navigate=["list","orders","services","refresh","open-pr","back-pr","back-po","open-po","open-receipt","standard-mr","standard-po","source"].includes(b.dataset.action);
    if(dirty&&navigate){frappe.confirm("Discard unsaved changes?",()=>{dirty=false;execute(b);});return;}
    await execute(b);
  });
  async function execute(b){
    busy=true;b.disabled=true;
    try{await run(b);}catch(error){console.error(error);if(!(error._server_messages||error.responseJSON?._server_messages||error.responseJSON?.exc_type))frappe.msgprint("The action could not be completed. "+esc(error.message||"Check the server message and try again."));}
    finally{busy=false;b.disabled=false;}
  }
  root.innerHTML="<p>Loading BS Procurement…</p>";
  let firstShow=true;
  const incoming=()=>{
    const invoice=frappe.route_options?.bsp_invoice;
    if(invoice){delete frappe.route_options.bsp_invoice;view="services";return {invoice};}
    const orderName=frappe.route_options?.bsp_order;
    if(orderName){delete frappe.route_options.bsp_order;po=orderName;}
    const name=frappe.route_options?.bsp_request;
    if(name){delete frappe.route_options.bsp_request;active=name;view="detail";}
    if(orderName)view="po";
    return {request:name};
  };
  wrapper.bsp_refresh=()=>{
    if(firstShow){firstShow=false;return;}
    const target=incoming();
    if(dirty||busy)return;
    if(view==="orders"&&!target.invoice&&!target.request){refreshOrders();return;}
    if(target.invoice||view==="services"){refreshSettlement(target.invoice||settlement?.id);return;}
    refresh(target.request||(active&&["detail","po","receipt"].includes(view)?active:null));
  };
  const initial=incoming();
  (async()=>{
    await refreshSettlement(null,false,false);
    if(initial.invoice){view="services";await refreshSettlement(initial.invoice);}
    else if(canReadRequests){await refresh(initial.request||null);}
    else{view="services";render();}
  })().catch(error=>{console.error(error);root.innerHTML="<p>Unable to load BS Procurement. Check your permissions and reload.</p>";});

};
frappe.pages["bs-procurement"].on_page_show=wrapper=>wrapper.bsp_refresh?.();
