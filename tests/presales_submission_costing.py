from pathlib import Path
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / "bsgroup"))
frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
try:
    rows = frappe.get_all("Presales Request", filters={"docstatus":0}, fields=["name","opportunity","party_type","party","company"])
    row = next(r for r in rows if r.opportunity and r.party and frappe.db.exists(r.party_type, r.party) and not frappe.db.exists("Deal Cost Sheet", {"opportunity":r.opportunity}))
    pre = frappe.get_doc("Presales Request", row.name)
    for s in frappe.get_all("Site Survey Request", filters={"opportunity":row.opportunity}, pluck="name"):
        frappe.db.set_value("Site Survey Request", s, "status", "Completed")
    pre.site_visit_required = 0
    pre.flags.ignore_mandatory = True
    pre.submit()
    sheets = frappe.get_all("Deal Cost Sheet", filters={"opportunity":row.opportunity}, fields=["name","docstatus","presales_request","party","company"])
    assert len(sheets) == 1 and sheets[0].docstatus == 0
    assert sheets[0].presales_request == pre.name and sheets[0].party == pre.party and sheets[0].company == pre.company
    pre.on_submit()
    assert frappe.db.count("Deal Cost Sheet", {"opportunity":row.opportunity}) == 1
    from bsgroup.opportunity_progress import resolve_many
    opp = frappe.get_doc("Opportunity", row.opportunity)
    assert resolve_many([opp])[opp.name]["label"] == "Deal Cost Sheet in Progress"
    print("PASS real Presales submit creates linked draft DCS, repeat is idempotent, Opportunity shows costing in progress", flush=True)
finally:
    frappe.db.rollback()
    frappe.destroy()

