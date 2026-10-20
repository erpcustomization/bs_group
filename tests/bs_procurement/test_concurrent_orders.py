"""Two independent DB transactions compete for the same remaining PR quantity."""
import json
import multiprocessing
import uuid
import frappe
from frappe.utils import nowdate, add_days

SITE="rel1-test.local"


def connect():
    frappe.init(site=SITE,sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test=True


def worker(request, barrier, queue, supplier):
    connect()
    from bsgroup import procurement as p
    try:
        r=p.get_request(request)
        barrier.wait(timeout=30)
        po=p.create_order(r["id"],r["modified"],supplier,
                          {r["items"][0]["sourceId"]:3},str(uuid.uuid4()))
        frappe.db.commit()
        queue.put(dict(result="created",name=po["id"]))
    except Exception as error:
        frappe.db.rollback()
        queue.put(dict(result="blocked",message=str(error)))
    finally:
        frappe.destroy()


def main():
    connect()
    from bsgroup import procurement as p
    from bsgroup.procurement_controls import PROCUREMENT_APPROVER
    r=p.create_request(dict(key=str(uuid.uuid4()),title="ZZTEST BSP concurrency (completed)",
        company="Bits Secure IT Infrastructure LLC - AE",warehouse="Stores - AE",
        schedule_date=add_days(nowdate(),10),
        items=[dict(item_code="ZZTEST-CLAUDE-DCS-ITEM-A",qty=4,rate=100)]))
    for action in ["Send for Approval","Approve"]:
        if action=="Approve":
            frappe.set_user(PROCUREMENT_APPROVER)
        r=p.request_action(r["id"],r["modified"],action)
    frappe.db.commit()
    request=r["id"]
    frappe.destroy()
    context=multiprocessing.get_context("spawn")
    barrier=context.Barrier(2)
    queue=context.Queue()
    workers=[context.Process(target=worker,args=(request,barrier,queue,s))
             for s in ["A plus typing","A Rehman tech services"]]
    for proc in workers:proc.start()
    for proc in workers:proc.join(50)
    assert all(not proc.is_alive() and proc.exitcode==0 for proc in workers)
    results=[queue.get(timeout=5) for _ in workers]
    assert sum(x["result"]=="created" for x in results)==1,results
    assert any("unallocated" in x.get("message","") or "allocation changed" in x.get("message","") for x in results),results
    connect()
    r=p.get_request(request)
    assert r["items"][0]["reserved"]==3 and r["items"][0]["available"]==1,r
    winner=next(x["name"] for x in results if x["result"]=="created")
    po=p.order_data(frappe.get_doc("Purchase Order",winner))
    p.order_action(po["id"],po["modified"],"Cancel","QC concurrency test completed")
    r=p.get_request(request)
    p.request_action(r["id"],r["modified"],"Cancel","QC concurrency test completed")
    frappe.db.commit()
    frappe.destroy()
    print(json.dumps(dict(passed=True,request=request,workers=results,
                          cleanup="PO withdrawn; PR cancelled; audit retained"),indent=2))


if __name__=="__main__":
    main()
