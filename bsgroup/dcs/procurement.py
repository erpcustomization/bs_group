"""Awarded sales handover into standard ERPNext Material Requests.

The old DCS Purchase Request controller remains read-only for historical packets.
New sends create only a standard Material Request and private source evidence.
"""
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import PurePosixPath
import frappe
from frappe import _
from frappe.utils import now_datetime, escape_html, nowdate, getdate, flt, cint
from frappe.utils.file_manager import save_file
from bsgroup.dcs.quotation_control import validate_position
from bsgroup import procurement as buying

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
    if before and (before.get("custom_purchase_request") or before.get("custom_bsp_material_request")):
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
    for field in ("custom_purchase_request", "custom_bsp_material_request"):
        if (doc.get(field) or None) != ((before.get(field) or None) if before else None):
            deny("Purchase request reference is managed by Send to Procurement.")

def file_guard(doc, method=None):
    old = doc.get_doc_before_save()
    parent = old or doc
    if doc.attached_to_doctype == DT or parent.attached_to_doctype == DT:
        if not _writer.get():
            deny("Procurement packet files cannot be changed or deleted.")
    if parent.attached_to_doctype == buying.MR and parent.attached_to_name:
        manifest = frappe.db.get_value(buying.MR, parent.attached_to_name, "custom_bsp_source_snapshot")
        files = buying.parse(manifest).get("files", [])
        if doc.name in {f["file"] for f in files} and (method == "on_trash" or any(
                doc.get(k) != parent.get(k) for k in
                ("file_url", "is_private", "attached_to_doctype", "attached_to_name"))):
            deny("Sales handover evidence must be retained unchanged. Keep the original file.")
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
        "items": [{k:r.get(k) for k in ("name", "item_code", "item_name", "description", "qty", "cost_rate", "selling_rate")}
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


def source_documents(quotation, lock=False):
    if frappe.session.user != "Administrator" and not set(frappe.get_roles()) & SEND_ROLES:
        deny("Sending to procurement requires commercial authority.")
    q = buying.access(frappe.get_doc("Quotation", quotation, for_update=lock), "write")
    if q.docstatus != 1 or q.custom_pipeline_stage != "Won":
        frappe.throw(_("Save the submitted quotation as Won before sending to procurement."))
    if not q.get("custom_deal_cost_sheet"):
        frappe.throw(_("A linked Deal Cost Sheet is required."))
    # Serialise by sheet, including parallel sends against different quotations of this deal.
    sheet = buying.access(frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet, for_update=lock), "write")
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
    if sheet.currency != frappe.get_cached_value("Company", sheet.company, "default_currency"):
        frappe.throw(_("The DCS and company currencies must match for this procurement handover."))
    return q, sheet


def source_items(sheet):
    rows = []
    for line in sheet.items:
        item = frappe.get_doc("Item", line.item_code)
        if item.disabled or not item.is_purchase_item:
            frappe.throw(_("DCS line {0}: select an enabled purchasable Item before handover.").format(line.idx))
        rows.append(dict(source=line.name, item_code=item.name, item_name=item.item_name,
                         description=line.description or item.description or item.item_name,
                         qty=buying.number(line.qty, "DCS quantity"),
                         rate=buying.number(line.cost_rate, "DCS cost rate", zero=True),
                         uom=item.stock_uom, is_stock_item=item.is_stock_item))
    if not rows or len(rows) > 100:
        frappe.throw(_("The handover needs between one and 100 DCS item lines."))
    return rows


def handover_key(sheet):
    return hashlib.sha256((sheet.name + ":" + str(sheet.custom_award_sequence_no)).encode()).hexdigest()


def handover_warehouses(company):
    """Narrow selection after source-document authority has been checked.

Sales users need no general Stock/warehouse access to send an awarded deal.
Respect explicit Warehouse user restrictions and expose names only.
"""
    from frappe.core.doctype.user_permission.user_permission import get_user_permissions
    allowed = {r.doc for r in get_user_permissions().get("Warehouse", [])}
    names = frappe.get_all("Warehouse", filters={"company":company,"is_group":0,"disabled":0},
                           pluck="name", order_by="name")
    return [name for name in names if not allowed or name in allowed]


@frappe.whitelist()
def handover_context(quotation):
    q, sheet = source_documents(quotation)
    existing = frappe.db.get_value(buying.MR, {"custom_bsp_key": handover_key(sheet)}, "name")
    return dict(quotation=q.name, dcs=sheet.name, company=sheet.company, currency=sheet.currency,
                customer_po=q.custom_customer_po_reference, revision=sheet.custom_revision_reference,
                existing=existing, items=source_items(sheet), required_by=nowdate(),
                warehouses=handover_warehouses(sheet.company),
                resources=len(sheet.resources or []), additional_charges=len(sheet.addtional_charges or []))


