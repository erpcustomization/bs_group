"""Test-only sales handover regression. Roll back all business/test-user changes."""
import json
import uuid
from io import BytesIO
from unittest.mock import patch
import frappe
from frappe.utils import add_days, nowdate, getdate
from frappe.utils.file_manager import save_file
from pypdf import PdfWriter

RESULTS=[]
COMPANY="Bits Secure IT Infrastructure LLC - AE"
SALES="zztest-bsp-handover-sales@example.com"
BUYER="zztest-bsp-handover-buyer@example.com"
MANAGER="zztest-bsp-handover-manager@example.com"

def check(label, value):
    assert value, label
    RESULTS.append(label)
    print("PASS",label,flush=True)

def blocked(label, function, text=None):
    point="handover_"+uuid.uuid4().hex
    frappe.db.savepoint(point)
    try:
        function()
    except (frappe.ValidationError, frappe.PermissionError) as error:
        frappe.db.rollback(save_point=point)
        if text: assert text.lower() in str(error).lower(),str(error)
        frappe.clear_messages()
        check(label,True)
    else:
        raise AssertionError("Expected rejection: "+label)

def sample_pdf(label="Customer PO"):
    stream=BytesIO()
    writer=PdfWriter()
    writer.add_blank_page(width=200+len(label),height=200)
    writer.add_metadata({"/Title":label})
    writer.write(stream)
    return stream.getvalue()

