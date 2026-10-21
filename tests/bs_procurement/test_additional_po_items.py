"""Rollback-only integration checks for additional PO items against an approved PR."""
import json
import sys
import uuid
from pathlib import Path

import frappe
from frappe.utils import nowdate

sys.path.insert(0, str(Path(__file__).parent))
from test_standard_documents import (
    check, blocked, RESULTS, new_request, new_order, action, payload,
    po_action, BUYER, MANAGER,
)
from qc_fixtures import make_file, cleanup_files


def run():
    from bsgroup import procurement as p, procurement_accounts as accounts
    from bsgroup.tests.dcs_fixtures import make_user
    from erpnext.buying.doctype.purchase_order.purchase_order import make_purchase_receipt

    make_user(BUYER, ["Purchase User"])
    make_user(MANAGER, ["Purchase User", "Purchase Manager", "Accounts Manager", "BS Procurement Approver"])
    extra = "ZZTEST-BSP-EXTRA-" + uuid.uuid4().hex[:10]
    frappe.get_doc(dict(doctype="Item", item_code=extra, item_name="Additional stock item",
        item_group="All Item Groups", stock_uom="Nos", is_stock_item=1,
        is_purchase_item=1, is_sales_item=0)).insert()
    frappe.set_user(BUYER)
    request = new_request(p)
    values = dict(item_code=extra, qty=2, rate=25, warehouse="Stores - AE")

    def only_extra():
        fresh = p.get_request(request["id"])
        return p.create_order(fresh["id"], fresh["modified"], "A plus typing", {},
                              str(uuid.uuid4()), [values])

    blocked("Additional-only PO still requires an approved PR", only_extra, "approved")
    request = action(p, request, "Send for Approval")
    frappe.set_user(MANAGER)
    request = action(p, request, "Approve")
    frappe.set_user(BUYER)
    before = frappe.get_doc("Material Request", request["id"]).as_dict()
    order = new_order(p, request, qty=1)
    order = p.add_order_item(order["id"], order["modified"], **values)
    added = next(r for r in order["items"] if r["additional"])
    check("Additional line is displayed with its own stable comparison key",
          added["sourceId"].startswith("additional:") and added["cost"] == 0)
    doc = frappe.get_doc("Purchase Order", order["id"])
    check("Additional item retains the PO header PR without inventing a PR row link",
          doc.custom_bsp_material_request == request["id"]
          and not doc.items[1].material_request and not doc.items[1].material_request_item)
    check("Additional stock item keeps its receiving warehouse", doc.items[1].warehouse == "Stores - AE")
    after = frappe.get_doc("Material Request", request["id"])
    check("Original PR scope and budget remain unchanged",
          [(r.item_code, r.qty, r.rate) for r in after.items]
          == [(r.item_code, r.qty, r.rate) for r in before["items"]])
    check("Additional quantity does not consume the original PR line",
          p.get_request(request["id"])["items"][0]["available"] == 3)
    blocked("Original requested items still use their PR quantity allocation",
            lambda: p.add_order_item(order["id"], order["modified"],
                item_code=request["items"][0]["item_code"], qty=20, rate=25, warehouse="Stores - AE"),
            "matching PR line")
    blocked("Additional stock item requires a warehouse",
            lambda: p.add_order_item(order["id"], order["modified"], item_code=extra, qty=1, rate=25),
            "warehouse")

    data = payload(order)
    data["items"] = order["items"]
    data["items"][0]["rate"] = 90
    order = p.save_order(order["id"], order["modified"], data)
    blocked("Additional item needs an explanation at PO approval submission",
            lambda: po_action(p, order, "Send for Approval"), "additional item")
    order = p.order_data(frappe.get_doc("Purchase Order", order["id"]))
    data = payload(order)
    data["items"] = order["items"]
    data["comparison"]["line_reasons"] = {added["sourceId"]: "Additional mounting supplies needed to complete installation."}
    suppliers = ["A plus typing", "A Rehman tech services", "A Z I TECHNOLOGY L.L.C"]
    data["comparison"].update(exception=False, selected=0,
        quotes=[dict(supplier=s, file=make_file(order["id"], "Additional item quote " + str(i)).name,
                     rates={r["sourceId"]: r["rate"] for r in order["items"]})
                for i, s in enumerate(suppliers)])
    del data["comparison"]["quotes"][1]["rates"][added["sourceId"]]
    order = p.save_order(order["id"], order["modified"], data)
    blocked("Three-quotation comparison includes additional item rates",
            lambda: po_action(p, order, "Send for Approval"), "Quotation line rate")
    order = p.order_data(frappe.get_doc("Purchase Order", order["id"]))
    data["comparison"]["quotes"][1]["rates"][added["sourceId"]] = 25
    order = p.save_order(order["id"], order["modified"], data)
    order = po_action(p, order, "Send for Approval")
    check("Mixed PR and additional items reach Pending Approval", order["status"] == "Pending Approval")
    blocked("Pending additional lines remain locked",
            lambda: p.add_order_item(order["id"], order["modified"], **values), "draft or rejected")
    frappe.set_user(MANAGER)
    order = po_action(p, order, "Approve")
    check("Mohan can approve the mixed PO", order["status"] == "Approved" and order["docstatus"] == 1)
    receipt = make_purchase_receipt(order["id"])
    receipt.posting_date = nowdate()
    receipt.insert()
    receipt.submit()
    check("Additional stock item is receivable against its approved PO",
          any(r.item_code == extra and r.purchase_order == order["id"] for r in receipt.items))
    invoice = accounts.prepare_payment_order("Purchase Receipt", receipt.name)
    check("Payment Order preparation includes the additional received item",
          any(r.item_code == extra and r.purchase_order == order["id"]
              and r.purchase_receipt == receipt.name for r in invoice.items))
    frappe.set_user(BUYER)
    other = only_extra()
    check("PO can contain only additional items against the approved PR",
          other["request"] == request["id"] and len(other["items"]) == 1 and other["items"][0]["additional"])
    check("Additional-only PO does not allocate original PR quantities",
          p.get_request(request["id"])["items"][0]["available"] == 3)
    print(json.dumps({"passed": len(RESULTS), "tests": RESULTS}, indent=2))


if __name__ == "__main__":
    frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
    frappe.connect()
    frappe.set_user("Administrator")
    frappe.flags.in_test = True
    try:
        run()
    finally:
        cleanup_files()
        frappe.db.rollback()
        frappe.destroy()
