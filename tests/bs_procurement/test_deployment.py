"""Test-site migration idempotency. Restore the temporary custom print format."""
import json
import runpy
import frappe

frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
assert frappe.local.site=="rel1-test.local"
checks=[]
def check(name,value):
    assert value,name
    checks.append(name)
    print("PASS",name,flush=True)
def transitions():
    name=frappe.db.get_value("Workflow",{"document_type":"Material Request","is_active":1})
    return [{k:r.get(k) for k in ("state","action","next_state","allowed","condition","allow_self_approval")}
            for r in frappe.get_doc("Workflow",name).transitions]
name="BS Procurement Purchase Order"
original=frappe.db.get_value("Print Format",name,"html")
try:
    from bsgroup.procurement_setup import execute
    before=transitions()
    execute()
    first=frappe.db.get_value("Print Format",name,"html")
    execute()
    check("G25 Repeated setup preserves shared workflow rules",transitions()==before)
    check("G25 Repeated setup leaves shipped print format stable",frappe.db.get_value("Print Format",name,"html")==first)
    custom=first+"\n<!-- QC temporary local customization -->"
    fmt=frappe.get_doc("Print Format",name)
    fmt.html=custom
    fmt.save()
    custom=fmt.reload().html
    frappe.db.commit()
    execute()
    check("G25 Migration preserves customized print format",frappe.db.get_value("Print Format",name,"html")==custom)
    hooks=frappe.get_hooks("after_migrate")
    check("G25 Procurement setup appended once to migration hooks",
          hooks.count("bsgroup.procurement_setup.execute")==1)
    combined=runpy.run_path(frappe.get_app_path("bsgroup","hooks.py"),
                           init_globals={"after_migrate":["qc.existing_migration"]})["after_migrate"]
    check("G25 Existing migration hooks survive composition",
          combined==["qc.existing_migration","bsgroup.procurement_setup.execute"])
    check("G07 Matching and overrun policies remain enabled",
          frappe.db.get_single_value("Buying Settings","po_required")=="Yes"
          and frappe.db.get_single_value("Buying Settings","pr_required")=="Yes"
          and frappe.db.get_single_value("BS Group Settings","cost_overrun_policy")=="Block")
    print(json.dumps(dict(passed=len(checks),tests=checks),indent=2),flush=True)
finally:
    frappe.db.rollback()
    fmt=frappe.get_doc("Print Format",name)
    fmt.html=original
    fmt.save()
    frappe.db.commit()
    frappe.clear_cache()
    frappe.destroy()