def run():
    from bsgroup.dcs import procurement as h
    from bsgroup import procurement as p
    from bsgroup.tests.dcs_fixtures import make_dcs,make_user
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation
    for user,roles in [(SALES,["Sales Manager"]),(BUYER,["Purchase User"]),
                       (MANAGER,["Purchase User","Purchase Manager"])]:
        make_user(user,roles)
    dcs=make_dcs(suffix="BSP-Handover-"+uuid.uuid4().hex[:6],submit=True,
                 company=COMPANY,currency="AED",deal_owner=SALES,
                 items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",qty=3,cost_rate=100,selling_rate=150),
                        dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",qty=2,cost_rate=200,selling_rate=300)])
    frappe.set_user(SALES)
    q=frappe.get_doc("Quotation",make_quotation(dcs.name))
    q.flags.ignore_mandatory=True
    q.flags.ignore_links=True
    q.custom_pipeline_stage="Sent"
    q.submit()
    def send():
        with patch.object(frappe,"get_print",return_value=sample_pdf("Quotation")),patch.object(h,"costing_pdf",return_value=sample_pdf("Costing")):
            return h.send_to_procurement(q.name,add_days(nowdate(),7),"Stores - AE")
    blocked("Unwon quotation cannot create a requisition",send)
    q.custom_pipeline_stage="Won"
    blocked("Won requires a customer PO",q.save)
    q.reload()
    source=save_file("ZZTEST-handover-customer-PO.pdf",sample_pdf(),"Quotation",q.name,
                     is_private=1,df="custom_customer_po")
    q.custom_customer_po=source.file_url
    q.custom_customer_po_reference="ZZTEST-HANDOVER-"+q.name
    q.custom_pipeline_stage="Won"
    q.save()
    dcs.reload()
    check("Won records the customer award without creating a PR",dcs.custom_award_state=="Awarded"
          and not q.custom_bsp_material_request)
    context=h.handover_context(q.name)
    check("Handover previews DCS costs, quantities and repeated Item rows",
          [(r["qty"],r["rate"]) for r in context["items"]]==[(3,100),(2,200)])
    blocked("Required-by date is required",lambda:h.send_to_procurement(q.name,warehouse="Stores - AE"))
    blocked("Past required-by date rejected",lambda:h.send_to_procurement(q.name,add_days(nowdate(),-1),"Stores - AE"))
    frappe.db.savepoint("stock_requirement")
    frappe.db.set_value("Item","ZZTEST-CLAUDE-DCS-ITEM-A","is_stock_item",1)
    blocked("Stock item handover requires a warehouse",
            lambda:h.send_to_procurement(q.name,add_days(nowdate(),7)), "warehouse")
    frappe.db.rollback(save_point="stock_requirement")
    wrong=frappe.db.get_value("Warehouse",{"company":["!=",COMPANY],"is_group":0,"disabled":0},"name")
    if wrong:
        blocked("Another company's warehouse is rejected",lambda:h.send_to_procurement(q.name,add_days(nowdate(),7),wrong))
    frappe.set_user(BUYER)
    blocked("Buying permission alone cannot send a sales award",send)
    frappe.set_user(SALES)
    with patch.object(frappe,"get_print",side_effect=RuntimeError("Synthetic print failure")):
        try: h.send_to_procurement(q.name,add_days(nowdate(),7),"Stores - AE")
        except RuntimeError: pass
        else: raise AssertionError("Expected print failure")
    check("Print failure leaves no requisition",not frappe.db.exists(p.MR,{"custom_bsp_key":h.handover_key(dcs)}))
    sent=send()
    mr=frappe.get_doc(p.MR,sent["name"])
    check("Sales sender creates a real draft standard Material Request",
          mr.material_request_type=="Purchase" and mr.docstatus==0 and mr.workflow_state=="Draft"
          and mr.owner==SALES and mr.custom_bsp_managed)
    check("Approved budget uses cost rates rather than selling prices",
          [(r.qty,r.rate) for r in mr.items]==[(3,100),(2,200)])
    check("Repeated Item rows retain distinct DCS row links",
          [r.custom_bsp_dcs_item for r in mr.items]==[r.name for r in dcs.items])
    check("Customer, company, quotation and DCS references copied",
          mr.custom_bsp_customer==q.party_name and mr.company==dcs.company
          and mr.custom_bsp_quotation==q.name and mr.custom_deal_cost_sheet==dcs.name
          and mr.custom_bsp_customer_po==q.custom_customer_po_reference)
    files=frappe.get_all("File",filters={"attached_to_doctype":p.MR,"attached_to_name":mr.name},
                         fields=["name","is_private","file_url"])
    if len(files)!=3:
        print("FILE_DIAGNOSTIC",files,p.parse(mr.custom_bsp_source_snapshot).get("files"),flush=True)
    check("Three private source documents are attached",len(files)==3 and all(f.is_private for f in files))
    check("Quotation points back to the standard requisition",
          frappe.db.get_value("Quotation",q.name,"custom_bsp_material_request")==mr.name)
    check("Sales sender has read-only access without a purchasing role",
          frappe.has_permission(p.MR,"read",doc=mr) and not frappe.has_permission(p.MR,"submit",doc=mr)
          and "Purchase User" not in frappe.get_roles(SALES))
    replay=send()
    check("Repeat send returns the same PR and creates no duplicate evidence",
          replay["already_sent"] and replay["name"]==mr.name
          and frappe.db.count(p.MR,{"custom_bsp_key":h.handover_key(dcs)})==1
          and frappe.db.count("File",{"attached_to_doctype":p.MR,"attached_to_name":mr.name})==3)
    check("Handover audit records one event",
          frappe.db.count("DCS Governance Event",{"dcs":dcs.name,"event_code":"DCS_PROCUREMENT_SENT"})==1)
    blocked("Sender cannot request PR approval without purchasing rights",
            lambda:p.request_action(mr.name,str(mr.modified),"Send for Approval"))
    frappe.set_user("Administrator")
    def alter():
        changed=frappe.get_doc(p.MR,mr.name)
        changed.items[0].rate=1
        changed.save()
    blocked("Source cost budget cannot be overwritten in the standard MR form",alter)
    for field, value in (("description","Unapproved replacement scope"),
                         ("item_name","Unapproved replacement name"),
                         ("schedule_date",getdate(add_days(nowdate(),20)))):
        def alter_source(field=field,value=value):
            changed=frappe.get_doc(p.MR,mr.name)
            changed.items[0].set(field,value)
            changed.save()
        blocked("G18 Handed-over line "+field+" remains frozen",alter_source)
    changed=frappe.get_doc(p.MR,mr.name)
    original_date=changed.schedule_date
    changed.schedule_date=getdate(add_days(nowdate(),21))
    changed.save()
    check("G18 Handed-over required date remains frozen",changed.reload().schedule_date==original_date)
    file=frappe.get_doc("File",files[0].name)
    blocked("Source evidence deletion is refused before blob removal",lambda:file.delete(ignore_permissions=True))
    check("Rejected deletion leaves the file content intact",bool(file.get_content()))
    def change_reference():
        quote=frappe.get_doc("Quotation",q.name)
        quote.custom_bsp_material_request=None
        quote.save()
    blocked("Quotation handover reference cannot be forged or removed",change_reference)
    r=p.get_request(mr.name)
    blocked("PO creation remains blocked until PR approval",
            lambda:p.create_order(mr.name,r["modified"],"A plus typing",{mr.items[0].name:1},str(uuid.uuid4())))
    frappe.set_user(BUYER)
    r=p.get_request(mr.name)
    r=p.request_action(r["id"],r["modified"],"Send for Approval")
    frappe.set_user(MANAGER)
    r=p.get_request(mr.name)
    r=p.request_action(r["id"],r["modified"],"Approve")
    check("Handed-over PR uses the normal approval workflow",r["approval"]=="Approved"
          and frappe.db.get_value(p.MR,mr.name,"docstatus")==1)
    po=p.create_order(mr.name,r["modified"],"A plus typing",{mr.items[0].name:1},str(uuid.uuid4()))
    check("Approved handover PR creates a native linked Purchase Order",po["request"]==mr.name
          and frappe.db.get_value("Purchase Order Item",{"parent":po["id"]},"material_request_item")==mr.items[0].name)
    point="source_changed";frappe.db.savepoint(point)
    frappe.db.set_value("Deal Cost Sheet",dcs.name,"custom_award_state","Not Awarded")
    blocked("Award reversal blocks further purchasing",
            lambda:p.create_order(mr.name,r["modified"],"A plus typing",{mr.items[1].name:1},str(uuid.uuid4())))
    frappe.db.rollback(save_point=point)
    p.order_action(po["id"],po["modified"],"Cancel","QC handover completed")
    r=p.get_request(mr.name)
    r=p.request_action(r["id"],r["modified"],"Cancel","QC handover completed")
    check("Handover PR cancels while preserving its quotation backlink",
          r["approval"]=="Cancelled" and frappe.db.get_value("Quotation",q.name,"custom_bsp_material_request")==mr.name)
    check("Legacy packet creation is not used",frappe.db.count("DCS Purchase Request",{"dcs":dcs.name})==0)
    print(json.dumps(dict(passed=len(RESULTS),tests=RESULTS),indent=2))

if __name__=="__main__":
    frappe.init(site="rel1-test.local",sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect();frappe.set_user("Administrator");frappe.flags.in_test=True
    try: run()
    finally: frappe.db.rollback();frappe.destroy()
