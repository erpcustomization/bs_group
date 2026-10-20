"""Temporary fixtures used only by rollback tests."""
import uuid
from pathlib import Path
from io import BytesIO
import frappe
from pypdf import PdfWriter

MANAGER2="zztest-bsp-manager-two@example.com"
FILES=[]


def pdf_content(label):
    stream=BytesIO()
    writer=PdfWriter()
    writer.add_blank_page(width=200,height=200)
    writer.add_metadata({"/Title":label})
    writer.write(stream)
    return stream.getvalue()


def supplier_details(doc):
    """Use explicit test-only masters; do not fill real supplier defaults."""
    user=frappe.session.user
    frappe.set_user("Administrator")
    try:
        tag="ZZTEST BSP QC "+doc.supplier
        address=frappe.db.get_value("Address",{"address_title":tag},"name")
        if not address:
            address=frappe.get_doc(dict(doctype="Address",address_title=tag,address_type="Billing",
                address_line1="QC TEST ONLY — DO NOT ISSUE",city="Dubai",country="United Arab Emirates",
                links=[dict(link_doctype="Supplier",link_name=doc.supplier)])).insert().name
        contact=frappe.db.get_value("Contact",{"first_name":tag},"name")
        if not contact:
            contact=frappe.get_doc(dict(doctype="Contact",first_name=tag,
                email_ids=[dict(email_id="zztest-supplier@example.com",is_primary=1)],
                links=[dict(link_doctype="Supplier",link_name=doc.supplier)])).insert().name
        tax="ZZTEST BSP Explicit Zero Tax - AE"
        if not frappe.db.exists("Purchase Taxes and Charges Template",tax):
            template=frappe.copy_doc(frappe.get_doc("Purchase Taxes and Charges Template","UAE VAT 5% Input - AE - AE"))
            template.title="ZZTEST BSP Explicit Zero Tax"
            template.is_default=0
            for row in template.taxes:
                row.rate=0
                row.description="QC explicit zero tax fixture"
            template.insert()
            tax=template.name
    finally:
        frappe.set_user(user)
    from frappe.contacts.doctype.address.address import get_address_display
    from frappe.contacts.doctype.contact.contact import get_contact_details
    doc.supplier_address=address
    doc.address_display=get_address_display(address)
    doc.contact_person=contact
    for key,value in get_contact_details(contact).items():
        doc.set(key,value)
    if not doc.taxes_and_charges:
        doc.taxes_and_charges=tax
        doc.set("taxes",[])
        for row in frappe.get_doc("Purchase Taxes and Charges Template",tax).taxes:
            doc.append("taxes",{k:row.get(k) for k in (
                "charge_type","account_head","description","rate","category","add_deduct_tax","cost_center")})
    return doc


def prepare_po(name):
    doc=frappe.get_doc("Purchase Order",name)
    supplier_details(doc)
    doc.save()
    return doc


def make_file(po,label,content=None):
    file=frappe.get_doc(dict(doctype="File",file_name="ZZTEST-GAP-"+uuid.uuid4().hex+".pdf",
        content=content if content is not None else pdf_content(label+" "+uuid.uuid4().hex),is_private=1,
        attached_to_doctype="Purchase Order",attached_to_name=po)).insert()
    FILES.append(file.get_full_path())
    return file


def cleanup_files():
    base=Path("/home/bitssecureit/rel1-bench/sites/rel1-test.local/private/files").resolve()
    for name in set(FILES):
        path=Path(name).resolve()
        assert path.is_relative_to(base), path
        path.unlink(missing_ok=True)
