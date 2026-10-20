"""Adversarial regressions for QC G-01..G-25. All business data rolls back."""
import hashlib
import json
import uuid
from pathlib import Path
import frappe
from frappe.utils import add_days, nowdate
from frappe.model.workflow import apply_workflow
from test_standard_documents import check, blocked, RESULTS, new_request, new_order, payload, action, po_action, BUYER, MANAGER, COMPANY
from qc_fixtures import MANAGER2, prepare_po, make_file, pdf_content, cleanup_files

ACCU="zztest-gap-accounts@example.com"
ACCM1="zztest-gap-accounts-manager1@example.com"
ACCM2="zztest-gap-accounts-manager2@example.com"


def approved_pr(p, item=None):
    frappe.set_user(BUYER)
    r=new_request(p) if not item else p.create_request(dict(key=str(uuid.uuid4()),company=COMPANY,
        supporting=dict(exception=True,explanation="QC single-source controls fixture."),
        title="ZZTEST gaps",schedule_date=add_days(nowdate(),7),warehouse="Stores - AE",
        items=[dict(item_code=item,qty=4,rate=100)]))
    r=action(p,r,"Send for Approval")
    frappe.set_user(MANAGER)
    return action(p,r,"Approve")


def ready_po(p,r,qty=2):
    frappe.set_user(BUYER)
    po=new_order(p,r,qty)
    po=p.save_order(po["id"],po["modified"],payload(po))
    prepare_po(po["id"])
    return p.order_data(frappe.get_doc("Purchase Order",po["id"]))


def invoice_fields(doc):
    doc.bill_no="ZZTEST-GAP-"+uuid.uuid4().hex
    doc.bill_date=doc.posting_date=doc.due_date=nowdate()
    return doc


