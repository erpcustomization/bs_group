"""Reroute pending DCS approvals to the revision submitter's immediate manager."""
import frappe
from bsgroup.dcs.manager_approval import resolve_manager, queue_review, ROUTE_FIELDS
from bsgroup.dcs.governance import record_governance_event

def execute():
    frappe.reload_doc("bs_group","doctype","dcs_revision")
    frappe.reload_doc("bs_group","doctype","deal_cost_sheet")
    for dt,fields in {"Deal Cost Sheet":{"custom_approval_required":"Manager","custom_approval_state":"Pending Manager"},
                      "DCS Revision":{"approval_requirement":"Manager","approval_state":"Pending Manager"}}.items():
        for field,option in fields.items():
            for setter in frappe.get_all("Property Setter",filters={"doc_type":dt,"field_name":field,"property":"options"},fields=["name","value"]):
                if option not in (setter.value or "").split("\n"):
                    frappe.db.set_value("Property Setter",setter.name,"value",(setter.value or "")+"\n"+option)
    frappe.clear_cache()
    for name in frappe.get_all("Deal Cost Sheet", filters={"docstatus":1,
            "custom_approval_required":["in",["Managing Director","Blocked"]],
            "custom_approval_state":["not in",["Approved","Rejected","Returned for Rework"]]}, pluck="name"):
        sheet=frappe.get_doc("Deal Cost Sheet",name,for_update=True)
        if not sheet.custom_revision_reference or not frappe.db.exists("DCS Revision",sheet.custom_revision_reference):
            continue
        rev=frappe.get_doc("DCS Revision",sheet.custom_revision_reference)
        if rev.approval_state in ("Approved","Rejected","Returned for Rework"):
            continue
        if rev.get("approval_policy")=="Immediate Manager":
            continue
        route=resolve_manager(rev.changed_by)
        frappe.db.set_value("DCS Revision",rev.name,route,update_modified=False)
        req="Blocked" if sheet.custom_approval_required=="Blocked" else "Manager"
        state="Blocked" if req=="Blocked" else "Pending Manager"
        before_req=sheet.custom_approval_required;before_state=sheet.custom_approval_state
        frappe.db.set_value("Deal Cost Sheet",sheet.name,{"custom_approval_required":req,
            "custom_approval_state":state,"custom_approval_reason":"Immediate manager approval is required for the current commercial exception."},update_modified=True)
        # Keep original revision requirement and previous decisions intact.
        rev.reload()
        rev.approval_requirement=req
        queue_review(rev)
        record_governance_event(sheet.name,"DCS_APPROVAL_ROUTED_TO_MANAGER",
            action_label="Route pending approval to immediate manager",source_endpoint="dcs_manager_approval_migration",
            reason="Approval policy changed to the current revision submitter's immediate manager.",
            revision_no=rev.revision_no,revision_reference=rev.name,
            changes=[{"dt":"Deal Cost Sheet","dn":sheet.name,"field":"custom_approval_required","old":before_req,"new":req},
                     {"dt":"Deal Cost Sheet","dn":sheet.name,"field":"custom_approval_state","old":before_state,"new":state}]
                    +[{"dt":"DCS Revision","dn":rev.name,"field":key,"old":"","new":value} for key,value in route.items()])
