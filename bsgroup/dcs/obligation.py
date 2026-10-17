"""Confidential obligations. No amounts, references or net totals live on the DCS.

Mutations lock the DCS then obligation. An in-process context token, never a
document flag, authorizes writes. Dedicated immutable events replace public
timeline, notifications and Version history.
"""
import hashlib
import json
import math
from contextlib import contextmanager
from contextvars import ContextVar
import frappe
from frappe.utils import flt, now_datetime
from bsgroup.dcs.currency import money_round

DT = "DCS Commercial Obligation"
EVENT = "DCS Commercial Obligation Event"
FINANCE = "sangeetha@bitssecureit.com"
DENIED_USERS = {"manikandan@bitssecureit.com"}
EXCLUDED = {"Operations Manager", "Presales", "Project Engineer", "Technical Engineer"}
EDITABLE = ("obligation_type", "payee", "agreement_reference", "calculation_method",
            "fixed_amount", "percentage", "payment_conditions", "reason")
_writer = ContextVar("dcs_obligation_writer", default=False)


def denied():
    frappe.throw("Not permitted", frappe.PermissionError)


def eligible(user=None):
    user = user or frappe.session.user
    roles = set(frappe.get_roles(user))
    if user in {"Guest", "Administrator"} | DENIED_USERS or roles & EXCLUDED:
        return False
    return bool(user == FINANCE or roles & {"Managing Director", "Sales User", "Sales Manager"})


def audience(sheet, user=None):
    user = user or frappe.session.user
    if not eligible(user):
        return False
    roles = set(frappe.get_roles(user))
    return bool((user == FINANCE or "Managing Director" in roles or sheet.deal_owner == user)
                and frappe.has_permission("Deal Cost Sheet", "read", doc=sheet, user=user))


def require(sheet):
    if not audience(sheet):
        denied()


def has_permission(doc, ptype=None, user=None, **kwargs):
    if ptype not in ("read", "select"):
        return False
    dcs = doc.get("dcs")
    return bool(dcs and audience(frappe.get_doc("Deal Cost Sheet", dcs), user))


def query_conditions(user=None):
    user = user or frappe.session.user
    if not eligible(user):
        return "1=0"
    filters = {} if user == FINANCE or "Managing Director" in frappe.get_roles(user) else {"deal_owner":user}
    names = [r.name for r in frappe.get_all("Deal Cost Sheet", filters=filters, fields=["name"])
             if audience(frappe.get_doc("Deal Cost Sheet", r.name), user)]
    return "dcs in ({})".format(",".join(frappe.db.escape(n) for n in names)) if names else "1=0"


@contextmanager
def writing():
    token = _writer.set(True)
    try:
        yield
    finally:
        _writer.reset(token)


def guard_write(doc, method=None):
    if not _writer.get() or (doc.doctype == EVENT and not doc.is_new()):
        denied()


def guard_delete(doc, method=None):
    denied()


def position(sheet):
    revised = bool(sheet.custom_dcs_revision_no)
    return (money_round(sheet.custom_working_total_selling if revised else sheet.total_selling, sheet.currency),
            money_round(sheet.custom_working_total_cost if revised else sheet.total_cost, sheet.currency))


def amount(doc, selling):
    if doc.calculation_method == "Percentage of customer selling":
        return money_round(selling * flt(doc.percentage) / 100, doc.currency)
    return money_round(doc.fixed_amount, doc.currency)


def all_obligations(sheet):
    return [frappe.get_doc(DT, r.name) for r in frappe.get_all(DT, filters={"dcs": sheet.name},
            fields=["name"], order_by="creation, name")]


def financials(sheet, docs=None):
    selling, cost = position(sheet)
    docs = docs if docs is not None else all_obligations(sheet)
    if any(d.currency != sheet.currency for d in docs):
        frappe.throw("Commercial currency clearance is required.")
    forecast = sum(amount(d, selling) if d.status != "Rejected" else flt(d.approved_amount) for d in docs)
    committed = sum(flt(d.approved_amount) for d in docs)
    net = money_round(selling-cost-forecast, sheet.currency)
    return dict(currency=sheet.currency, selling=selling, delivery_cost=cost,
                delivery_contribution=money_round(selling-cost, sheet.currency),
                forecast_obligations=money_round(forecast, sheet.currency),
                approved_commitments=money_round(committed, sheet.currency),
                forecast_net_contribution=net,
                forecast_net_margin=net/selling*100 if selling > 0 else None,
                approved_net_contribution=money_round(selling-cost-committed, sheet.currency))


