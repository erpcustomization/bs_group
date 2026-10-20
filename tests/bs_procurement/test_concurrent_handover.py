"""Two independent sales sends must create exactly one standard Material Request."""
import json
import multiprocessing
import uuid
from unittest.mock import patch
import frappe
from frappe.utils import add_days,nowdate
from frappe.utils.file_manager import save_file
from test_sales_handover import sample_pdf

def connect():
    frappe.init(site="rel1-test.local",sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect();frappe.set_user("Administrator");frappe.flags.in_test=True

def worker(quotation,barrier,queue):
    connect()
    from bsgroup.dcs import procurement as h
    try:
        barrier.wait(timeout=30)
        with patch.object(frappe,"get_print",return_value=sample_pdf("Quotation")),patch.object(h,"costing_pdf",return_value=sample_pdf("Costing")):
            result=h.send_to_procurement(quotation,add_days(nowdate(),7),"Stores - AE")
        frappe.db.commit()
        queue.put(dict(result="saved",**result))
    except Exception as error:
        frappe.db.rollback()
        queue.put(dict(result="blocked",message=str(error)))
    finally:frappe.destroy()

def main():
    connect()
    from bsgroup.tests.dcs_fixtures import make_dcs
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import make_quotation
    from bsgroup.dcs import procurement as h
    from bsgroup import procurement as p
    dcs=make_dcs(suffix="BSP-Send-Race-"+uuid.uuid4().hex[:6],submit=True,
        company="Bits Secure IT Infrastructure LLC - AE",currency="AED",
        items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",qty=2,cost_rate=100,selling_rate=150)])
    q=frappe.get_doc("Quotation",make_quotation(dcs.name))
    q.flags.ignore_mandatory=True;q.flags.ignore_links=True;q.custom_pipeline_stage="Sent";q.submit()
    f=save_file("ZZTEST-concurrent-handover-PO.pdf",sample_pdf(),"Quotation",q.name,is_private=1,df="custom_customer_po")
    q.custom_customer_po=f.file_url;q.custom_customer_po_reference="ZZTEST-CONCURRENT-SEND"
    q.custom_pipeline_stage="Won";q.save();dcs.reload()
    key=h.handover_key(dcs);quote=q.name
    frappe.db.commit();frappe.destroy()
    context=multiprocessing.get_context("spawn");barrier=context.Barrier(2);queue=context.Queue()
    workers=[context.Process(target=worker,args=(quote,barrier,queue)) for _ in range(2)]
    for proc in workers:proc.start()
    for proc in workers:proc.join(55)
    assert all(not proc.is_alive() and proc.exitcode==0 for proc in workers)
    outcomes=[queue.get(timeout=5) for _ in workers]
    assert any(x["result"]=="saved" for x in outcomes),outcomes
    assert sum(x["result"]=="saved" and not x["already_sent"] for x in outcomes)==1,outcomes
    connect()
    names=frappe.get_all(p.MR,filters={"custom_bsp_key":key},pluck="name")
    assert len(names)==1,names
    mr=names[0]
    assert frappe.db.count("File",{"attached_to_doctype":p.MR,"attached_to_name":mr})==3
    assert frappe.db.count("DCS Governance Event",{"dcs":dcs.name,"event_code":"DCS_PROCUREMENT_SENT"})==1
    # A retry after both transactions completed must resolve to the same record.
    replay=h.send_to_procurement(quote,add_days(nowdate(),7),"Stores - AE")
    assert replay["already_sent"] and replay["name"]==mr
    r=p.get_request(mr)
    for action in ("Send for Approval","Approve","Cancel"):
        r=p.request_action(r["id"],r["modified"],action,"QC concurrent handover completed" if action=="Cancel" else "")
    frappe.db.commit();frappe.destroy()
    print(json.dumps(dict(passed=True,quotation=quote,request=mr,workers=outcomes,
                          cleanup="PR cancelled; source and evidence retained"),indent=2))

if __name__=="__main__":main()
