"""One-record, audited commercial correction; never modifies purchasing rates."""
import json
import frappe
from frappe.utils import flt, now_datetime

QUOTE = 'QTN-2026-01336'
SHEET = 'DCS-REEM-AL-BAWADI-REAL-ESTATE-DEVELOPMENT-LLC-005'
REQUEST = 'MAT-MR-2026-00020'
REASON = 'Reconciled to customer PO RABRED/BITS/26-077/2026: subtotal 240419.33, customs 1370, discount 23789.33, net 218000, VAT additional 10900. Purchase costs unchanged.'
EVENT = 'PAUL_PO_077_RECONCILED'


def records():
    from bsgroup.oman_quotation_flow import uae
    if not uae() or frappe.session.user != 'mohan@bitssecureit.com':
        frappe.throw('This correction is limited to Mohan and the verified UAE customer PO.', frappe.PermissionError)
    q = frappe.get_doc('Quotation', QUOTE, for_update=True)
    d = frappe.get_doc('Deal Cost Sheet', SHEET, for_update=True)
    r = frappe.get_doc('Material Request', REQUEST, for_update=True)
    for doc in (q,d,r): doc.check_permission('write')
    if q.custom_deal_cost_sheet != d.name or q.custom_bsp_material_request != r.name or r.custom_bsp_quotation != q.name:
        frappe.throw('Source links changed; correction stopped.')
    return q,d,r


@frappe.whitelist(methods=['POST'])
def apply(mode='preview'):
    if mode not in ('preview', 'apply'):
        frappe.throw('Select preview or apply.')
    try:
        result = reconcile()
        result['preview_only'] = mode == 'preview'
        return result
    finally:
        if mode == 'preview':
            # Full rollback also discards after-commit notifications from the
            # preview revision; no test approval request survives.
            frappe.db.rollback()


