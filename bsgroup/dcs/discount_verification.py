"""Mohan-only live regression check. Every write is unconditionally rolled back."""
import frappe
from frappe.utils import flt
from bsgroup.dcs.quotation_discount import gross_selling, net_selling


def authorise():
    from bsgroup.oman_quotation_flow import enabled
    if frappe.session.user != 'mohan@bitssecureit.com' or not enabled():
        frappe.throw('This verification is restricted to Mohan on the enabled sites.', frappe.PermissionError)


@frappe.whitelist(methods=['POST'])
def verify(quotation):
    authorise()
    try:
        q=frappe.get_doc('Quotation',quotation,for_update=True)
        q.check_permission('write')
        if q.docstatus != 0 or q.custom_pipeline_stage in ('Won','Lost') or not q.custom_deal_cost_sheet:
            frappe.throw('Select an open Draft quotation linked to a DCS.')
        d=frappe.get_doc('Deal Cost Sheet',q.custom_deal_cost_sheet,for_update=True)
        d.check_permission('write')
        def costs():
            d.reload()
            return [d.total_cost,d.custom_working_total_cost,
                [(r.name,r.qty,r.cost_rate,r.cost_amount) for r in d.items],
                [(r.name,r.get('cost_rate'),r.get('cost_amount')) for r in d.resources],
                [(r.name,r.amount) for r in d.addtional_charges]]
        original_cost=costs()
        counts={dt:frappe.db.count(dt) for dt in ('Quotation','Material Request','Project')}
        results=[]
        gross=gross_selling(d)
        if gross<=1:frappe.throw('Select a quotation with selling total above 1.')
        for title,amount,percent in [('Amount discount',1,0),('Percentage discount',0,2),('Remove discount',0,0)]:
            q.discount_amount=amount;q.additional_discount_percentage=percent
            q.save()
            q.reload();d.reload()
            expected=net_selling(gross,q,d.currency)
            assert abs(q.net_total-expected)<.0005,(title,q.net_total,expected)
            assert abs(d.total_selling-expected)<.0005,(title,d.total_selling,expected)
            assert abs(d.custom_working_total_selling-expected)<.0005
            assert abs(d.custom_working_margin_percent-(expected-d.total_cost)/expected*100)<.001
            assert costs()==original_cost,'Purchase cost changed'
            revision=d.custom_dcs_revision_no
            q.save();d.reload()
            assert d.custom_dcs_revision_no==revision,'Repeated save duplicated a revision'
            results.append(dict(check=title,net_selling=expected,cost=d.total_cost,
                margin=d.custom_working_margin_percent,repeat_save='No duplicate revision'))
        assert counts=={dt:frappe.db.count(dt) for dt in counts},'Duplicate business document created'
        return dict(passed=True,quotation=q.name,dcs=d.name,checks=results,
            purchase_costs='Unchanged',duplicate_documents=0,all_changes='Rolled back')
    finally:
        frappe.db.rollback()


@frappe.whitelist()
def review(quotation):
    authorise()
    q=frappe.get_doc('Quotation',quotation);q.check_permission('read')
    import json
    frappe.respond_as_web_page('Discount verification','''<h2>Quotation discount regression check</h2>
    <p>Tests amount discount, percentage discount, discount removal and repeated saves.
    All test writes are rolled back. Purchase costs and existing business records remain unchanged.</p>
    <button onclick="this.disabled=true;frappe.call({method:'bsgroup.dcs.discount_verification.verify',type:'POST',args:{quotation:QUOTATION},callback:r=>{document.getElementById('result').textContent=JSON.stringify(r.message,null,2);this.disabled=false},error:()=>{this.disabled=false}})">Run reversible discount tests</button><pre id="result"></pre>'''.replace('QUOTATION',frappe.utils.escape_html(json.dumps(q.name))))