def basis(sheet):
    f = financials(sheet)
    return hashlib.sha256(json.dumps([f["currency"], f["selling"], f["delivery_cost"],
           f["forecast_obligations"]], separators=(",", ":")).encode()).hexdigest()


def is_current(doc, sheet):
    margin = financials(sheet)["forecast_net_margin"]
    return bool(doc.status == "Approved" and doc.decision_basis == basis(sheet)
                and doc.finance_by and doc.finance_by != doc.requested_by and margin is not None
                and (margin >= 20 or (doc.md_by and doc.md_by != doc.requested_by
                                     and doc.md_by != doc.finance_by)))


def assert_clearance(sheet):
    """Execution gate only; never used to enrich public financial projections."""
    docs = all_obligations(sheet)
    if any(not is_current(d, sheet) for d in docs if d.status != "Rejected" or d.approved_amount):
        frappe.throw("The current commercial position requires clearance before this action.")


def validate_terms(doc, sheet):
    if sheet.docstatus == 2 or sheet.custom_superseded_by:
        frappe.throw("This Deal Cost Sheet is not active.")
    if sheet.custom_award_state == "Awarded" or str(sheet.custom_delivery_release_state or "").startswith("Released"):
        frappe.throw("Record obligations before award. Reopen the commercial position through the governed process.")
    if doc.obligation_type not in ("Consulting", "Partner Fee", "Other"):
        frappe.throw("Choose an obligation type.")
    if doc.calculation_method not in ("Fixed amount", "Percentage of customer selling"):
        frappe.throw("Choose a calculation method.")
    for field in ("fixed_amount", "percentage"):
        try:
            value = float(doc.get(field) or 0)
        except (TypeError, ValueError):
            frappe.throw("Enter a valid amount.")
        if not math.isfinite(value) or value < 0:
            frappe.throw("Amounts must be finite and non-negative.")
        doc.set(field, value)
    if doc.percentage > 100:
        frappe.throw("Percentage cannot exceed 100.")
    if not all(str(doc.get(f) or "").strip() for f in ("payee", "agreement_reference", "reason")):
        frappe.throw("Payee, agreement reference and revision reason are required.")
    doc.currency = sheet.currency
    if doc.currency not in ("AED", "OMR"):
        frappe.throw("Obligations currently support AED and OMR only.")
    proposed = amount(doc, position(sheet)[0])
    if proposed <= 0:
        frappe.throw("Enter a positive obligation amount.")
    if proposed < max(flt(doc.get("accrued_amount")),flt(doc.get("paid_amount"))):
        frappe.throw("The revised commitment cannot fall below recorded accruals or payments.")
    import re
    for row in sheet.addtional_charges or []:
        text = str(row.get("description") or "") + " " + str(row.get("charges_type") or "")
        if re.search(r"consult(?:ant|ing)|partner\s+(?:fee|payment)|commercial\s+obligation",text,re.I):
            frappe.throw("Resolve legacy commercial charges before recording a separate obligation. No amount has been migrated.")


def persist(doc, action, reason):
    with writing():
        doc.save(ignore_permissions=True)
        frappe.get_doc(dict(doctype=EVENT, dcs=doc.dcs, obligation=doc.name,
            revision=doc.revision, action=action, actor=frappe.session.user,
            occurred_on=now_datetime(), reason=reason,
            snapshot=json.dumps({k:v for k,v in doc.as_dict().items() if not k.startswith("_")},
                                default=str, sort_keys=True))).insert(ignore_permissions=True)


def locked(dcs):
    sheet = frappe.get_doc("Deal Cost Sheet", dcs, for_update=True)
    require(sheet)
    return sheet


