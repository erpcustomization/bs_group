"""Add explicit quotation lineage and restore Presales commercial permissions."""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def execute():
    create_custom_fields({"Quotation": [
        {"fieldname": "custom_dcs_revision_reference", "label": "DCS Revision Reference",
         "fieldtype": "Data", "read_only": 1, "allow_on_submit": 1},
        {"fieldname": "custom_dcs_superseded_revision", "label": "Superseded by DCS Revision",
         "fieldtype": "Data", "read_only": 1, "allow_on_submit": 1}
    ]})
    if frappe.db.exists("Custom DocPerm", {"parent": "Deal Cost Sheet"}):
        for level in (0, 1):
            filters = {"parent": "Deal Cost Sheet", "role": "Presales", "permlevel": level}
            name = frappe.db.get_value("Custom DocPerm", filters, "name")
            values = {"read": 1, "write": 1, "create": 0, "submit": 0, "cancel": 0, "delete": 0}
            if name:
                frappe.db.set_value("Custom DocPerm", name, values)
            else:
                frappe.get_doc({"doctype": "Custom DocPerm", "parenttype": "DocType",
                    "parentfield": "permissions", **filters, **values}).insert(ignore_permissions=True)
    frappe.clear_cache(doctype="Deal Cost Sheet")

    # Keep the published management view aligned with the app payload.
    name = frappe.db.get_value("Web Page", {"route": "living-dcs"}, "name")
    if name:
        page = frappe.get_doc("Web Page", name)
        marker = "/* DCS_AUDIT_MARGIN_BRIDGE */"
        if marker not in (page.javascript or ""):
            anchor = "  h+='<div class=\"ldcs-grid\"><div class=\"ldcs-card\"><div class=\"ldcs-h\">Readiness gates</div>';"
            addition = r'''  /* DCS_AUDIT_MARGIN_BRIDGE */
  var b=p.margin_bridge;
  if(b){
   h+='<div class="ldcs-card"><div class="ldcs-h">Margin bridge</div><table class="ldcs-t"><thead><tr><th>Position</th><th class="r">Buying</th><th class="r">Selling</th><th class="r">GP</th><th class="r">Margin</th></tr></thead><tbody>';
   [['Original',b.original],['Current',b.current],['Awarded',b.awarded]].forEach(function(x){if(x[1])h+='<tr><td>'+esc(x[0])+'</td><td class="r">'+money(x[1].cost,c)+'</td><td class="r">'+money(x[1].selling,c)+'</td><td class="r">'+money(x[1].gp,c)+'</td><td class="r">'+n(x[1].margin_percent,3)+'%</td></tr>';});
   h+='</tbody></table><div class="ldcs-kv"><span>GP movement</span><b>'+money(b.gp_movement,c)+' · '+n(b.margin_point_movement,3)+' margin points</b></div>';
   Object.keys(b.gp_impacts).forEach(function(k){h+='<div class="ldcs-kv"><span>'+esc(k)+' GP impact</span><b>'+money(b.gp_impacts[k],c)+'</b></div>';});
   h+='<div class="ldcs-kv"><span>Approval</span><b>'+esc(b.approval_required)+' · '+esc(b.approval_state)+'</b></div><div class="ldcs-note">'+esc(b.basis)+'</div></div>';
  }
'''
            if anchor not in (page.javascript or ""):
                frappe.throw("Living DCS page layout changed; review the margin bridge insertion before release.")
            page.javascript = page.javascript.replace(anchor, addition + anchor)
            page.save(ignore_permissions=True)
