"""Oman-only separation of costing text from customer quotation wording."""
from html.parser import HTMLParser

import frappe
from frappe.utils import cint, flt

FLAG = "bs_oman_client_descriptions"
FIELD = "custom_oman_client_description"
SOURCE = "custom_oman_dcs_row"
PARENT = "custom_oman_client_descriptions"
ADDITIONAL = "__additional_charges__"
PRINT_MODE = '(doc.get("custom_oman_client_descriptions") or (doc.docstatus == 0 and doc.get("custom_deal_cost_sheet")))'


def enabled():
    from bsgroup.oman_quotation_flow import enabled as pilot_enabled
    return pilot_enabled() and cint(frappe.defaults.get_global_default(FLAG)) == 1


def managed(q):
    from bsgroup.oman_quotation_flow import pilot
    before = q.get_doc_before_save()
    return bool(enabled() and pilot(q) and (q.docstatus == 0 or q.get(PARENT)
        or (before and before.docstatus == 0)))


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def visible_text(value):
    parser = _Text()
    parser.feed(str(value or ""))
    return " ".join(" ".join(parser.parts).replace("\u00a0", " ").split())


def missing_rows(q):
    if not managed(q):
        return []
    return [r.idx or i for i, r in enumerate(q.items, 1)
        if visible_text(r.get(FIELD)).casefold() in ("", "generic", "item")]


def require_client_wording(q):
    missing = missing_rows(q)
    if missing:
        frappe.throw("Enter CO Item Description for quotation line(s) "
            + ", ".join(map(str, missing))
            + ". Only this wording is printed for the client; internal costing descriptions are never used as a fallback.")


def signature(row):
    return (row.get("item_code"), round(flt(row.get("qty")), 6),
        round(flt(row.get("rate", row.get("selling_rate"))), 3))


def sources(sheet):
    result = []
    for row in sheet.items:
        name = row.item_name or frappe.db.get_value("Item", row.item_code, "item_name") or row.item_code
        description = row.description or (name if row.exclude_item_name_and_brand else
            " - ".join(str(v) for v in (row.brand, row.item_code, name) if v))
        result.append(dict(key=row.name, item_code=row.item_code, qty=row.qty,
            rate=row.selling_rate, description=description))
    charges = sum(flt(r.get("selling_amount")) for r in sheet.addtional_charges or [])
    if charges:
        code = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
        name = frappe.db.get_value("Item", code, "item_name") or code
        result.append(dict(key=ADDITIONAL, item_code=code, qty=1, rate=charges, description=name))
    return result


def bind(q, sheet, restore_internal=True):
    """Resolve legacy lines once; revisions subsequently follow immutable DCS row IDs."""
    expected = sources(sheet)
    by_key = {r["key"]: r for r in expected}
    used, bindings = set(), []
    ordered = len(q.items) == len(expected) and all(signature(a) == signature(b)
        for a, b in zip(q.items, expected))
    for i, row in enumerate(q.items):
        key = row.get(SOURCE)
        source = by_key.get(key) if key else None
        if key and (not source or signature(row) != signature(source)):
            frappe.throw("Quotation source lines changed. Use Revise Costing Sheet to update the linked quotation.")
        if not source and ordered:
            source = expected[i]
        if not source:
            candidates = [r for r in expected if r["key"] not in used and signature(row) == signature(r)]
            matching = [r for r in candidates if visible_text(r["description"]) == visible_text(row.description)]
            source = matching[0] if len(matching) == 1 else candidates[0] if len(candidates) == 1 else None
        if not source or source["key"] in used:
            frappe.throw("Quotation lines cannot be matched safely to costing. Review the DCS links before saving.")
        used.add(source["key"])
        row.set(SOURCE, source["key"])
        if restore_internal:
            row.description = source["description"]
        bindings.append((row, source))
    if len(used) != len(expected):
        frappe.throw("Quotation scope differs from costing. Use Revise Costing Sheet.")
    return bindings


def prepare(q):
    if not managed(q):
        return
    before = q.get_doc_before_save()
    from bsgroup.oman_quotation_flow import _operation
    revising = _operation.get() == (q.name, "revise")
    prior = {r.name: r for r in before.items} if before else {}
    if not revising:
        for row in q.items:
            old = prior.get(row.name)
            if old and old.get(SOURCE) and row.get(SOURCE) != old.get(SOURCE):
                frappe.throw("Costing source references are maintained by the quotation service.")
    sheet = frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet)
    bind(q, sheet)
    q.set(PARENT, 1)


def preserved_wording(q, previous_sheet):
    if not managed(q):
        return {}
    return {source["key"]: (row.item_code, row.get(FIELD) or "")
        for row, source in bind(q, previous_sheet, restore_internal=False)}


