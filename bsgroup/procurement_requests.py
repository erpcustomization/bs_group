"""Supporting documents for manually raised BS purchase requisitions."""
import frappe
from frappe.utils import cint
from bsgroup.procurement_controls import evidence


def normalize(data):
    from bsgroup.procurement import parse, text, fail
    data = parse(data)
    if not isinstance(data, dict):
        fail("Invalid PR supporting documents.")
    kind = data.get("kind") or "purchase"
    if kind not in ("purchase", "direct_invoice"):
        fail("Select Purchase or Utility bill / direct invoice.")
    quotes, invoices = data.get("quotes") or [], data.get("invoices") or []
    if not isinstance(quotes, list) or len(quotes) > 3:
        fail("A PR can contain up to three supplier quotations.")
    if not isinstance(invoices, list) or len(invoices) > 20:
        fail("A PR can contain up to 20 invoice copies.")
    if not all(isinstance(x, dict) for x in quotes + invoices):
        fail("Invalid supporting document entry.")
    return dict(kind=kind, exception=bool(cint(data.get("exception"))),
                explanation=text(data.get("explanation")),
                quotes=[dict(supplier=text(q.get("supplier"), 140), file=text(q.get("file"), 140))
                        for q in quotes],
                invoices=[dict(file=text(f.get("file"), 140)) for f in invoices])


def file_references(data):
    return {x.get("file") for x in (data or {}).get("quotes", []) + (data or {}).get("invoices", [])
            if x.get("file")}


def attachment(doc, name):
    from bsgroup.procurement import fail
    file = frappe.get_doc("File", name)
    file.check_permission("read")
    if (file.attached_to_doctype != "Material Request" or file.attached_to_name != doc.name
            or not file.is_private):
        fail("Supporting documents must be private uploads attached to this PR.")
    digest = evidence(file)
    return dict(file=file.name, filename=file.file_name, url=file.file_url, sha256=digest)


def validate_support(doc, required=False):
    from bsgroup.procurement import fail, encoded
    data = normalize(doc.get("custom_bsp_request_evidence"))
    for quote in data["quotes"]:
        if quote["supplier"]:
            supplier = frappe.get_doc("Supplier", quote["supplier"])
            supplier.check_permission("read")
            if supplier.disabled:
                fail("Select an enabled supplier for each PR quotation.")
        if quote["file"]:
            quote.update(attachment(doc, quote["file"]))
    for invoice in data["invoices"]:
        if not invoice["file"]:
            fail("Upload the invoice copy before adding it to the PR.")
        invoice.update(attachment(doc, invoice["file"]))
    if len({f["sha256"] for f in data["invoices"]}) != len(data["invoices"]):
        fail("The same invoice copy has been added more than once.")
    if required:
        if data["kind"] == "direct_invoice":
            if not data["invoices"]:
                fail("Attach at least one invoice copy for a utility bill or direct invoice PR.")
            if not data["exception"]:
                fail("For a utility bill or direct invoice, select No three quotations required and explain why.")
        if data["exception"]:
            if not data["explanation"]:
                fail("Enter notes explaining why three quotations are not required.")
        else:
            quotes = data["quotes"]
            if (len(quotes) != 3 or any(not q["supplier"] or not q["file"] for q in quotes)
                    or len({q["supplier"] for q in quotes}) != 3):
                fail("Attach three quotations from different suppliers, or select No three quotations required and enter notes.")
            if len({q["sha256"] for q in quotes}) != 3:
                fail("Three quotations must contain three different documents; duplicate content is not allowed.")
    doc.custom_bsp_request_evidence = encoded(data)
    return data


def support_data(doc):
    """Expose saved evidence, including server-recorded names and content hashes."""
    from bsgroup.procurement import parse
    data = normalize(doc.get("custom_bsp_request_evidence"))
    saved = parse(doc.get("custom_bsp_request_evidence"))
    for category in ("quotes", "invoices"):
        for value, original in zip(data[category], saved.get(category, [])):
            value.update({k: original.get(k, "") for k in ("filename", "url", "sha256")})
    data["quotes"] += [dict(supplier="", file="", filename="", url="") for _ in range(3-len(data["quotes"]))]
    return data