@frappe.whitelist()
def overview(dcs):
    if not eligible():
        return {}
    sheet = frappe.get_doc("Deal Cost Sheet", dcs)
    if not audience(sheet):
        return {}
    docs = all_obligations(sheet)
    return dict(can_record=sheet.docstatus != 2 and sheet.custom_award_state != "Awarded",
        financials=financials(sheet, docs) if docs else None,
        obligations=[dict(name=d.name, status=d.status, revision=d.revision,
             amount=amount(d, position(sheet)[0]), approved_amount=d.approved_amount,
             current=is_current(d, sheet), payee=d.payee) for d in docs])


@frappe.whitelist(methods=["POST"])
def save_proposal(dcs, values, name=None, expected_revision=None):
    sheet = locked(dcs)
    values = frappe.parse_json(values)
    if not isinstance(values, dict) or set(values) - set(EDITABLE):
        frappe.throw("Unsupported proposal fields.")
    if name:
        doc = frappe.get_doc(DT, name, for_update=True)
        if doc.dcs != dcs:
            denied()
        if int(expected_revision or 0) != doc.revision:
            frappe.throw("This obligation changed. Refresh before saving.")
    else:
        doc = frappe.new_doc(DT)
        doc.dcs, doc.revision, doc.approved_amount = dcs, 0, 0
    for field in EDITABLE:
        if field in values:
            doc.set(field, values[field])
    validate_terms(doc, sheet)
    doc.revision = (doc.revision or 0) + 1
    doc.status, doc.requested_by = "Draft", frappe.session.user
    doc.finance_by = doc.finance_on = doc.md_by = doc.md_on = doc.decision_basis = None
    persist(doc, "Proposal revised" if name else "Proposal created", doc.reason)
    return {"name":doc.name, "revision":doc.revision}


@frappe.whitelist()
def detail(name):
    if not eligible():
        denied()
    doc = frappe.get_doc(DT, name)
    sheet = frappe.get_doc("Deal Cost Sheet", doc.dcs)
    require(sheet)
    files = frappe.get_all("File", filters={"attached_to_doctype":DT,"attached_to_name":name}, fields=["file_name","file_url","is_private"])
    return dict(can_settle=frappe.session.user == FINANCE, files=files, obligation=doc.as_dict(), financials=financials(sheet),
        current=is_current(doc, sheet),
        can_finance=frappe.session.user == FINANCE and doc.requested_by != FINANCE,
        can_md="Managing Director" in frappe.get_roles() and
               frappe.session.user not in (doc.requested_by, doc.finance_by),
        history=frappe.get_all(EVENT, filters={"obligation":name},
            fields=["revision","action","actor","occurred_on","reason"], order_by="creation, name"))


@frappe.whitelist(methods=["POST"])
def transition(name, action, expected_revision, reason):
    ref = frappe.db.get_value(DT, name, "dcs")
    if not ref:
        denied()
    sheet = locked(ref)
    doc = frappe.get_doc(DT, name, for_update=True)
    if doc.revision != int(expected_revision) or not str(reason or "").strip():
        frappe.throw("Refresh the obligation and supply a decision reason.")
    validate_terms(doc, sheet)
    me, f, current_basis = frappe.session.user, financials(sheet), basis(sheet)
    if action == "Submit":
        if doc.status != "Draft":
            frappe.throw("Only a draft can be submitted.")
        if me != doc.requested_by:
            denied()
        doc.status = "Pending Finance"
    elif action == "Finance Approve":
        if me != FINANCE or me == doc.requested_by or doc.status != "Pending Finance":
            denied()
        if f["forecast_net_margin"] is None:
            frappe.throw("Customer selling must be positive before approval.")
        doc.finance_by, doc.finance_on, doc.decision_basis = me, now_datetime(), current_basis
        doc.status = "Pending MD" if f["forecast_net_margin"] < 20 else "Approved"
    elif action == "MD Approve":
        if "Managing Director" not in frappe.get_roles() or me in (doc.requested_by,doc.finance_by) or doc.status != "Pending MD":
            denied()
        if not doc.finance_by or doc.decision_basis != current_basis:
            frappe.throw("The commercial position changed. Revise and obtain Finance approval again.")
        doc.md_by, doc.md_on, doc.status = me, now_datetime(), "Approved"
    elif action == "Reject":
        if doc.status == "Pending Finance" and me == FINANCE and me != doc.requested_by:
            pass
        elif doc.status == "Pending MD" and "Managing Director" in frappe.get_roles() and me not in (doc.requested_by,doc.finance_by):
            pass
        else:
            denied()
        doc.status = "Rejected"
    else:
        frappe.throw("Unsupported action.")
    if doc.status == "Approved":
        doc.approved_amount = amount(doc, position(sheet)[0])
        doc.approved_snapshot = json.dumps({k:doc.get(k) for k in EDITABLE}, sort_keys=True)
    doc.revision += 1
    persist(doc, action, reason)
    return {"name":doc.name,"revision":doc.revision,"status":doc.status}