@frappe.whitelist(methods=["POST"])
@buying.transaction_conflicts
def send_to_procurement(quotation, schedule_date=None, warehouse=None):
    q, sheet = source_documents(quotation, lock=True)
    key = handover_key(sheet)
    existing = frappe.db.get_value(buying.MR, {"custom_bsp_key": key}, "name", for_update=True)
    if existing:
        if frappe.db.get_value(buying.MR, existing, "custom_bsp_quotation") != q.name:
            frappe.throw(_("This award was already sent using another quotation."))
        return {"name": existing, "doctype": buying.MR, "already_sent": True}
    rows = source_items(sheet)
    if not schedule_date or getdate(schedule_date) < getdate(nowdate()):
        frappe.throw(_("Select a required-by date of today or later."))
    if warehouse:
        if warehouse not in handover_warehouses(sheet.company):
            frappe.throw(_("Select an enabled warehouse belonging to the DCS company."))
    elif any(r["is_stock_item"] for r in rows):
        frappe.throw(_("Select a target warehouse for the stock items."))
    source = po_file(q)
    data = costing_snapshot(sheet)
    # Render before inserting: a rendering failure cannot leave a half-created PR.
    quote_pdf = frappe.get_print("Quotation", q.name, as_pdf=True, no_letterhead=1)
    cost_pdf = costing_pdf(data)
    manifest = dict(costing=data, items=rows, files=[], source_po=source.name,
                    schedule_date=str(schedule_date),
                    customer_po_reference=q.custom_customer_po_reference,
                    customer=q.party_name if q.quotation_to == "Customer" else sheet.customer,
                    project=sheet.project, quotation=q.name)
    request = frappe.new_doc(buying.MR)
    request.update(dict(material_request_type="Purchase", company=sheet.company,
                        transaction_date=nowdate(), schedule_date=schedule_date,
                        custom_bsp_managed=1, custom_bsp_key=key,
                        custom_deal_cost_sheet=sheet.name, custom_bsp_quotation=q.name,
                        custom_project=sheet.project, custom_bsp_customer=manifest["customer"],
                        title=("Purchase · " + (sheet.subject or sheet.name))[:140],
                        custom_bsp_customer_po=q.custom_customer_po_reference,
                        custom_bsp_source_snapshot=buying.encoded(manifest)))
    for row in rows:
        request.append("items", dict(item_code=row["item_code"], item_name=row["item_name"],
                       description=row["description"], qty=row["qty"], rate=row["rate"],
                       stock_uom=row["uom"], uom=row["uom"], conversion_factor=1,
                       custom_bsp_dcs_item=row["source"], warehouse=warehouse,
                       project=sheet.project, schedule_date=schedule_date))
    # The commercial sender can create only this service-built draft. This is not
    # a Purchase User role grant and does not submit or approve the requisition.
    with buying.operation("handover"):
        request.insert(ignore_permissions=True)
    for field, name, content in (
            ("quotation", "Awarded-Quotation.pdf", quote_pdf),
            ("customer_po", source.file_name, source.get_content(encodings=())),
            ("costing", "Awarded-Costing-Sheet.pdf", cost_pdf)):
        # Pass bytes to File directly. The legacy save_file helper writes a
        # blob first and then lets File read/decode it again during insert,
        # which can transcode a binary PDF header and corrupt its offsets.
        f = frappe.get_doc(dict(doctype="File", file_name=name, content=content,
            attached_to_doctype=buying.MR, attached_to_name=request.name, is_private=1,
            attached_to_field="custom_bsp_customer_po_file" if field == "customer_po" else None
        )).insert(ignore_permissions=True)
        stored_content = f.get_content(encodings=())
        if field == "customer_po" and stored_content != content:
            frappe.throw(_("The customer PO copy differs from the original. Handover was not completed."))
        manifest["files"].append(dict(kind=field, file=f.name, url=f.file_url,
                                     filename=f.file_name,
                                     sha256=hashlib.sha256(stored_content if isinstance(stored_content,bytes) else stored_content.encode()).hexdigest()))
        if field == "customer_po":
            request.custom_bsp_customer_po_file = f.file_url
    request.custom_bsp_source_snapshot = buying.encoded(manifest)
    buying.append_event(request, "Received from Sales", dict(
        quotation=q.name, dcs=sheet.name, revision=data["revision"],
        award_sequence=data["award_sequence"], customer_po=q.custom_customer_po_reference))
    with buying.operation("handover"):
        request.save(ignore_permissions=True)
    frappe.db.set_value("Quotation", q.name, "custom_bsp_material_request", request.name)
    # Standard read-only document share lets the sender follow their requisition.
    # No notification/email is sent and no purchasing approval access is granted.
    if frappe.session.user != "Administrator":
        from frappe import share
        share.add(buying.MR, request.name, user=frappe.session.user,
                         read=1, write=0, share=0, submit=0, notify=0,
                         flags={"ignore_share_permission": True})
    from bsgroup.dcs.governance import record_governance_event
    record_governance_event(sheet.name, "DCS_PROCUREMENT_SENT",
        action_label="Create standard Purchase Requisition",
        source_endpoint="send_to_procurement", revision_no=sheet.custom_frozen_revision_no,
        revision_reference=sheet.custom_revision_reference, evidence_reference=request.name,
        changes=[{"dt":"Quotation","dn":q.name,"field":"custom_bsp_material_request",
                  "old":q.get("custom_bsp_material_request") or "","new":request.name}])
    q.add_comment("Info", _("Sent to Procurement: {0}").format(request.name))
    return {"name": request.name, "doctype": buying.MR, "already_sent": False}


