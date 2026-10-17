"""Customer PO enforcement and immutable sales-to-procurement document packets."""
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import PurePosixPath
import frappe
from frappe import _
from frappe.utils import now_datetime, escape_html
from frappe.utils.file_manager import save_file
from bsgroup.dcs.quotation_control import validate_position

DT = "DCS Purchase Request"
_writer = ContextVar("dcs_procurement_writer", default=False)
SEND_ROLES = {"Sales Manager", "Commercial Controller", "Managing Director"}
BUY_ROLES = {"Purchase User", "Purchase Manager"}

@contextmanager
def writing():
    token = _writer.set(True)
    try:
        yield
    finally:
        _writer.reset(token)

def deny(message="Not permitted"):
    frappe.throw(_(message), frappe.PermissionError)

def guard(doc, method=None):
    if not _writer.get() or (doc.doctype == DT and not doc.is_new()):
        deny("Purchase request packets are immutable. Create a new award for a new request.")

def has_permission(doc, ptype=None, user=None, **kwargs):
    user = user or frappe.session.user
    if ptype not in ("read", "select", "print") or user == "Guest":
        return False
    if user == "Administrator":
        return True
    roles = set(frappe.get_roles(user))
    from frappe.core.doctype.user_permission.user_permission import get_user_permissions
    company_permissions = get_user_permissions(user).get("Company", [])
    if company_permissions and doc.company not in {p.doc for p in company_permissions}:
        return False
    if roles & BUY_ROLES:
        return True
    return bool(roles & SEND_ROLES and frappe.has_permission("Quotation", "read", doc=doc.quotation, user=user)
                and frappe.has_permission("Deal Cost Sheet", "read", doc=doc.dcs, user=user))

def query_conditions(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return ""
    roles = set(frappe.get_roles(user))
    if user == "Guest" or not roles & (BUY_ROLES | SEND_ROLES):
        return "1=0"
    # User permissions on Company are also enforced by Frappe's list query.
    if roles & BUY_ROLES:
        return ""
    names = [r.name for r in frappe.get_all(DT, fields=["name", "dcs", "quotation", "company"])
             if has_permission(r, "read", user)]
    return "name in ({})".format(",".join(frappe.db.escape(n) for n in names)) if names else "1=0"

def po_file(quotation):
    url = quotation.get("custom_customer_po")
    if not url:
        frappe.throw(_("Upload the Customer PO before saving this quotation as Won."))
    name = frappe.db.get_value("File", {"file_url": url, "attached_to_doctype": "Quotation",
        "attached_to_name": quotation.name, "is_private": 1, "is_folder": 0}, "name")
    if not name or not url.startswith("/private/files/"):
        frappe.throw(_("Upload a private Customer PO file attached to this quotation."))
    file = frappe.get_doc("File", name)
    if PurePosixPath(file.file_name).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".webp"}:
        frappe.throw(_("Customer PO must be a PDF or image."))
    if not file.get_content():
        frappe.throw(_("The uploaded Customer PO is empty or unavailable."))
    return file

def validate_won(doc, method=None):
    if not doc.get("custom_deal_cost_sheet"):
        return
    before = doc.get_doc_before_save()
    if before and before.get("custom_purchase_request"):
        for field in ("custom_customer_po", "custom_customer_po_reference", "custom_pipeline_stage"):
            if doc.get(field) != before.get(field):
                frappe.throw(_("This quotation was sent to procurement. Its PO and Won status are locked."))
    if doc.custom_pipeline_stage != "Won" or doc.docstatus == 2:
        return
    if doc.docstatus != 1:
        frappe.throw(_("Submit the quotation before marking it Won."))
    if not (doc.get("custom_customer_po_reference") or "").strip():
        frappe.throw(_("Customer PO Reference is required when the quotation is Won."))
    po_file(doc)
    sheet = frappe.get_doc("Deal Cost Sheet", doc.custom_deal_cost_sheet)
    validate_position(sheet, doc)
    if sheet.custom_quotation and sheet.custom_quotation != doc.name:
        frappe.throw(_("Only the current quotation linked to this costing sheet can be awarded."))
    if before and before.get("custom_purchase_request") != doc.get("custom_purchase_request"):
        deny("Purchase request reference is managed by Send to Procurement.")

def sync_won(doc, method=None):
    if not doc.get("custom_deal_cost_sheet") or doc.custom_pipeline_stage != "Won" or doc.docstatus != 1:
        return
    sheet = frappe.get_doc("Deal Cost Sheet", doc.custom_deal_cost_sheet, for_update=True)
    if sheet.custom_award_state == "Awarded":
        return
    from bsgroup.api.dcs.award import dcs_record_award
    result = dcs_record_award(dcs=sheet.name, award_reference=doc.custom_customer_po_reference,
                              evidence_type="Customer PO", notes="Customer PO uploaded on quotation " + doc.name +
                              " (award sequence " + str((sheet.custom_award_sequence_no or 0) + 1) + ")")
    if not result.get("ok"):
        frappe.throw(result.get("error") or _("The customer award could not be recorded."))
    sheet.reload()
    if sheet.custom_award_state != "Awarded":
        frappe.throw(_("The award is no longer active. Refresh the quotation and try again."))
    if not sheet.custom_quotation:
        frappe.db.set_value("Deal Cost Sheet", sheet.name, "custom_quotation", doc.name)


