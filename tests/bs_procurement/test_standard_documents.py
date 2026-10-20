"""Integration regression against rel1-test.local. All test transactions roll back."""
import json
import uuid
import frappe
from frappe.utils import add_days, nowdate
from bsgroup.procurement_controls import PROCUREMENT_APPROVER

SITE="rel1-test.local"
COMPANY="Bits Secure IT Infrastructure LLC - AE"
BUYER="zztest-bsp-buyer@example.com"
MANAGER=PROCUREMENT_APPROVER
OTHER="zztest-bsp-noaccess@example.com"
RESULTS=[]


def check(name, condition):
    assert condition, name
    RESULTS.append(name)
    print("PASS",name,flush=True)


def blocked(name, function, message=None):
    savepoint="bsp_" + uuid.uuid4().hex
    frappe.db.savepoint(savepoint)
    try:
        function()
    except (frappe.ValidationError,frappe.PermissionError,frappe.DoesNotExistError) as error:
        frappe.db.rollback(save_point=savepoint)
        if message:
            assert message.lower() in str(error).lower(), (name,str(error))
        check(name,True)
        frappe.clear_messages()
    else:
        raise AssertionError("Expected rejection: "+name)


def new_request(p, count=4):
    return p.create_request(dict(key=str(uuid.uuid4()),company=COMPANY,
        title="ZZTEST BSP regression",schedule_date=add_days(nowdate(),10),
        warehouse="Stores - AE",items=[
            dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",qty=count,rate=100),
            dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-B",qty=2,rate=200)]))


def fresh(p,r):
    return p.get_request(r["id"])


def action(p,r,a,reason=""):
    r=fresh(p,r)
    return p.request_action(r["id"],r["modified"],a,reason)


def new_order(p,r,qty=2,supplier="A plus typing"):
    r=fresh(p,r)
    return p.create_order(r["id"],r["modified"],supplier,{r["items"][0]["sourceId"]:qty},str(uuid.uuid4()))


def payload(po, rate=90, exception=True):
    return dict(supplier=po["supplier"],group="Hardware",delivery=add_days(nowdate(),10),
                terms="30 days from invoice",
                items=[dict(row,rate=rate) for row in po["items"]],
                comparison=dict(exception=exception,explanation="QC single source exception",
                                quotes=[],selection_reason="",selected=None))


def po_action(p,po,a,reason=""):
    if a=="Send for Approval":
        from qc_fixtures import prepare_po
        prepare_po(po["id"])
    current=p.order_data(frappe.get_doc("Purchase Order",po["id"]))
    return p.order_action(current["id"],current["modified"],a,reason)


def run():
    from bsgroup import procurement as p
    for user,role in [(BUYER,"Purchase User"),(MANAGER,"Purchase Manager"),(OTHER,"Sales User")]:
        if not frappe.db.exists("User",user):
            frappe.get_doc(dict(doctype="User",email=user,first_name="ZZTEST BSP "+role,
                enabled=1,send_welcome_email=0,user_type="System User",
                roles=[dict(role=r) for r in (["Purchase User","Purchase Manager"] if role=="Purchase Manager" else [role])])).insert()
    frappe.set_user(BUYER)
    r=new_request(p)
    mr=frappe.get_doc("Material Request",r["id"])
    check("PR is a saved standard Material Request with purpose Purchase",
          mr.material_request_type=="Purchase" and mr.docstatus==0 and mr.custom_bsp_managed)
    check("Real requested items and budget survive reloading",fresh(p,r)["items"][0]["cost"]==100)
    blocked("PO creation before PR approval",lambda:new_order(p,r))
    r=action(p,r,"Send for Approval")
    blocked("Buyer cannot approve PR",lambda:action(p,r,"Approve"))
    def pending_edit():
        d=frappe.get_doc("Material Request",r["id"]);d.items[0].qty=99;d.save()
    blocked("Pending PR lines are locked through standard form",pending_edit)
    frappe.set_user(MANAGER)
    blocked("PR rejection requires reason",lambda:action(p,r,"Reject"))
    r=action(p,r,"Reject","Correct the requested quantities")
    check("PR rejection reason is saved",r["reason"]=="Correct the requested quantities")
    frappe.set_user(BUYER)
    r=action(p,r,"Send for Approval")
    frappe.set_user(MANAGER)
    r=action(p,r,"Approve")
    check("PR approval submits the standard Material Request",frappe.get_doc("Material Request",r["id"]).docstatus==1)
    check("Real manager identity remains in PR history",r["history"][-1]["actor"]==MANAGER)
    frappe.set_user(BUYER)
    po=new_order(p,r)
    standard=frappe.get_doc("Purchase Order",po["id"])
    check("PO uses standard source MR and MR-item links",standard.items[0].material_request==r["id"] and standard.items[0].material_request_item==r["items"][0]["sourceId"])
    check("Draft PO reserves quantity persistently",fresh(p,r)["items"][0]["available"]==2)
    blocked("Other PO cannot overallocate a reserved line",lambda:new_order(p,r,3),"unallocated")
    blocked("PO approval requires full commercial data",lambda:po_action(p,po,"Send for Approval"))
    po=p.save_order(po["id"],po["modified"],payload(po))
    blocked("Stale draft update rejected",lambda:p.save_order(po["id"],"2000-01-01",payload(po)))
    def direct_submit():
        d=frappe.get_doc("Purchase Order",po["id"]);d.submit()
    blocked("Standard-form submit cannot bypass BS approval",direct_submit)
    po=po_action(p,po,"Send for Approval")
    def pending_po_edit():
        d=frappe.get_doc("Purchase Order",po["id"]);d.items[0].rate=1;d.save()
    blocked("Pending PO cannot be edited in standard form",pending_po_edit,"locked")
    blocked("Buyer cannot approve own PO",lambda:po_action(p,po,"Approve"))
    frappe.set_user(MANAGER)
    blocked("PO rejection requires reason",lambda:po_action(p,po,"Reject"))
    po=po_action(p,po,"Reject","Please negotiate")
    frappe.set_user(BUYER)
    po=p.save_order(po["id"],po["modified"],payload(po,85))
    po=po_action(p,po,"Send for Approval")
    checks=[e for e in po["history"] if e["action"]=="Pending Approval"]
    check("Rejected/resubmitted PO retains both price snapshots",len(checks)==2 and checks[0]["snapshot"]["items"][0]["rate"]==90 and checks[1]["snapshot"]["items"][0]["rate"]==85)
    frappe.set_user(MANAGER)
    po=po_action(p,po,"Approve")
    check("PO approval submits the standard Purchase Order",frappe.get_doc("Purchase Order",po["id"]).docstatus==1)
    from bsgroup.dcs.quotation_control import update_child_qty_rate
    blocked("Standard Update Items endpoint cannot bypass approval",
            lambda:update_child_qty_rate("Purchase Order","[]",po["id"]),"protected")
    check("Standard MR ordered quantity and partial status update",fresh(p,r)["items"][0]["ordered"]==2 and fresh(p,r)["purchasing"]=="Partially ordered")
    blocked("Approved PO editable API is locked",lambda:p.save_order(po["id"],po["modified"],payload(po)))
    blocked("PR cannot cancel while linked PO remains active",lambda:action(p,r,"Cancel"))
    frappe.set_user(BUYER)
    po2=new_order(p,r,2,"A Rehman tech services")
    data=payload(po2,95,False)
    suppliers=["A Rehman tech services","A plus typing","A Z I TECHNOLOGY L.L.C"]
    files=[]
    for i,supplier in enumerate(suppliers):
        from qc_fixtures import make_file
        file=make_file(po2["id"],"QC supplier quotation "+str(i))
        files.append(file.name)
    data["comparison"]["quotes"]=[dict(supplier=s,file=f,rates={po2["items"][0]["sourceId"]:95+i})
                                  for i,(s,f) in enumerate(zip(suppliers,files))]
    data["comparison"]["selected"]=0
    po2=p.save_order(po2["id"],po2["modified"],data)
    po2=po_action(p,po2,"Send for Approval")
    check("Three actual supplier quotes and attachments accepted",len(po2["quotes"])==3 and not po2["na"])
    blocked("Quotation evidence cannot be deleted",lambda:frappe.delete_doc("File",files[0]))
    def detach_file():
        d=frappe.get_doc("File",files[0]);d.attached_to_doctype=None;d.attached_to_name=None;d.save()
    blocked("Quotation evidence cannot be detached",detach_file)
    frappe.set_user(MANAGER)
    po2=po_action(p,po2,"Approve")
    check("Two suppliers can purchase split quantity from one PR",fresh(p,r)["items"][0]["ordered"]==4)
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt, make_purchase_invoice
    receipt=make_purchase_receipt(po2["id"])
    frappe.set_user(BUYER)
    blocked("Invoice creation still requires accounting permissions",lambda:make_purchase_invoice(po2["id"]))
    frappe.set_user("Administrator")
    invoice=make_purchase_invoice(po2["id"])
    frappe.set_user(MANAGER)
    check("Standard Purchase Receipt mapping retains the PO link",receipt.items[0].purchase_order==po2["id"])
    check("Standard Purchase Invoice mapping retains the PO link",invoice.items[0].purchase_order==po2["id"])
    frappe.set_user(BUYER)
    r=fresh(p,r)
    third=p.create_order(r["id"],r["modified"],suppliers[0],{r["items"][1]["sourceId"]:2},str(uuid.uuid4()))
    third=p.save_order(third["id"],third["modified"],payload(third,190))
    third=po_action(p,third,"Send for Approval")
    frappe.set_user(MANAGER)
    third=po_action(p,third,"Approve")
    check("All submitted PO lines make standard MR fully ordered",fresh(p,r)["purchasing"]=="Fully ordered" and frappe.get_doc("Material Request",r["id"]).status=="Ordered")
    po2=po_action(p,po2,"Cancel","QC cancellation")
    check("Standard PO cancellation releases MR quantity",fresh(p,r)["items"][0]["available"]==2 and fresh(p,r)["items"][0]["ordered"]==2)
    amended=frappe.copy_doc(frappe.get_doc("Purchase Order",po2["id"]))
    amended.amended_from=po2["id"]
    amended.docstatus=0
    amended.insert()
    check("Standard PO amendment starts a new draft and preserves lineage",
          amended.custom_bsp_approval_state=="Draft" and amended.amended_from==po2["id"]
          and amended.custom_bsp_key!=frappe.get_doc("Purchase Order",po2["id"]).custom_bsp_key)
    p.order_action(amended.name,str(amended.modified),"Cancel","QC amendment check completed")
    frappe.set_user(BUYER)
    replacement=new_order(p,r,2)
    replacement=po_action(p,replacement,"Cancel","No longer needed")
    check("Withdrawing a draft releases reservation and preserves record",fresh(p,r)["items"][0]["available"]==2 and frappe.db.exists("Purchase Order",replacement["id"]))
    blocked("Withdrawn draft cannot be revived",lambda:p.save_order(replacement["id"],replacement["modified"],payload(replacement)))
    high=new_order(p,r,2)
    high=p.save_order(high["id"],high["modified"],payload(high,120))
    blocked("Above-budget line requires explanation",lambda:po_action(p,high,"Send for Approval"),"Explain")
    blocked("Standard print path cannot issue an unapproved BS PO",
            lambda:frappe.get_doc("Purchase Order",high["id"]).run_method("before_print",frappe._dict()),"Approve")
    bad=payload(high,90,False)
    bad["comparison"].update(quotes=[dict(supplier=suppliers[0],file=files[0],rates={high["items"][0]["sourceId"]:90})]*3,selected=0)
    high=p.save_order(high["id"],high["modified"],bad)
    blocked("Duplicate quote suppliers rejected",lambda:po_action(p,high,"Send for Approval"),"different suppliers")
    bad["comparison"]["quotes"]=[dict(supplier=s,file=f,rates={high["items"][0]["sourceId"]:90}) for s,f in zip(suppliers,files)]
    high=p.save_order(high["id"],high["modified"],bad)
    blocked("Quotations attached to another PO rejected",lambda:po_action(p,high,"Send for Approval"),"attachments on this")
    frappe.set_user(OTHER)
    blocked("User without buying access cannot read PR",lambda:p.get_request(r["id"]))
    blocked("User without buying access cannot change PO",lambda:po_action(p,po,"Reject","Unauthorized"))
    frappe.set_user("Administrator")
    check("Existing non-BS Purchase Orders remain unmodified",frappe.db.count("Purchase Order",{"custom_bsp_managed":0})==BASELINE_PO_COUNT)
    print(json.dumps({"passed":len(RESULTS),"tests":RESULTS},indent=2),flush=True)


if __name__=="__main__":
    frappe.init(site=SITE,sites_path="/home/bitssecureit/rel1-bench/sites");frappe.connect()
    frappe.set_user("Administrator");frappe.flags.in_test=True
    BASELINE_PO_COUNT=frappe.db.count("Purchase Order",{"custom_bsp_managed":0})
    try:
        run()
    finally:
        frappe.db.rollback()
        from qc_fixtures import cleanup_files
        cleanup_files()
        frappe.destroy()