REFS = {"Comment":("reference_doctype","reference_name"),
        "Communication":("reference_doctype","reference_name"),
        "Version":("ref_doctype","docname"),
        "File":("attached_to_doctype","attached_to_name"),
        "ToDo":("reference_type","reference_name"),
        "DocShare":("share_doctype","share_name"),
        "Notification Log":("document_type","document_name")}


def protected_ref(doc):
    fields = REFS.get(doc.doctype)
    if fields and doc.get(fields[0]) in (DT, EVENT):
        return doc.get(fields[0]), doc.get(fields[1])
    return None


def auxiliary_permission(doc, ptype=None, user=None, **kwargs):
    ref = protected_ref(doc)
    if doc.doctype == "File" and doc.file_url:
        refs = frappe.get_all("File", filters={"file_url":doc.file_url,
            "attached_to_doctype":["in",[DT,EVENT]]},fields=["attached_to_doctype","attached_to_name"])
        if refs:
            return ptype in ("read","select") and all(has_permission(
                frappe.get_doc(r.attached_to_doctype,r.attached_to_name),"read",user) for r in refs)
    if ref:
        return ptype in ("read","select") and has_permission(frappe.get_doc(*ref),"read",user)
    return True


def auxiliary_query(doctype, user=None):
    q = chr(96)
    column = q+"tab"+doctype+q+"."+q+REFS[doctype][0]+q
    condition = "ifnull({},'') not in ({},{})".format(column,frappe.db.escape(DT),frappe.db.escape(EVENT))
    if doctype == "File":
        condition += " and not exists (select 1 from "+q+"tabFile"+q+" secret where secret.file_url="+q+"tabFile"+q+".file_url and secret.attached_to_doctype in ({},{}))".format(frappe.db.escape(DT),frappe.db.escape(EVENT))
    return condition


def auxiliary_guard(doc, method=None):
    previous, ref = doc.get_doc_before_save(), protected_ref(doc)
    if previous and protected_ref(previous) and protected_ref(previous) != ref:
        denied()
    if doc.doctype == "File":
        if ref:
            if not has_permission(frappe.get_doc(*ref),"read"):
                denied()
            if not doc.is_private or doc.attached_to_doctype != DT or (doc.file_url and not doc.file_url.startswith("/private/files/")):
                frappe.throw("Supporting documents must be private and attached to the obligation.")
            if doc.file_url and frappe.db.exists("File",{"file_url":doc.file_url,"is_private":0}):
                denied()
        elif doc.file_url and frappe.db.exists("File",{"file_url":doc.file_url,"attached_to_doctype":["in",[DT,EVENT]]}):
            denied()
    elif ref:
        denied()


def comment_query(user=None):
    return auxiliary_query("Comment", user)


def communication_query(user=None):
    return auxiliary_query("Communication", user)


def version_query(user=None):
    return auxiliary_query("Version", user)


def file_query(user=None):
    return auxiliary_query("File", user)


def todo_query(user=None):
    return auxiliary_query("ToDo", user)


def docshare_query(user=None):
    return auxiliary_query("DocShare", user)


