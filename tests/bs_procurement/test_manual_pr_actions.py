"""Manual draft actions; all records roll back."""
import sys, uuid
from pathlib import Path
import frappe
sys.path.insert(0,str(Path(__file__).parent))
from test_standard_documents import new_request, action, check, blocked, BUYER, MANAGER
from qc_fixtures import cleanup_files

def run():
 from bsgroup import procurement as p
 from bsgroup.tests.dcs_fixtures import make_user
 make_user(BUYER,["Purchase User"])
 make_user(MANAGER,["Purchase Manager","Purchase User","BS Procurement Approver"])
 frappe.set_user("Administrator")
 original=new_request(p)
 check("Draft PR exposes edit, clone and delete",all(original[k] for k in ("canEdit","canClone","canDelete")))
 doc=frappe.get_doc("Material Request",original["id"])
 doc.items[0].description="QC custom equipment description"
 doc.items[0].qty=3
 doc.save()
 check("Draft quantities can be edited",p.get_request(doc.name)["items"][0]["qty"]==3)
 key=str(uuid.uuid4())
 copied=p.clone_request(doc.name,key)
 copy=frappe.get_doc("Material Request",copied["id"])
 check("Clone is a distinct manual draft",copy.name!=doc.name and copied["approval"]=="Draft" and not copy.docstatus)
 check("Clone preserves quantities, descriptions and budget",[(r.qty,r.description,r.rate,r.warehouse) for r in doc.items]==[(r.qty,r.description,r.rate,r.warehouse) for r in copy.items])
 check("Clone has fresh evidence and approval",not copied["supporting"]["exception"] and len(copied["history"])==1)
 check("Clone retries do not duplicate",p.clone_request(doc.name,key)["id"]==copy.name)
 from qc_fixtures import pdf_content, FILES
 file=frappe.get_doc(dict(doctype="File",file_name="ZZTEST-CLONE-"+uuid.uuid4().hex+".pdf",
  content=pdf_content("QC draft delete"),is_private=1,attached_to_doctype="Material Request",attached_to_name=copy.name)).insert()
 FILES.append(file.get_full_path())
 p.save_request_evidence(copy.name,str(copy.modified),dict(kind="direct_invoice",exception=True,
  explanation="QC utility invoice deletion check",invoices=[dict(file=file.name)]))
 copy.reload()
 p.delete_request(copy.name,str(copy.modified))
 check("Manual draft with supporting attachment can be deleted",not frappe.db.exists("Material Request",copy.name))
 current=action(p,original,"Send for Approval")
 check("Pending PR hides edit and delete",not current["canEdit"] and not current["canDelete"])
 blocked("Pending PR deletion rejected",lambda:p.delete_request(current["id"],current["modified"]))
 blocked("Direct pending PR deletion rejected",lambda:frappe.delete_doc("Material Request",current["id"]))
 frappe.set_user(MANAGER)
 approved=action(p,current,"Approve")
 blocked("Approved PR deletion rejected",lambda:p.delete_request(approved["id"],approved["modified"]))
 approved_copy=p.clone_request(approved["id"],str(uuid.uuid4()))
 check("Approved manual PR clones back to Draft",approved_copy["approval"]=="Draft")
 frappe.set_user("Administrator")
 sourced=frappe.get_all("Material Request",filters={"custom_bsp_managed":1,"custom_bsp_source_snapshot":["is","set"]},pluck="name",limit=1)
 if sourced:
  blocked("Sales PR cannot be cloned",lambda:p.clone_request(sourced[0],str(uuid.uuid4())))
  src=p.get_request(sourced[0])
  blocked("Sales PR cannot be deleted",lambda:p.delete_request(src["id"],src["modified"]))

if __name__=="__main__":
 frappe.init(site="rel1-test.local",sites_path="/home/bitssecureit/rel1-bench/sites");frappe.connect();frappe.set_user("Administrator");frappe.flags.in_test=True
 try:run()
 finally:
  cleanup_files();frappe.db.rollback();frappe.destroy()
