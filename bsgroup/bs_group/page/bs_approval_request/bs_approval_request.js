frappe.pages['bs-approval-request'].on_page_load = function(wrapper) {
    const page=frappe.ui.make_app_page({parent:wrapper,title:__('Approval Request'),single_column:true});
    const root=document.createElement('div');root.className='bs-approval-inbox';page.main.append(root);
    if(frappe.session.user!=='mohan@bitssecureit.com') {
        root.textContent=__('Approval Request is available only to Mohan.');return;
    }
    const esc=value=>frappe.utils.escape_html(String(value??''));
    const api=async(method,args={})=>(await frappe.call({method:'bsgroup.approval_requests.'+method,args})).message;
    const money=(value,currency)=>`${esc(currency||'')} ${Number(value||0).toLocaleString('en',{minimumFractionDigits:currency==='OMR'?3:2,maximumFractionDigits:currency==='OMR'?3:2})}`;
    const date=value=>esc(value?frappe.datetime.str_to_user(value):'—');
    const link=(dt,name,label)=>name?`<a href="/desk/${dt}/${encodeURIComponent(name)}" target="_blank" rel="noopener">${esc(label||name)}</a>`:'—';
    const facts=rows=>'<div class="bsar-facts">'+rows.map(([label,value])=>`<div><small>${esc(label)}</small><strong>${value}</strong></div>`).join('')+'</div>';
    let records=[],kind='all',search='',sequence=0,reviewing=false;
    root.innerHTML=`<style>
      .bs-approval-inbox{color:#17395d;padding:8px 0 24px}.bsar-header{background:#16384e;color:white;border-radius:14px;padding:24px 28px;margin-bottom:18px}
      .bsar-header small{letter-spacing:1.5px;color:#b8d5e6}.bsar-header h2{margin:8px 0;color:white;font-size:25px}.bsar-header p{margin:0;color:#d3e2ed}
      .bsar-controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:18px 0}.bsar-controls button{background:white;border:1px solid #d5dfeb;border-radius:8px;padding:9px 14px;color:#17395d}.bsar-controls button.active{background:#215db4;color:white;border-color:#215db4}
      .bsar-controls input{margin-left:auto;min-width:220px;max-width:100%;padding:9px 12px;border:1px solid #d5dfeb;border-radius:8px}
      .bsar-table-wrap{overflow:auto;background:white;border:1px solid #dce5ef;border-radius:12px}.bsar-table{width:100%;margin:0}.bsar-table th{background:#edf3fa;color:#35577a;font-size:12px;padding:13px;white-space:nowrap}.bsar-table td{padding:13px;border-top:1px solid #e4ebf3;vertical-align:middle}.bsar-table small{display:block;color:#6f7f92;margin-top:5px}.bsar-badge{display:inline-block;background:#eaf5f3;color:#107d72;border-radius:6px;padding:4px 8px;font-size:12px}.bsar-empty{padding:36px;text-align:center;color:#627489}.bsar-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:10px 0 18px}.bsar-facts>div{padding:12px;background:#f4f7fb;border:1px solid #e1e8f0;border-radius:8px}.bsar-facts small{display:block;color:#6b7a8b;margin-bottom:5px}.bsar-facts strong{display:block;overflow-wrap:anywhere}.bsar-note{padding:12px;border-radius:8px;background:#fff6e6;margin:12px 0}.bsar-review-table{width:100%;font-size:12px}.bsar-review-table th,.bsar-review-table td{padding:8px;border:1px solid #e1e8f0;vertical-align:top}.bsar-review-table th{background:#edf3fa}.bsar-review{max-height:52vh;overflow:auto}.bsar-status{font-size:12px;color:#63778e;margin:10px 0}
    </style><div class="bsar-header"><small>SALES / MOHAN'S APPROVALS</small><h2>Approval Request</h2><p>Review sales commercial approvals and purchase requisitions in one place.</p></div>
    <div class="bsar-controls"><button data-kind="all" class="active">All Requests</button><button data-kind="sales">Sales</button><button data-kind="purchase">Purchase Requisitions</button><input type="search" aria-label="Search approval requests" placeholder="Search request, customer or requester"></div>
    <div class="bsar-status" aria-live="polite"></div><div class="bsar-results"></div>`;
    const results=root.querySelector('.bsar-results'),status=root.querySelector('.bsar-status');
    function render() {
        const visible=records.filter(row=>(kind==='all'||kind===row.kind)&&[row.name,row.subject,row.customer,row.requested_by,row.quotation,row.company].join(' ').toLowerCase().includes(search.toLowerCase()));
        for(const button of root.querySelectorAll('[data-kind]')) {
            const key=button.dataset.kind, label=key==='all'?'All Requests':key==='sales'?'Sales':'Purchase Requisitions';
            button.textContent=`${label} (${records.filter(r=>key==='all'||r.kind===key).length})`;button.classList.toggle('active',key===kind);
        }
        if(!visible.length){results.innerHTML='<div class="bsar-table-wrap bsar-empty">'+(search?'No requests match your search.':'No pending approval requests in this view.')+'</div>';return;}
        results.innerHTML=`<div class="bsar-table-wrap"><table class="bsar-table"><thead><tr><th>Request</th><th>Customer / Project</th><th>Requested by</th><th>Amount</th><th>Status</th><th></th></tr></thead><tbody>${visible.map(row=>`<tr><td><span class="bsar-badge">${row.kind==='sales'?'Sales':'Purchase Requisition'}</span><strong style="display:block;margin-top:6px">${esc(row.name)}</strong><small>${esc(row.quotation||'')}</small></td><td>${esc(row.subject||row.customer||'—')}<small>${esc(row.customer||'')} · ${esc(row.company||'')}</small></td><td>${esc(row.requested_by)}<small>${date(row.modified)}</small></td><td style="white-space:nowrap">${money(row.amount,row.currency)}<small>${row.kind==='sales'?'Selling value':'Requested budget'}</small></td><td>${esc(row.state)}</td><td><button class="btn btn-primary btn-sm" data-review="${esc(row.name)}" data-type="${row.kind}">Review</button></td></tr>`).join('')}</tbody></table></div>`;
    }
    async function refresh() {
        const ticket=++sequence;status.textContent='Loading pending requests…';
        try {const data=await api('pending');if(ticket!==sequence)return;records=data.requests;render();status.textContent=`${records.length} pending request(s) · Refreshed just now`;}
        catch(error){if(ticket===sequence){records=[];results.innerHTML='<div class="bsar-empty">Unable to load approvals. Use Refresh to try again.</div>';status.textContent='Requests could not be loaded.';}}
    }
    function reviewHTML(data) {
        if(data.kind==='sales') {
            const d=data.deal,c=data.current,p=data.previous_approved;
            return `<div class="bsar-review">${facts([['Costing sheet',link('deal-cost-sheet',data.name)],['Quotation',link('quotation',data.quotation)],['Customer',esc(d.customer||'—')],['Revision',esc(data.revision)],['Current cost',money(c.total_cost,d.currency)],['Current selling',money(c.total_selling,d.currency)],['Gross margin',esc(c.margin_percent)+'%'],[p.comparison_basis||'Previous selling',money(p.total_selling,d.currency)]])}
            <p><b>Approval reason:</b> ${esc(data.why?.approval_reason||data.why?.policy_basis||'Commercial review required.')}</p>
            ${(data.blockers||[]).map(b=>`<div class="bsar-note">${esc(b)}</div>`).join('')}
            <table class="bsar-review-table"><thead><tr><th>Item / Description</th><th>Quantity</th><th>Unit cost</th><th>Unit selling</th></tr></thead><tbody>${data.items.map(r=>`<tr><td>${esc(r.item)}<br>${esc(r.description)}</td><td>${esc(r.qty)} ${esc(r.uom)}</td><td>${money(r.cost,d.currency)}</td><td>${money(r.selling,d.currency)}</td></tr>`).join('')}</tbody></table>
            <p style="margin-top:12px">This decision applies to the displayed commercial revision. It does not mark the quotation Won or send it to Procurement.</p></div>`;
        }
        return `<div class="bsar-review">${facts([['Purchase Requisition',link('material-request',data.name)],['Project',link('project',data.project)],['Customer',esc(data.customer||'—')],['Quotation',link('quotation',data.quotation)],['Costing sheet',link('deal-cost-sheet',data.dcs)],['Customer PO reference',esc(data.customerPO||'—')]])}
        <table class="bsar-review-table"><thead><tr><th>Item / Description</th><th>Quantity</th><th>Unit budget</th><th>Total</th></tr></thead><tbody>${data.items.map(r=>`<tr><td>${esc(r.item_code)}<br>${esc(r.description)}</td><td>${esc(r.qty)} ${esc(r.uom)}</td><td>${money(r.cost,data.currency)}</td><td>${money(r.qty*r.cost,data.currency)}</td></tr>`).join('')}</tbody></table>
        <p style="margin-top:12px">Approve to release this requisition for purchasing. Purchase Order approvals remain separate.</p></div>`;
    }
    async function openReview(type,name) {
        if(reviewing)return;reviewing=true;
        try {
            const data=await api('review',{kind:type,name});let dialog;
            dialog=new frappe.ui.Dialog({title:__('Review {0}',[name]),size:'extra-large',fields:[
                {fieldtype:'HTML',fieldname:'review',options:reviewHTML(data)},
                {fieldtype:'Select',fieldname:'action',label:__('Decision'),options:['',...data.actions],reqd:1},
                {fieldtype:'Small Text',fieldname:'reason',label:__('Reason / Note'),description:__('A reason is required for Reject or Return for Rework.')}
            ],primary_action_label:__('Record Decision'),async primary_action(values){
                if(values.action!=='Approve'&&!String(values.reason||'').trim()){frappe.msgprint(__('Enter a reason for this decision.'));return;}
                dialog.disable_primary_action();
                try {await api('decide',{kind:type,name,modified:data.modified,revision:data.revision,action:values.action,reason:values.reason});dialog.hide();frappe.show_alert({message:__('Decision recorded'),indicator:'green'});await refresh();}
                finally {dialog.enable_primary_action();}
            }});dialog.show();if(!data.actions.length)dialog.disable_primary_action();
        } finally {reviewing=false;}
    }
    root.addEventListener('click',event=>{
        const filter=event.target.closest('[data-kind]');if(filter){kind=filter.dataset.kind;render();return;}
        const button=event.target.closest('[data-review]');if(button)openReview(button.dataset.type,button.dataset.review).catch(()=>{});
    });
    root.querySelector('input').addEventListener('input',event=>{search=event.target.value;render();});
    page.set_primary_action(__('Refresh'),refresh,'refresh');wrapper.bs_approval_refresh=refresh;refresh();
};
frappe.pages['bs-approval-request'].on_page_show = function(wrapper) {wrapper.bs_approval_refresh?.();};
