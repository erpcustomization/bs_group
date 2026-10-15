"""Install portable DCS count cards and preserve existing workspace content."""
import json
import frappe

CARDS = ("Open DCS Handover Blockers", "DCS Awarded Pending Delivery Release",
         "DCS PO Reconciliation Mismatch")

def ensure_components():
    definitions = (
        (CARDS[0], "DCS Handover Condition", "#e0a336", [
            ["DCS Handover Condition", "category", "=", "Blocker"],
            ["DCS Handover Condition", "state", "=", "Open"],
            ["DCS Handover Condition", "dcs", "not like", "%ZZTEST%"],
            ["DCS Handover Condition", "dcs", "not like", "%ZZ-TEST%"]]),
        (CARDS[1], "Deal Cost Sheet", "#4287f5", [
            ["Deal Cost Sheet", "custom_award_state", "=", "Awarded"],
            ["Deal Cost Sheet", "custom_delivery_release_state", "in", ["", "Pending", "Blocked", "On Hold"]],
            ["Deal Cost Sheet", "docstatus", "=", 1],
            ["Deal Cost Sheet", "name", "not like", "%ZZTEST%"],
            ["Deal Cost Sheet", "name", "not like", "%ZZ-TEST%"]]),
        (CARDS[2], "Deal Cost Sheet", "#e03636", [
            ["Deal Cost Sheet", "custom_po_recon_state", "=", "Mismatch"],
            ["Deal Cost Sheet", "docstatus", "=", 1],
            ["Deal Cost Sheet", "name", "not like", "%ZZTEST%"],
            ["Deal Cost Sheet", "name", "not like", "%ZZ-TEST%"]]),
    )
    for name, doctype, color, filters in definitions:
        if not frappe.db.exists("Number Card", name):
            frappe.get_doc({"doctype": "Number Card", "name": name, "label": name,
                "type": "Document Type", "document_type": doctype, "function": "Count",
                "is_public": 1, "is_standard": 0, "color": color,
                "filters_json": json.dumps(filters), "show_percentage_stats": 1,
                "stats_time_interval": "Daily"}).insert(ignore_permissions=True)
    if not frappe.db.exists("Workspace", "DCS Governance"):
        shortcuts = ("Deal Cost Sheet", "DCS Handover Condition", "DCS Revision", "DCS Governance Event")
        blocks = [{"id": "dcs_governance_header", "type": "header", "data": {
            "text": '<span class="h4"><b>DCS Governance</b></span>', "col": 12}}]
        blocks += [{"id": "dcs_governance_shortcut_" + str(i), "type": "shortcut",
            "data": {"shortcut_name": name, "col": 3}} for i, name in enumerate(shortcuts)]
        frappe.get_doc({"doctype": "Workspace", "label": "DCS Governance", "title": "DCS Governance",
            "public": 1, "module": frappe.get_meta("Deal Cost Sheet").module,
            "content": json.dumps(blocks), "roles": [{"role": role} for role in
                ("Sales Manager", "Commercial Controller", "Managing Director") if frappe.db.exists("Role", role)],
            "shortcuts": [{"type": "DocType", "link_to": name, "label": name, "doc_view": "List"}
                for name in shortcuts]}).insert(ignore_permissions=True)


def execute():
    ensure_components()
    workspace = frappe.get_doc("Workspace", "DCS Governance")
    blocks = json.loads(workspace.content or "[]")
    # Remove only our cards from their previous positions; preserve every other block.
    blocks = [b for b in blocks if not (b.get("type") == "number_card"
              and b.get("data", {}).get("number_card_name") in CARDS)]
    position = 1 if blocks and blocks[0].get("type") == "header" else 0
    cards = [{"id": "dcs_live_count_" + str(i), "type": "number_card",
              "data": {"number_card_name": name, "col": 4}}
             for i, name in enumerate(CARDS)]
    blocks[position:position] = cards
    have = {r.number_card_name for r in workspace.number_cards}
    for name in CARDS:
        if name not in have:
            workspace.append("number_cards", {"number_card_name": name, "label": name})
    workspace.content = json.dumps(blocks)
    workspace.save(ignore_permissions=True)
    frappe.clear_cache()