def assert_source_current(request):
    manifest = buying.parse(request.get("custom_bsp_source_snapshot"))
    if not manifest:
        return
    data = manifest["costing"]
    # Match the sales send lock order while validating against concurrent reversal.
    q = frappe.get_doc("Quotation", manifest["quotation"], for_update=True)
    sheet = frappe.get_doc("Deal Cost Sheet", data["dcs"], for_update=True)
    from bsgroup.dcs.commercial_authority import authorised_position
    from bsgroup.dcs.obligation import assert_clearance
    if (sheet.docstatus != 1 or sheet.custom_award_state != "Awarded"
            or not sheet.custom_baseline_frozen or sheet.custom_superseded_by
            or sheet.custom_award_sequence_no != data["award_sequence"]
            or sheet.custom_revision_reference != data["revision"]
            or sheet.custom_frozen_revision_no != sheet.custom_dcs_revision_no
            or not authorised_position(sheet)):
        frappe.throw(_("The source award or DCS revision changed. Resolve the sales handover before continuing procurement."))
    if buying.encoded(costing_snapshot(sheet)) != buying.encoded(data):
        frappe.throw(_("The source costing changed after handover. Resolve the sales handover first."))
    if q.docstatus != 1 or q.custom_pipeline_stage != "Won":
        frappe.throw(_("The source quotation is no longer submitted and Won."))
    validate_position(sheet, q)
    assert_clearance(sheet)


def validate_handover_request(doc, old):
    manifest = buying.parse(doc.get("custom_bsp_source_snapshot"))
    if not manifest:
        return
    # Core MR.on_update reprices rows after validation when its default price
    # list changes. This requisition's budget is the awarded DCS snapshot.
    doc.buying_price_list = None
    if old and not (buying.op() and buying.op()[0] == "handover"):
        if old.custom_bsp_source_snapshot != doc.custom_bsp_source_snapshot:
            deny("Sales handover evidence cannot be changed.")
    data = manifest["costing"]
    if (doc.company != data["company"] or doc.custom_deal_cost_sheet != data["dcs"]
            or doc.custom_bsp_quotation != manifest["quotation"]
            or (doc.custom_project or "") != (manifest.get("project") or "")
            or (doc.custom_bsp_customer or "") != (manifest.get("customer") or "")
            or doc.custom_bsp_customer_po != manifest["customer_po_reference"]):
        deny("Sales handover references cannot be changed.")
    customer_file = next((f["url"] for f in manifest.get("files", []) if f["kind"] == "customer_po"), None)
    if customer_file and doc.custom_bsp_customer_po_file != customer_file:
        deny("The customer PO attachment must match the sales handover evidence.")
    expected = [(r["source"],r["item_code"],r["item_name"],r["description"],
                 flt(r["qty"]),flt(r["rate"]),r["uom"]) for r in manifest["items"]]
    actual = [(r.custom_bsp_dcs_item,r.item_code,r.item_name,r.description,
               flt(r.qty),flt(r.rate),r.uom) for r in doc.items]
    if actual != expected or any(flt(r.conversion_factor) != 1 for r in doc.items):
        frappe.throw(_("PR quantities and budget must match the awarded DCS lines. Revise the source deal for scope changes."))
    required_by = manifest.get("schedule_date") or (str(old.schedule_date) if old else None)
    if required_by and (str(doc.schedule_date) != required_by
                        or any(str(row.schedule_date) != required_by for row in doc.items)):
        frappe.throw(_("The handover required-by date is protected. Resolve the source handover before changing it."))
    if doc.docstatus != 2 and doc.workflow_state in ("Pending Approval", "Approved"):
        assert_source_current(doc)


class ProcurementFileMixin:
    # Core File methods move/delete blobs before doc-event hooks run.
    # Refuse first so a rejected operation cannot alter the stored documents.
    def before_insert(self):
        buying.protect_file(self, "before_insert")
        file_guard(self, "before_insert")
        return super().before_insert()

    def validate(self):
        buying.protect_file(self, "validate")
        file_guard(self, "validate")
        return super().validate()

    def on_trash(self):
        buying.protect_file(self, "on_trash")
        file_guard(self, "on_trash")
        return super().on_trash()


def before_cancel(doc, method=None):
    if doc.get("custom_purchase_request") or doc.get("custom_bsp_material_request"):
        frappe.throw(_("This quotation was sent to procurement. Resolve its purchase request before cancellation."))