def guard_reference(doc, method=None):
    before = doc.get_doc_before_save()
    if (doc.get("custom_purchase_request") or None) != ((before.get("custom_purchase_request") or None) if before else None):
        deny("Purchase request reference is managed by Send to Procurement.")

def file_guard(doc, method=None):
    old = doc.get_doc_before_save()
    parent = old or doc
    if doc.attached_to_doctype == DT or parent.attached_to_doctype == DT:
        if not _writer.get():
            deny("Procurement packet files cannot be changed or deleted.")
    if (parent.attached_to_doctype == "Quotation" and parent.attached_to_name
            and frappe.get_meta("Quotation").has_field("custom_customer_po")):
        quote = frappe.db.get_value("Quotation", parent.attached_to_name,
            ["custom_pipeline_stage", "custom_customer_po"], as_dict=True)
        if quote and quote.custom_pipeline_stage == "Won" and quote.custom_customer_po == parent.file_url:
            if method == "on_trash" or not doc.is_private or any(doc.get(k) != parent.get(k) for k in
                    ("file_url", "attached_to_doctype", "attached_to_name")):
                deny("The Customer PO for a Won quotation must be retained as a private attachment.")


def costing_snapshot(sheet):
    # Explicit allowlist: confidential obligations and net contribution never enter the packet.
    return {"dcs": sheet.name, "company": sheet.company, "currency": sheet.currency,
        "subject": sheet.subject, "revision": sheet.custom_revision_reference,
        "revision_no": sheet.custom_frozen_revision_no, "award_sequence": sheet.custom_award_sequence_no,
        "total_cost": sheet.custom_frozen_total_cost, "total_selling": sheet.custom_frozen_total_selling,
        "items": [{k:r.get(k) for k in ("item_code", "item_name", "description", "qty", "cost_rate", "selling_rate")}
                  for r in sheet.items],
        "resources": [{k:r.get(k) for k in ("resource_type", "no_of_persons", "no_of_days", "hours", "cost_rate", "cost_amount")}
                      for r in sheet.resources or []],
        "additional_charges": [{k:r.get(k) for k in ("description", "amount", "selling_amount")}
                               for r in sheet.addtional_charges or []]}


def costing_pdf(data):
    from frappe.utils.pdf import get_pdf
    from frappe.utils import strip_html, flt
    from bsgroup.dcs.currency import money_precision
    money = lambda value: f"{flt(value):,.{money_precision(data['currency'])}f}"
    e = lambda v: escape_html(str(v if v is not None else ""))
    html = '<h1>Deal Cost Sheet</h1><p>' + e(data["dcs"]) + ' | ' + e(data["revision"]) + '</p>'
    html += '<p>' + e(data["company"]) + ' | ' + e(data["subject"]) + ' | ' + e(data["currency"]) + '</p>'
    for title, rows in (("Items", data["items"]), ("Labour / Resources", data["resources"]),
                        ("Additional Charges", data["additional_charges"])):
        if not rows:
            continue
        keys = list(rows[0])
        html += '<h2>' + title + '</h2><table border="1" cellpadding="5"><thead><tr>'
        html += ''.join('<th>' + e(k.replace('_',' ').title()) + '</th>' for k in keys) + '</tr></thead><tbody>'
        html += ''.join('<tr>' + ''.join('<td>' + e(money(row[k]) if k in {'cost_rate','selling_rate','cost_amount','amount','selling_amount'} else strip_html(str(row[k] or '')) if k == 'description' else row[k]) + '</td>' for k in keys) + '</tr>' for row in rows)
        html += '</tbody></table>'
    html += '<p>Total Cost: ' + e(money(data["total_cost"])) + ' | Total Selling: ' + e(money(data["total_selling"])) + '</p>'
    return get_pdf(html)


def procurement_users(request):
    candidates = frappe.get_all("Has Role", filters={"role":["in",sorted(BUY_ROLES)], "parenttype":"User"}, pluck="parent")
    return sorted({u for u in candidates if frappe.db.get_value("User",u,"enabled")
                   and frappe.db.get_value("User",u,"user_type") == "System User"
                   and has_permission(request, "read", u)})