def print_html(html):
    """Patch only the pilot format; keep historical offers' legacy branch intact."""
    marker = "{# Oman CO descriptions v2 #}"
    if marker in html:
        return html
    if "{# Oman CO descriptions v1 #}" in html:
        old_mode = 'doc.get("custom_oman_client_descriptions")'
        if html.count(old_mode) != 4:
            frappe.throw("Review the existing Oman client-description print conditions before setup.")
        return html.replace("{# Oman CO descriptions v1 #}", marker).replace(old_mode, PRINT_MODE)
    replacements = {
        '{%- set raw = row.description or row.item_name or "" -%}':
            '{%- set raw = (row.get("custom_oman_client_description") or "") if ' + PRINT_MODE + ' else (row.description or row.item_name or "") -%}',
        '{%- set head = parts[0] if parts|length else (row.item_name or "") -%}':
            '{%- set head = parts[0] if parts|length else ("" if ' + PRINT_MODE + ' else (row.item_name or "")) -%}',
        '{% if row.item_code and row.item_code not in PLACEHOLDERS %}':
            '{% if not ' + PRINT_MODE + ' and row.item_code and row.item_code not in PLACEHOLDERS %}',
    }
    for old, new in replacements.items():
        count = 2 if old.startswith("{% if row.item_code") else 1
        if html.count(old) != count:
            frappe.throw("The Oman print layout changed. Review the description and item-code sections before setup.")
        html = html.replace(old, new)
    return marker + "\n" + html


def readiness_script(script):
    marker = "// Oman CO descriptions v2"
    if marker in script:
        return script
    declaration = "const clientWording = !!(d.custom_oman_client_descriptions || (d.docstatus === 0 && d.custom_deal_cost_sheet) || frm.__oman_client_descriptions);"
    if "// Oman CO descriptions v1" in script:
        return script.replace("// Oman CO descriptions v1", marker).replace(
            "const clientWording = !!(d.custom_oman_client_descriptions || frm.__oman_client_descriptions);", declaration)
    anchor = "const items = d.items || [];"
    expression = "const t = eqa_flatten(r.description || r.item_name || '');"
    if script.count(anchor) != 1 or script.count(expression) != 1:
        frappe.throw("The Oman readiness script changed. Review its description checks before setup.")
    script = script.replace(anchor, anchor + "\n\t" + marker
        + "\n\t" + declaration)
    script = script.replace(expression,
        "const t = eqa_flatten(clientWording ? (r.custom_oman_client_description || '') : (r.description || r.item_name || ''));")
    script = script.replace("'items[].description (empty or placeholder-only) · line(s) '",
        "(clientWording ? 'CO Item Description' : 'items[].description') + ' (empty or placeholder-only) · line(s) '")
    return script.replace("'items[].description · line(s) '",
        "(clientWording ? 'CO Item Description' : 'items[].description') + ' · line(s) '")


@frappe.whitelist(methods=["POST"])
def install():
    from bsgroup.oman_quotation_flow import OMAN_SITES, PILOT_PRINT_FORMAT, SOURCE_PRINT_FORMAT
    if frappe.local.site not in OMAN_SITES or frappe.session.user != "Administrator":
        frappe.throw("Only Administrator on Oman can enable CO Item Descriptions.", frappe.PermissionError)
    if not frappe.db.exists("Print Format", PILOT_PRINT_FORMAT):
        frappe.throw("Complete the existing Oman quotation pilot setup first.")
    # Validate live templates before any schema/configuration mutation.
    formats = [frappe.get_doc("Print Format", name) for name in (PILOT_PRINT_FORMAT, SOURCE_PRINT_FORMAT)]
    rendered = [(fmt, print_html(fmt.html)) for fmt in formats]
    script = frappe.get_doc("Client Script", "Quotation Readiness - Class A OM")
    code = readiness_script(script.script)
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Quotation": [dict(fieldname=PARENT, label="Client description mode",
        fieldtype="Check", hidden=1, read_only=1, print_hide=1, no_copy=1)],
        "Quotation Item": [
            dict(fieldname=FIELD, label="CO Item Description", fieldtype="Text Editor",
                insert_after="description", in_list_view=1, columns=3,
                description="Only this wording is printed for the client. Enter customer-friendly wording without internal part numbers where required."),
            dict(fieldname=SOURCE, label="Oman costing source row", fieldtype="Data",
                hidden=1, read_only=1, print_hide=1, no_copy=1),
        ]})
    for fmt, html in rendered:
        if fmt.html != html:
            fmt.html = html
            fmt.save(ignore_permissions=True)
    if script.script != code:
        script.script = code
        script.save(ignore_permissions=True)
    frappe.defaults.set_global_default(FLAG, 1)
    frappe.clear_cache()
    return dict(enabled=True, roles_changed=False, historical_quotations_changed=False)
