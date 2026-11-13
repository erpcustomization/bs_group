"""Optional UAE quotation contractual terms; retain all entered wording."""
import frappe


def patch_html(html):
    # These are the existing Enterprise layouts' exact terms-only conditions.
    # Keep their scope, payment, warranty, validity and other readiness checks.
    return (html or "").replace(
        "or not warr_ok or not doc.tc_name or not doc.valid_till",
        "or not warr_ok or not doc.valid_till"
    ).replace(
        '{% if doc.tc_name and doc.terms %}<div class="sec tc',
        '{% if doc.terms %}<div class="sec tc'
    ).replace(
        'doc.tc_name and doc.terms and "arrant" in doc.terms',
        'doc.terms and "arrant" in doc.terms'
    )


def install():
    from bsgroup.oman_quotation_flow import uae
    if not uae():
        return
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    for name in ("tc_name", "terms"):
        field = frappe.get_meta("Quotation").get_field(name)
        if field and field.reqd:
            make_property_setter("Quotation", name, "reqd", 0, "Check")
        if field and field.mandatory_depends_on:
            make_property_setter("Quotation", name, "mandatory_depends_on", "", "Data")
    for name in frappe.get_all("Print Format", filters={"doc_type": "Quotation"}, pluck="name"):
        doc = frappe.get_doc("Print Format", name)
        html = patch_html(doc.html)
        if html != (doc.html or ""):
            doc.html = html
            doc.save(ignore_permissions=True)
    frappe.clear_cache(doctype="Quotation")
