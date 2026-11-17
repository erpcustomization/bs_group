"""Read-only source Lead access for the exact assigned presales handoff."""
import frappe


def ensure_source_read(sheet, quotation, request):
    from bsgroup.dcs.presales_lineage import _same_deal
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_deal_identity
    if (quotation.get("quotation_to") != "Lead" or not quotation.get("party_name")
            or quotation.docstatus != 0 or sheet.docstatus != 1
            or quotation.custom_deal_cost_sheet != sheet.name
            or sheet.custom_quotation != quotation.name
            or request.custom_deal_cost_sheet != sheet.name
            or request.name != sheet.presales_request
            or request.docstatus == 2 or not _same_deal(sheet, request)
            or quotation_deal_identity(sheet, quotation)):
        return
    user = request.get("presales_owner") or request.get("owner")
    if not user or user in ("Guest", "Administrator"):
        return
    if not frappe.db.get_value("User", user, "enabled"):
        return
    if "BS Scoped Presales" not in frappe.get_roles(user):
        return
    if frappe.has_permission("Lead", "read", doc=quotation.party_name, user=user):
        return
    # Preserve existing grants rather than replacing or downgrading them.
    existing = frappe.db.get_value("DocShare", {"share_doctype": "Lead",
        "share_name": quotation.party_name, "user": user},
        ["write", "share", "submit"], as_dict=True) or {}
    from frappe.share import add
    add("Lead", quotation.party_name, user=user, read=1,
        write=existing.get("write", 0), share=existing.get("share", 0),
        submit=existing.get("submit", 0), notify=0,
        flags={"ignore_share_permission": True})