@frappe.whitelist(methods=["POST"])
def send_to_procurement(quotation):
    if not set(frappe.get_roles()) & SEND_ROLES:
        deny("Sending to procurement requires commercial authority.")
    # Lock before reading the quotation so a competing send cannot invalidate
    # an earlier optimistic read. Won-save uses this same quotation -> sheet order.
    q = frappe.get_doc("Quotation", quotation, for_update=True)
    q.check_permission("write")
    if q.docstatus != 1 or q.custom_pipeline_stage != "Won":
        frappe.throw(_("Save the submitted quotation as Won before sending to procurement."))
    if not q.get("custom_deal_cost_sheet"):
        frappe.throw(_("A linked Deal Cost Sheet is required."))
    # Serialise by sheet, including parallel sends against different quotations of this deal.
    sheet = frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet, for_update=True)
    sheet.check_permission("write")
    validate_won(q)
    if sheet.custom_award_state != "Awarded" or not sheet.custom_baseline_frozen:
        frappe.throw(_("The customer award must be active before sending to procurement."))
    if sheet.custom_frozen_revision_no != sheet.custom_dcs_revision_no:
        frappe.throw(_("The costing revision differs from the awarded revision."))
    from bsgroup.dcs.commercial_authority import authorised_position
    if not authorised_position(sheet):
        frappe.throw(_("The awarded commercial position is not authorised."))
    if importlib.util.find_spec("bsgroup.dcs.obligation") is not None:
        from bsgroup.dcs.obligation import assert_clearance
        assert_clearance(sheet)
    key = hashlib.sha256((sheet.name + ":" + str(sheet.custom_award_sequence_no)).encode()).hexdigest()
    existing = frappe.db.get_value(DT, {"award_key": key}, "name", for_update=True)
    if existing:
        request = frappe.get_doc(DT, existing, for_update=True)
        request.check_permission("read")
        if request.quotation != q.name:
            frappe.throw(_("This award was already sent using another quotation."))
        return {"name":existing, "already_sent":True}
    source = po_file(q)
    packet = frappe.get_doc({"doctype":DT,"dcs":sheet.name,"quotation":q.name,"company":sheet.company,
        "customer_po_reference":q.custom_customer_po_reference,"revision_reference":sheet.custom_revision_reference,
        "award_sequence":sheet.custom_award_sequence_no,"award_key":key,"status":"Sent to Procurement",
        "sent_by":frappe.session.user,"sent_on":now_datetime()})
    recipients = procurement_users(packet)
    if not recipients:
        frappe.throw(_("No enabled procurement users have access to this company. Assign Purchase User or Purchase Manager before sending."))
    data = costing_snapshot(sheet)
    quote_pdf = frappe.get_print("Quotation",q.name,as_pdf=True)
    cost_pdf = costing_pdf(data)
    with writing():
        packet.insert(ignore_permissions=True)
        files = []
        for field, name, content in (("awarded_quotation", "Awarded-Quotation.pdf", quote_pdf),
                                    ("customer_po", source.file_name, source.get_content()),
                                    ("costing_sheet", "Awarded-Costing-Sheet.pdf", cost_pdf)):
            f = save_file(name,content,DT,packet.name,is_private=1,df=field)
            files.append({"field":field,"file":f.name,"sha256":hashlib.sha256(content if isinstance(content,bytes) else content.encode()).hexdigest()})
            frappe.db.set_value(DT,packet.name,field,f.file_url,update_modified=False)
        frappe.db.set_value(DT,packet.name,"packet_manifest",json.dumps({"costing":data,"files":files},default=str),update_modified=False)
    frappe.db.set_value("Quotation",q.name,"custom_purchase_request",packet.name,update_modified=False)
    from bsgroup.dcs.governance import record_governance_event
    record_governance_event(sheet.name,"DCS_PROCUREMENT_SENT",action_label="Send awarded documents to procurement",
        source_endpoint="send_to_procurement",revision_no=sheet.custom_frozen_revision_no,
        revision_reference=sheet.custom_revision_reference,evidence_reference=packet.name,
        changes=[{"dt":"Quotation","dn":q.name,"field":"custom_purchase_request","old":"","new":packet.name}])
    for user in recipients:
        frappe.get_doc({"doctype":"Notification Log","type":"Alert","subject":"Purchase request " + packet.name,
            "document_type":DT,"document_name":packet.name,"for_user":user,"from_user":frappe.session.user}).insert(ignore_permissions=True)
    q.add_comment("Info",_("Sent to Procurement: {0}").format(packet.name))
    return {"name":packet.name,"already_sent":False}


class ProcurementFileMixin:
    # Core File methods move/delete blobs before doc-event hooks run.
    # Refuse first so a rejected operation cannot alter the stored documents.
    def before_insert(self):
        file_guard(self, "before_insert")
        return super().before_insert()

    def validate(self):
        file_guard(self, "validate")
        return super().validate()

    def on_trash(self):
        file_guard(self, "on_trash")
        return super().on_trash()


def before_cancel(doc, method=None):
    if doc.get("custom_purchase_request"):
        frappe.throw(_("This quotation was sent to procurement. Resolve its purchase request before cancellation."))