def run():
    from bsgroup import procurement as p, procurement_accounts as a
    from bsgroup.tests.dcs_fixtures import make_user
    for user,roles in ((BUYER,["Purchase User"]),(MANAGER,["Purchase User","Purchase Manager"]),
        (MANAGER2,["Purchase User","Purchase Manager"]),(ACCU,["Accounts User"]),
        (ACCM1,["Accounts User","Accounts Manager"]),(ACCM2,["Accounts User","Accounts Manager"])):
        make_user(user,roles)
    frappe.set_user(BUYER)
    blocked("G06 Manual PR cannot claim quotation and invented DCS budget",lambda:p.create_request(
        dict(key=str(uuid.uuid4()),company=COMPANY,quotation="SAL-QTN-2026-01213",
             items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",qty=1,rate=999999)])),"Send to Procurement")
    plain=frappe.get_doc(dict(doctype="Material Request",company=COMPANY,material_request_type="Purchase",
        schedule_date=add_days(nowdate(),7),items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",
        qty=1,warehouse="Stores - AE",schedule_date=add_days(nowdate(),7))])).insert()
    def convert():
        d=frappe.get_doc("Material Request",plain.name);d.custom_bsp_managed=1;d.save()
    blocked("G11 Ordinary MR cannot be converted through standard form",convert,"cannot be converted")
    r=new_request(p)
    frappe.db.set_value("Material Request",r["id"],"owner",ACCU,update_modified=False)
    frappe.set_user(MANAGER2)
    r=action(p,r,"Send for Approval")
    blocked("G02 Non-designated PR sender cannot approve Sales-owned PR",lambda:action(p,r,"Approve"),"Only Mohan")
    frappe.set_user(MANAGER)
    r=action(p,r,"Approve")
    po=ready_po(p,r)
    frappe.set_user(MANAGER2)
    po=p.save_order(po["id"],po["modified"],payload(po,95))
    po=po_action(p,po,"Send for Approval")
    blocked("G01 Non-designated PO preparer cannot approve buyer-owned PO",lambda:po_action(p,po,"Approve"),"Only Mohan")
    check("G01 UI hides approval from other managers",not p.order_data(frappe.get_doc("Purchase Order",po["id"]))["canApprove"])
    frappe.set_user(MANAGER)
    po=po_action(p,po,"Approve")
    check("G01 Mohan can approve",po["docstatus"]==1)
    frappe.set_user("Administrator")
    admin_r=new_request(p)
    admin_r=action(p,admin_r,"Send for Approval")
    blocked("G15 Administrator cannot substitute for Mohan",lambda:action(p,admin_r,"Approve"),"Only Mohan")
    from bsgroup.procurement_controls import approval_allowed
    for doctype in ("Purchase Order","Purchase Invoice"):
        owned=frappe.new_doc(doctype)
        owned.owner="Administrator"
        owned.custom_bsp_managed=1
        blocked("G15 Administrator approval guard also covers "+doctype,
                lambda:approval_allowed(owned,throw=True),
                "Only Mohan" if doctype=="Purchase Order" else "different authorised")
    # Supplier invoice maker-checker must also catch an editor who is not owner.
    invoice=invoice_fields(a.prepare_payment_order("Purchase Order",po["id"]))
    frappe.set_user(ACCU);invoice.insert()
    frappe.set_user(ACCM1)
    invoice.reload();invoice.bill_no+="-prepared";invoice.save()
    invoice=apply_workflow(invoice,"Send for Approval")
    blocked("G03 Invoice preparer cannot approve another user's invoice",
            lambda:a.invoice_action(invoice.name,str(invoice.modified),"Approve"),"different authorised")
    frappe.set_user(ACCM2)
    a.invoice_action(invoice.name,str(invoice.modified),"Approve")
    check("G03 Independent accounts manager approves vendor invoice",invoice.reload().docstatus==1)
    # Separate unbilled PO for cancellation, closed/reopen, UOM and FX probes.
    r2=approved_pr(p)
    po2=ready_po(p,r2)
    blocked("G21 API withdrawal needs a reason",
            lambda:p.order_action(po2["id"],po2["modified"],"Cancel"),"reason")
    # Per-line reasons and supplier completeness are enforced at submission.
    high=payload(po2,120);high["comparison"]["selection_reason"]="."
    po2=p.save_order(po2["id"],po2["modified"],high)
    blocked("G10 Global dot reason cannot justify line variance",
            lambda:p.order_action(po2["id"],po2["modified"],"Send for Approval"),"15 characters")
    high["comparison"]["line_reasons"]={po2["items"][0]["sourceId"]:"Confirmed additional freight for this specific line."}
    po2=p.save_order(po2["id"],po2["modified"],high)
    d=frappe.get_doc("Purchase Order",po2["id"]);d.contact_person=d.contact_display=None;d.save()
    blocked("G13 Missing supplier contact blocks approval request",
            lambda:po_action_without_fixture(p,po2["id"],"Send for Approval"),"contact")
    prepare_po(po2["id"])
    d=frappe.get_doc("Purchase Order",po2["id"]);d.taxes_and_charges=None;d.save()
    blocked("G13 Missing explicit tax treatment blocks approval request",
            lambda:po_action_without_fixture(p,po2["id"],"Send for Approval"),"tax")
    prepare_po(po2["id"])
    po2=po_action_without_fixture(p,po2["id"],"Send for Approval")
    for label,edit in (
        ("description",lambda d:setattr(d.items[0],"description","Changed pending scope")),
        ("item name",lambda d:setattr(d.items[0],"item_name","Changed pending name")),
        ("contact",lambda d:setattr(d,"contact_email","different@example.com")),
        ("tax template",lambda d:setattr(d,"taxes_and_charges","UAE VAT 5% Input - AE - AE")),
    ):
        def change():
            d=frappe.get_doc("Purchase Order",po2["id"]);edit(d);d.save()
        blocked("G08 Pending PO locks "+label,change,"locked")
    d=frappe.get_doc("Purchase Order",po2["id"])
    supplier_name=d.supplier_name
    d.supplier_name="Different supplier wording"
    d.save()
    check("G08 Supplier name cannot be replaced on pending PO",d.reload().supplier_name==supplier_name)
    frappe.set_user(MANAGER);po2=po_action(p,po2,"Approve")
    html=frappe.get_print("Purchase Order",po2["id"],print_format="BS Procurement Purchase Order",no_letterhead=1)
    check("G13 PDF includes approver and tax registration fields",MANAGER in html and "Company tax registration" in html)
    from erpnext.buying.doctype.purchase_order.purchase_order import update_status
    update_status("Closed",po2["id"])
    check("G12 Closing unreceived PO releases quantity",p.get_request(r2["id"])["items"][0]["available"]==4)
    frappe.set_user(BUYER)
    replacement=new_order(p,r2,4)
    frappe.set_user(MANAGER)
    blocked("G12 Reopening after re-sourcing cannot overallocate",lambda:update_status("Submitted",po2["id"]),"unallocated")
    frappe.set_user(BUYER);replacement=po_action(p,replacement,"Cancel","QC closed-order re-sourcing test complete")
    check("G14 Withdrawn draft is distinctly labelled",replacement["erpStatus"]=="Withdrawn")
    # Unique physical evidence checks, plus the ordinary PO deletion regression.
    r3=approved_pr(p);po3=ready_po(p,r3)
    suppliers=["A plus typing","A Rehman tech services","A Z I TECHNOLOGY L.L.C"]
    duplicate=pdf_content("Identical quotation "+uuid.uuid4().hex)
    files=[make_file(po3["id"],str(i),duplicate) for i in range(3)]
    data=payload(po3,90,False)
    data["comparison"].update(selected=0,quotes=[dict(supplier=s,file=f.name,
        rates={po3["items"][0]["sourceId"]:90+i}) for i,(s,f) in enumerate(zip(suppliers,files))])
    po3=p.save_order(po3["id"],po3["modified"],data)
    blocked("G09 Identical documents cannot count as three quotations",
        lambda:po_action_without_fixture(p,po3["id"],"Send for Approval"),"duplicate content")
    files=[make_file(po3["id"],"Supplier "+str(i)) for i in range(3)]
    for q,f in zip(data["comparison"]["quotes"],files):q["file"]=f.name
    po3=p.save_order(po3["id"],po3["modified"],data)
    po3=po_action_without_fixture(p,po3["id"],"Send for Approval")
    path=Path(files[0].get_full_path());before=hashlib.sha256(path.read_bytes()).hexdigest()
    blocked("G04 Quotation deletion rejected",lambda:frappe.delete_doc("File",files[0].name),"procurement evidence")
    check("G04 Blocked deletion preserves exact file bytes",path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==before)
    def publish():
        f=frappe.get_doc("File",files[0].name);f.is_private=0;f.save()
    blocked("G04 Making quotation public is rejected before moving it",publish,"procurement evidence")
    check("G04 Privacy rejection preserves original private file",path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==before)
    plain_po=frappe.get_doc(dict(doctype="Purchase Order",company=COMPANY,supplier=suppliers[0],
        schedule_date=add_days(nowdate(),7),items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",
        qty=1,rate=10,warehouse="Stores - AE",schedule_date=add_days(nowdate(),7))])).insert()
    ordinary_file=make_file(plain_po.name,"Ordinary PO")
    frappe.delete_doc("Purchase Order",plain_po.name)
    check("G05 Ordinary draft PO with attachment can be deleted",not frappe.db.exists("Purchase Order",plain_po.name))
    # Currency and alternate buying UOM are compared against stock-equivalent budget.
    frappe.set_user("Administrator")
    item=frappe.copy_doc(frappe.get_doc("Item","ZZTEST-CLAUDE-DCS-ITEM-A"))
    item.item_code=item.item_name="ZZTEST-GAP-UOM-"+uuid.uuid4().hex[:8]
    item.append("uoms",dict(uom="Box",conversion_factor=2));item.insert()
    rx=approved_pr(p,item.name);px=ready_po(p,rx,4)
    data=payload(px,40);data.update(currency="USD",conversionRate=3.6725)
    data["items"][0].update(qty=2,uom="Box")
    px=p.save_order(px["id"],px["modified"],data)
    px=po_action(p,px,"Send for Approval")
    frappe.set_user(MANAGER);px=po_action(p,px,"Approve")
    check("G24 Foreign-currency PO and Box UOM retain stock allocation",
          px["currency"]=="USD" and px["items"][0]["uom"]=="Box"
          and p.get_request(rx["id"])["items"][0]["ordered"]==4)
    limits(p,a)
    from bsgroup.procurement_setup import enforce_policy
    enforce_policy()
    check("G07 Deployment policy restores required controls",
          frappe.db.get_single_value("Buying Settings","po_required")=="Yes"
          and frappe.db.get_single_value("Buying Settings","pr_required")=="Yes"
          and frappe.db.get_single_value("BS Group Settings","cost_overrun_policy")=="Block")
    # Pagination query must find a PO even when only one unrelated newest PR is loaded.
    frappe.set_user(BUYER)
    check("G23 PO search works independently of loaded requisition page",
          any(row["id"]==po3["id"] for row in p.get_orders(search=po3["id"])["orders"]))
    check("G17 PR summaries do not include nested PO payloads",all(not r["orders"] for r in p.get_requests(page_length=2)["requests"]))
    from unittest.mock import patch
    # Warm permission and metadata caches, then count real SQL calls by page size.
    p.get_requests(page_length=50)
    def queries(size):
        with patch.object(frappe.db,"sql",wraps=frappe.db.sql) as sql:
            p.get_requests(page_length=size)
            return sql.call_count
    one,many=queries(1),queries(50)
    check("G17 PR list queries stay bounded as rows increase",many<=one+2)
    print("QUERY_COUNTS",json.dumps(dict(one_row=one,fifty_rows=many)),flush=True)
    from bsgroup.bs_group.page.bs_procurement import bs_procurement as old
    check("G16 Sample PO PDF endpoints removed",
          not hasattr(old,"download_sample_pdf") and not hasattr(old,"fetch_sample_pdf"))
    print(json.dumps(dict(passed=len(RESULTS),tests=RESULTS),indent=2),flush=True)


