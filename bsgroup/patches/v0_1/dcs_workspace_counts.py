"""Place the existing live number cards above DCS Governance shortcuts."""
import json
import frappe

CARDS = ("Open DCS Handover Blockers", "DCS Awarded Pending Delivery Release",
         "DCS PO Reconciliation Mismatch")

def execute():
    if not frappe.db.exists("Workspace", "DCS Governance"):
        frappe.throw("DCS Governance workspace is missing; restore it before this layout migration.")
    for name in CARDS:
        if not frappe.db.exists("Number Card", name):
            frappe.throw("Required DCS number card is missing: " + name)
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