def notification_log_query(user=None):
    return auxiliary_query("Notification Log", user)

def guard_amendment(doc):
    if doc.amended_from and frappe.db.exists(DT, {"dcs":doc.amended_from}):
        frappe.throw("Commercial clearance is required before amending this sheet.")

class ConfidentialFileMixin:
    def before_insert(self):
        auxiliary_guard(self)
        return super().before_insert()

    def create_attachment_record(self):
        if protected_ref(self):
            return
        return super().create_attachment_record()

    def is_downloadable(self):
        return auxiliary_permission(self, "read") and super().is_downloadable()

@frappe.whitelist(methods=["POST"])
def upload_support(name, filename, content):
    import base64
    import os
    if not eligible():
        denied()
    doc = frappe.get_doc(DT, name)
    locked(doc.dcs)
    if not filename or os.path.basename(filename) != filename or len(content) > 14_000_000:
        frappe.throw("Choose a supporting file up to 10 MB.")
    try:
        data = base64.b64decode(content, validate=True)
    except Exception:
        frappe.throw("Invalid file content.")
    if len(data) > 10_000_000:
        frappe.throw("Choose a supporting file up to 10 MB.")
    from frappe.utils.file_manager import save_file
    saved = save_file(filename, data, DT, name, is_private=1)
    with writing():
        frappe.get_doc(dict(doctype=EVENT, dcs=doc.dcs, obligation=name, revision=doc.revision,
            action="Supporting document attached", actor=frappe.session.user,
            occurred_on=now_datetime(),reason=filename,
            snapshot=json.dumps({"file":saved.name,"file_url":saved.file_url}))).insert(ignore_permissions=True)
    return {"file_name":saved.file_name,"file_url":saved.file_url}


def delivery_reader(user=None):
    user = user or frappe.session.user
    return user == "manikandan@bitssecureit.com" or "Operations Manager" in frappe.get_roles(user)

@frappe.whitelist(methods=["POST"])
def record_settlement(name, expected_revision, accrued_amount, paid_amount, reference):
    """Records Finance evidence only. Does not create or execute a payment."""
    if frappe.session.user != FINANCE:
        denied()
    dcs = frappe.db.get_value(DT, name, "dcs")
    if not dcs:
        denied()
    sheet = locked(dcs)
    doc = frappe.get_doc(DT, name, for_update=True)
    if doc.revision != int(expected_revision) or not is_current(doc, sheet):
        frappe.throw("Refresh and obtain approval for the current position first.")
    try:
        accrued, paid = float(accrued_amount), float(paid_amount)
    except (TypeError, ValueError):
        frappe.throw("Enter valid settlement amounts.")
    if not all(math.isfinite(v) for v in (accrued,paid)) or not 0 <= paid <= accrued <= doc.approved_amount:
        frappe.throw("Paid must not exceed accrued; accrued must not exceed the approved commitment.")
    if not str(reference or "").strip():
        frappe.throw("Settlement evidence reference is required.")
    doc.accrued_amount = money_round(accrued,doc.currency)
    doc.paid_amount = money_round(paid,doc.currency)
    doc.settlement_reference = reference
    doc.revision += 1
    persist(doc,"Settlement recorded",reference)
    return {"name":name,"revision":doc.revision,"balance":money_round(doc.approved_amount-doc.paid_amount,doc.currency)}

def guard_currency(doc):
    previous = doc.get_doc_before_save()
    if previous and previous.currency != doc.currency and frappe.db.exists(DT,{"dcs":doc.name}):
        frappe.throw("Commercial currency clearance is required before changing currency.")

@frappe.whitelist()
def export_query():
    # System Manager has a framework-level can_export shortcut. Do not rely on it.
    if frappe.form_dict.get("doctype") in (DT, EVENT):
        denied()
    from frappe.desk.reportview import export_query as core
    return core()


@frappe.whitelist()
def export_data(doctype, **kwargs):
    if doctype in (DT, EVENT):
        denied()
    from frappe.core.doctype.data_export.exporter import export_data as core
    return frappe.call(core, doctype=doctype, **kwargs)