def reconcile():
    q,d,r = records()
    if frappe.db.exists('DCS Governance Event', {'dcs':d.name,'event_code':EVENT}):
        return {'already_applied':True,'quotation':q.name,'dcs':d.name,'requisition':r.name}
    if (q.docstatus != 1 or q.custom_pipeline_stage != 'Won' or r.docstatus != 0
        or r.workflow_state != 'Draft' or len(q.items)!=5 or len(d.items)!=5 or d.addtional_charges
        or abs(flt(q.net_total)-218000)>.005 or abs(flt(q.total)-240420.5)>.005
        or abs(flt(d.total_cost)-174609)>.005 or abs(flt(q.grand_total)-228900)>.005):
        frappe.throw('The verified record values changed; correction requires a fresh review.')
    if frappe.db.exists('Purchase Order Item', {'material_request':r.name,'docstatus':['!=',2]}):
        frappe.throw('Purchasing has started. Reconciliation requires review of the linked orders first.')
    from bsgroup.dcs.procurement import po_file, costing_snapshot
    po_file(q)
    if q.custom_customer_po != '/private/files/BITS-077-LPO.pdf':
        frappe.throw('The customer PO attachment changed.')
    code = frappe.db.get_single_value('BS Group Settings','dcs_addtional_item')
    if not code or not frappe.db.exists('Item',code):
        frappe.throw('Configure the existing DCS Additional Item before reconciling customs.')
    from bsgroup.oman_quotation_flow import snapshot
    snapshot(q,'Before customer PO customs and discount reconciliation')
    for doc in (d,r):
        frappe.get_doc(dict(doctype='Version',ref_doctype=doc.doctype,docname=doc.name,
            data=frappe.as_json({'changed':[], 'po_reconciliation_before':doc.as_dict()}))).insert(ignore_permissions=True)
    before_costs = [(x.name,x.item_code,x.qty,x.cost_rate,x.cost_amount) for x in d.items]
    before_pr = [(x.name,x.item_code,x.qty,x.rate,x.amount) for x in r.items]
    targets = [7500,37976.88,2676.79,137265.66,55000]
    quantities = [10,10,10,330,1]
    for index,(di,qi,amount,qty) in enumerate(zip(d.items,q.items,targets,quantities)):
        if di.item_code != qi.item_code or flt(di.qty)!=qty or flt(qi.qty)!=qty:
            frappe.throw('PO item identity or quantity changed at row '+str(index+1))
        rate = flt(amount/qty,9)
        di.selling_rate=rate; di.selling_amount=amount
        di.gp_value=amount-flt(di.cost_amount)
        di.gp_percent=flt(di.gp_value/amount*100,di.precision('gp_percent'))
        for field in ('selling_rate','selling_amount','gp_value','gp_percent'):
            frappe.db.set_value(di.doctype,di.name,field,di.get(field),update_modified=False)
        qi.rate=rate; qi.price_list_rate=rate; qi.custom_selling_rate=rate
        qi.discount_percentage=0; qi.discount_amount=0
    charge=d.append('addtional_charges',dict(description='Customs — customer PO RABRED/BITS/26-077/2026',amount=0,selling_amount=1370))
    charge.db_insert()
    item=frappe.get_doc('Item',code)
    q.append('items',dict(item_code=code,item_name=item.item_name,description='Customs',
        qty=1,uom=item.stock_uom,stock_uom=item.stock_uom,conversion_factor=1,rate=1370,price_list_rate=1370,
        custom_selling_rate=1370,custom_cost_rate=0,custom_oman_dcs_row='__additional_charges__',
        custom_oman_use_costing_description=1))
    # Preserve PO line-amount precision without changing site-wide currency settings.
    from bsgroup.dcs.quotation_discount import preserve_rate_precision
    preserve_rate_precision(q)
    q.apply_discount_on='Net Total'; q.additional_discount_percentage=0; q.discount_amount=23789.33
    q.calculate_taxes_and_totals()
    for key,value in [('total',241789.33),('net_total',218000),('total_taxes_and_charges',10900),('grand_total',228900)]:
        if abs(flt(q.get(key))-value)>.005: frappe.throw('PO reconciliation calculation failed: '+key)
    from bsgroup.dcs.quotation_discount import record_net_revision
    record_net_revision(d,218000,REASON)
    frappe.db.set_value('Deal Cost Sheet',d.name,dict(custom_frozen_revision_no=d.custom_dcs_revision_no,
        custom_frozen_total_selling=218000,custom_frozen_margin_percent=(218000-174609)/218000*100))
    q.custom_dcs_revision_reference=d.custom_revision_reference
    q.custom_oman_revision_no=int(q.custom_oman_revision_no or 0)+1
    # This narrowly validated repair retains the submitted Won document and its
    # previous snapshot; it does not invoke another award or procurement handover.
    q.modified = now_datetime()
    q.modified_by = frappe.session.user
    q.db_update()
    for row in q.items:
        if row.is_new(): row.db_insert()
        else: row.db_update()
    for row in q.taxes: row.db_update()
    d.reload();q.reload()
    manifest=json.loads(r.custom_bsp_source_snapshot)
    old_manifest=r.custom_bsp_source_snapshot
    manifest['costing']=costing_snapshot(d)
    manifest['commercial_reconciliation']=dict(reason=REASON,quotation_revision=q.custom_oman_revision_no)
    frappe.db.set_value('Material Request',r.name,'custom_bsp_source_snapshot',frappe.as_json(manifest))
    r.reload()
    if before_costs != [(x.name,x.item_code,x.qty,x.cost_rate,x.cost_amount) for x in d.items] or before_pr != [(x.name,x.item_code,x.qty,x.rate,x.amount) for x in r.items]:
        frappe.throw('Purchase-cost preservation check failed.')
    from bsgroup.dcs.governance import record_governance_event
    record_governance_event(d.name,EVENT,action_label='Reconcile customer PO commercial breakdown',
        source_endpoint='paul_po_reconciliation.apply',reason=REASON,revision_no=d.custom_dcs_revision_no,
        revision_reference=d.custom_revision_reference,changes=[dict(dt='Material Request',dn=r.name,
            field='custom_bsp_source_snapshot',old=old_manifest,new=r.custom_bsp_source_snapshot)])
    snapshot(q,'After customer PO customs and discount reconciliation; manager review required for net margin')
    d.add_comment('Info',REASON)
    r.add_comment('Info',REASON+' Original handover PDFs retained as historical evidence. Refer to current quotation for corrected commercial breakdown.')
    return dict(quotation=q.name,dcs=d.name,requisition=r.name,project=r.custom_project,net_selling=q.net_total,
        vat=q.total_taxes_and_charges,grand_total=q.grand_total,purchase_cost=d.total_cost,
        margin=d.custom_working_margin_percent,approval=d.custom_approval_state)


@frappe.whitelist()
def review():
    q,d,r=records()
    frappe.respond_as_web_page('Customer PO reconciliation', '''<h2>Paul — Radisson Blu PO reconciliation</h2>
    <p>Same quotation, DCS, requisition and project. Purchase costs stay AED 174,609.</p>
    <p>PO subtotal 240,419.33 + customs 1,370 − discount 23,789.33 = 218,000. VAT 10,900. Total 228,900.</p>
    <p>The corrected margin is 19.904%. A new revision will require Mohan’s normal commercial approval; this action does not approve it.</p>
    <button onclick="runCorrection('preview',this)">Verify reconciliation without saving</button>
    <button onclick="runCorrection('apply',this)">Apply verified PO reconciliation</button><pre id="result"></pre>
    <script>function runCorrection(mode,button){button.disabled=true;frappe.call({method:'bsgroup.dcs.paul_po_reconciliation.apply',type:'POST',args:{mode:mode},callback:r=>{document.getElementById('result').textContent=JSON.stringify(r.message,null,2);button.disabled=false},error:()=>{button.disabled=false}})}</script>''')
