"""Use the authenticated PDF preparer's business profile, never the offer owner."""
import re
import json

import frappe


def quotation_preparer(doc):
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Sign in before preparing a quotation.")
    profile = frappe.get_doc("User", user)
    employee = frappe.db.get_value("Employee", {
        "user_id": user, "status": "Active", "company": doc.get("company")
    }, ["designation", "cell_number", "company_email"], as_dict=True) or {}
    return dict(
        name=profile.get("full_name") or profile.get("first_name") or user,
        designation=profile.get("designation") or employee.get("designation") or "",
        email=employee.get("company_email") or profile.get("email") or user,
        phone=profile.get("mobile_no") or profile.get("phone") or employee.get("cell_number") or "",
    )


SIGNATURE = '''{# BS quotation converter signature v1 #}
{% set preparer = quotation_preparer(doc) %}
<div class="bs-quotation-preparer" style="break-inside:avoid;page-break-inside:avoid">
<p class="sig-name"><b>{{ preparer.name | e }}</b></p>
{% if preparer.designation %}<p class="sig-title">{{ preparer.designation | e }}</p>{% endif %}
{% if preparer.phone %}<p class="sig-title">{{ preparer.phone | e }}</p>{% endif %}
<p class="sig-title">{{ preparer.email | e }}</p>
</div>'''


def patch_html(html):
    html = html or ""
    if "BS quotation converter signature v1" in html:
        return html
    # Cover-page signatures in the deployed regional Proposal formats.
    proposal = r'(<div class="cover-closing"[^>]*>With Regards,</div>).*?(?=\s*</div>\s*(?:\{\{ footer\(\) \}\}\s*)?</div>)'
    if re.search(proposal, html, flags=re.S):
        return re.sub(proposal, lambda m: m.group(1) + "\n" + SIGNATURE, html, count=1, flags=re.S)
    # Enterprise layouts keep their independent authorised-signatory block;
    # the preparer is always the current converter, even when a signatory exists.
    enterprise = r'{% elif signatory %}\s*<div class="sec"><div class="sh">(?:Prepared By|With Regards)</div>.*?\n{% endif %}'
    if re.search(enterprise, html, flags=re.S):
        replacement = '{% endif %}\n<div class="sec"><div class="sh">Prepared By</div>\n' + SIGNATURE + '\n</div>'
        return re.sub(enterprise, lambda m: replacement, html, count=1, flags=re.S)
    return html


def patch_format_data(value):
    if not value:
        return value
    rows = json.loads(value)
    changed = False
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict) and row.get("fieldtype") in ("HTML", "Custom HTML"):
                original = row.get("options") or ""
                updated = patch_html(original)
                if updated != original:
                    row["options"] = updated
                    changed = True
    return json.dumps(rows, ensure_ascii=False) if changed else value


def install():
    for name in frappe.get_all("Print Format", filters={"doc_type": "Quotation"}, pluck="name"):
        fmt = frappe.get_doc("Print Format", name)
        updated = patch_html(fmt.html)
        data = patch_format_data(fmt.get("format_data"))
        if updated != (fmt.html or "") or data != fmt.get("format_data"):
            fmt.html = updated
            fmt.format_data = data
            fmt.save(ignore_permissions=True)