def po_action_without_fixture(p,name,action):
    d=frappe.get_doc("Purchase Order",name)
    return p.order_action(d.name,str(d.modified),action)


def limits(p,a):
    frappe.set_user("Administrator")
    item=frappe.copy_doc(frappe.get_doc("Item","ZZTEST-CLAUDE-DCS-ITEM-A"))
    item.item_code=item.item_name="ZZTEST-GAP-STOCK-"+uuid.uuid4().hex[:8]
    item.is_stock_item=1;item.valuation_rate=100;item.insert()
    r=approved_pr(p,item.name);po=ready_po(p,r)
    po=po_action(p,po,"Send for Approval")
    frappe.set_user(MANAGER);po=po_action(p,po,"Approve")
    frappe.set_user("Administrator")
    for key,value in dict(po_required="No",pr_required="No",maintain_same_rate=0).items():
        frappe.db.set_single_value("Buying Settings",key,value)
    frappe.db.set_single_value("Accounts Settings","over_billing_allowance",100)
    frappe.db.set_single_value("Stock Settings","over_delivery_receipt_allowance",100)
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_invoice,make_purchase_receipt
    from erpnext.stock.doctype.purchase_receipt.purchase_receipt import make_purchase_invoice as receipt_invoice
    blocked("G07 Stock invoice requires receipt even with global checks off",
            lambda:invoice_fields(make_purchase_invoice(po["id"])).insert(),"Receipt")
    def over_receive():
        d=make_purchase_receipt(po["id"]);d.items[0].qty=d.items[0].received_qty=3;d.insert()
    blocked("G07 App blocks over-receipt despite 100 percent allowance",over_receive,"quantity")
    d=make_purchase_receipt(po["id"])
    d.items[0].conversion_factor=0.5
    d.insert()
    check("G07 Invented receiving conversion cannot persist",d.reload().items[0].conversion_factor==1)
    receipt=make_purchase_receipt(po["id"]);receipt.items[0].qty=receipt.items[0].received_qty=1
    receipt.insert();receipt.submit()
    def bad_invoice(kind):
        d=invoice_fields(receipt_invoice(receipt.name))
        if kind=="rate":d.items[0].rate=100
        if kind=="quantity":d.items[0].qty=2
        if kind=="unmatched":
            row=frappe.copy_doc(d.items[0])
            for field in ("purchase_order","po_detail","purchase_receipt","pr_detail","material_request","material_request_item"):
                row.set(field,None)
            d.append("items",row)
        d.insert()
    blocked("G07 App blocks invoice rate above approved PO",lambda:bad_invoice("rate"),"rate")
    blocked("G07 App blocks invoice quantity above accepted receipt",lambda:bad_invoice("quantity"),"quantity")
    blocked("G07 Mixed invoice cannot hide an unmatched line",lambda:bad_invoice("unmatched"),"Every line")
    from erpnext.buying.doctype.purchase_order.purchase_order import update_status
    update_status("Closed",po["id"])
    check("G12 Partially received closed PO retains received quantity only",
          p.get_request(r["id"])["items"][0]["available"]==3)


if __name__=="__main__":
    frappe.init(site="rel1-test.local",sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect();frappe.set_user("Administrator");frappe.flags.in_test=True
    try:run()
    finally:
        frappe.db.rollback();cleanup_files();frappe.destroy()
        print("QC gap transactions rolled back.",flush=True)
