"""BS Procurement uses standard Material Request and Purchase Order documents.

All monetary totals, links, permissions and submitted quantities remain ERPNext's.
The BS-specific fields contain approval/comparison evidence, not parallel orders.
"""
import json
import math
import re
import uuid
from contextlib import contextmanager
from functools import wraps

import frappe
from frappe.utils import cint, flt, get_datetime, now_datetime, nowdate, strip_html
from frappe.model.workflow import (
    apply_workflow, get_transitions, get_workflow_name, has_approval_access,
)
from bsgroup.procurement_controls import (
    business_values, closed_stock_qty, evidence, approval_allowed, track_preparers,
    validate_supplier_details, approver_details,
)

MR = "Material Request"
PO = "Purchase Order"
PREFIX = "custom_bsp_"


def transaction_conflicts(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (frappe.QueryDeadlockError, frappe.QueryTimeoutError):
            # MariaDB snapshot isolation can reject a current read after a
            # competing commit. Do not retry a partially executed transaction.
            fail("PR allocation changed in another session. Refresh and try again.",
                 frappe.TimestampMismatchError)
    return guarded


def fail(message, exception=frappe.ValidationError):
    frappe.throw(message, exception)


def parse(value, default=None):
    if not value:
        return default if default is not None else {}
    return frappe.parse_json(value) if isinstance(value, str) else value


def encoded(value):
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def number(value, label, zero=False):
    try:
        value = float(value)
    except (ValueError, TypeError):
        fail(label + " must be a number.")
    if not math.isfinite(value) or value < 0 or (not zero and value == 0) or value > 1e9:
        fail(label + " is outside the allowed range.")
    return value


def uom_factor(item_code, uom):
    item = frappe.get_cached_doc("Item", item_code)
    if uom == item.stock_uom:
        return 1.0
    factor = next((flt(r.conversion_factor) for r in item.uoms if r.uom == uom), 0)
    if factor <= 0:
        fail("Select a purchase UOM with a positive conversion configured on the Item.")
    return factor


def text(value, limit=4000):
    value = str(value or "").strip()
    if len(value) > limit:
        fail("A text value exceeds the allowed length.")
    return value


def roles():
    return set(frappe.get_roles())


def purchaser():
    return frappe.session.user == "Administrator" or bool(roles() & {"Purchase User", "Purchase Manager"})


def manager():
    return frappe.session.user == "Administrator" or "Purchase Manager" in roles()


def require_purchaser():
    if not purchaser():
        fail("Purchase User or Purchase Manager access is required.", frappe.PermissionError)


def access(doc, permission="read"):
    if frappe.session.user == "Guest":
        fail("Sign in to use BS Procurement.", frappe.PermissionError)
    doc.check_permission(permission)
    # Preserve this site's company selection boundary for direct API calls as well.
    if frappe.session.user != "Administrator":
        from bsgroup.utils.company_access import global_company_condition
        condition = global_company_condition(frappe.session.user, doc.doctype)
        if condition and not frappe.db.sql(
            f"select name from `tab{doc.doctype}` where name=%s and ({condition})",
            (doc.name,),
        ):
            fail("This record is outside your selected company.", frappe.PermissionError)
    return doc


def load(doctype, name, permission="read", modified=None):
    doc = access(frappe.get_doc(doctype, name), permission)
    if modified is not None and get_datetime(modified) != get_datetime(doc.modified):
        fail("This record changed in another session. Refresh before continuing.",
             frappe.TimestampMismatchError)
    return doc


@contextmanager
def operation(action, reason=""):
    previous = getattr(frappe.local, "_bsp_operation", None)
    frappe.local._bsp_operation = (action, text(reason))
    try:
        yield
    finally:
        frappe.local._bsp_operation = previous


def op():
    return getattr(frappe.local, "_bsp_operation", None)


def history(doc):
    return parse(doc.get(PREFIX + "history"), [])


def append_event(doc, action, snapshot=None):
    rows = history(doc)
    rows.append(dict(action=action, at=str(now_datetime()), actor=frappe.session.user,
                     reason=op()[1] if op() else "", snapshot=snapshot))
    doc.custom_bsp_history = encoded(rows)
    if op() and op()[1]:
        doc.custom_bsp_reason = op()[1]


def mr_values(doc):
    return dict(company=doc.company, purpose=doc.material_request_type,
                transaction_date=doc.transaction_date, schedule_date=doc.schedule_date,
                buying_price_list=None if doc.get("custom_bsp_managed") else doc.buying_price_list,
                project=doc.get("custom_project"), dcs=doc.get("custom_deal_cost_sheet"),
                quotation=doc.get("custom_bsp_quotation"), customer=doc.get("custom_bsp_customer") or doc.customer,
                customer_po=doc.get("custom_bsp_customer_po"),
                customer_po_file=doc.get("custom_bsp_customer_po_file"),
                request_evidence=parse(doc.get("custom_bsp_request_evidence")),
                items=[{k:row.get(k) for k in (
                    "name", "item_code", "item_name", "description", "qty", "uom",
                    "conversion_factor", "rate", "warehouse", "project", "schedule_date"
                )} for row in doc.items])


def po_values(doc):
    return dict(document=business_values(doc),
                company=doc.company, supplier=doc.supplier, currency=doc.currency,
                company_tax_id=frappe.get_cached_value("Company", doc.company, "tax_id") or "",
                supplier_tax_id=doc.get("tax_id") or "",
                project=doc.project, cost_center=doc.cost_center,
                conversion_rate=doc.conversion_rate, terms=doc.terms,
                payment_terms_template=doc.payment_terms_template,
                schedule_date=doc.schedule_date, supplier_address=doc.supplier_address,
                contact_person=doc.contact_person, address_display=doc.address_display,
                contact_display=doc.contact_display, contact_email=doc.contact_email,
                contact_mobile=doc.contact_mobile,
                group=doc.get("custom_bsp_group"),
                comparison=parse(doc.get("custom_bsp_comparison")),
                taxes=[{k:r.get(k) for k in ("charge_type", "account_head", "rate",
                        "tax_amount", "included_in_print_rate", "add_deduct_tax",
                        "category", "row_id")} for r in doc.taxes],
                payment_schedule=[{k:r.get(k) for k in ("payment_term", "due_date",
                                  "invoice_portion", "payment_amount")}
                                  for r in doc.payment_schedule],
                discount_amount=doc.discount_amount,
                additional_discount_percentage=doc.additional_discount_percentage,
                items=[{k:r.get(k) for k in ("name", "item_code", "material_request",
                       "material_request_item", "qty", "uom", "conversion_factor",
                       "rate", "warehouse", "project", "cost_center", "expense_account", "schedule_date")}
                       for r in doc.items],
                net_total=doc.net_total, taxes_total=doc.total_taxes_and_charges,
                grand_total=doc.grand_total)


def protected(doc, old, fields):
    for name in fields:
        if old and doc.get(PREFIX + name) != old.get(PREFIX + name) and not op():
            fail("BS approval evidence can only be changed through BS Procurement.")


def prepare_new(doc, method=None):
    # Material Request stores the header project in a custom field. The standard
    # mapper copies row projects but cannot infer this differently named header.
    # Fill it before ERP validation and project commitment checks, including POs
    # created from the native Material Request form.
    if doc.doctype == PO and doc.is_new():
        requests = managed_request_names(doc)
        if len(requests) == 1:
            project = frappe.db.get_value(MR, requests[0], "custom_project")
            if project:
                if doc.project and doc.project != project:
                    fail("The PO project must match its purchase requisition.")
                doc.project = project
    if not doc.is_new() or not doc.get("custom_bsp_managed"):
        return
    if doc.amended_from:
        original = load(doc.doctype, doc.amended_from)
        if original.docstatus != 2 or not original.get("custom_bsp_managed"):
            fail("Amend only a cancelled BS document.")
        doc.custom_bsp_key = str(uuid.uuid4())
        if doc.doctype == PO:
            doc.custom_bsp_approval_state = "Draft"
        else:
            doc.workflow_state = "Draft"
    doc.custom_bsp_history = None
    doc.custom_bsp_reason = None


def validate_request(doc, method=None):
    old = doc.get_doc_before_save()
    if not doc.get("custom_bsp_managed") and not (old and old.get("custom_bsp_managed")):
        return
    # MR.on_update reprices even a newly inserted request when a default
    # buying price list is present. BS rates are the entered approval budget.
    doc.buying_price_list = None
    if not (op() and op()[0] == "handover"):
        require_purchaser()
    if old and not doc.custom_bsp_managed:
        fail("The BS Procurement link cannot be removed.")
    if old and not old.get("custom_bsp_managed"):
        fail("An existing ordinary Material Request cannot be converted into a BS requisition.")
    if doc.material_request_type != "Purchase":
        fail("A BS Purchase Requisition must have purpose Purchase.")
    protected(doc, old, ["history", "reason", "key", "source_snapshot", "request_evidence"])
    if doc.get("custom_bsp_source_snapshot"):
        from bsgroup.dcs.procurement import validate_handover_request
        validate_handover_request(doc, old)
    elif doc.get("custom_bsp_quotation") or doc.get("custom_deal_cost_sheet"):
        fail("Create a quotation/DCS requisition using Send to Procurement; its budget must come from the awarded costing.")
    if not old and not op() and not doc.amended_from:
        fail("Create BS requisitions through BS Procurement.")
    for row in doc.items:
        number(row.qty, "Requested quantity")
        number(row.rate, "Budget rate", zero=True)
    old_state = old.workflow_state if old else None
    state = doc.workflow_state or "Draft"
    if not doc.get("custom_bsp_source_snapshot"):
        from bsgroup.procurement_requests import validate_support
        if not old or old_state in ("Draft", "Rejected") or (
                state != old_state and state in ("Pending Approval", "Approved")):
            validate_support(doc, required=state in ("Pending Approval", "Approved"))
        for row in doc.items:
            if frappe.get_cached_value("Item", row.item_code, "is_stock_item") and not row.warehouse:
                fail("Select a receiving warehouse for stock items.")
    track_preparers(doc, old, state, old_state)
    if old and old_state in ("Pending Approval", "Approved") and encoded(mr_values(old)) != encoded(mr_values(doc)):
        fail("Requested/approved PR lines and source references are locked. Reject or amend the PR first.")
    if state != old_state:
        if state in ("Rejected", "Cancelled") and not (op() and op()[1]):
            fail("Enter a rejection/cancellation reason through BS Procurement.")
        if old:
            transitions = get_transitions(old)
            eligible = [t for t in transitions if t.next_state == state
                        and has_approval_access(frappe.session.user, old, t)]
            if not eligible:
                fail("You cannot perform this PR approval transition.", frappe.PermissionError)
        append_event(doc, state, mr_values(doc))
    for dt, name in (("Quotation", doc.get("custom_bsp_quotation")),
                     ("Deal Cost Sheet", doc.get("custom_deal_cost_sheet"))):
        if name and (not old or old.get("custom_bsp_quotation" if dt == "Quotation" else "custom_deal_cost_sheet") != name):
            source = access(frappe.get_doc(dt, name))
            if source.company != doc.company:
                fail("Source document and requisition must belong to the same company.")


def managed_request_names(doc):
    names = {r.material_request for r in doc.items if r.material_request}
    if doc.get("custom_bsp_material_request"):
        names.add(doc.custom_bsp_material_request)
    return sorted(n for n in names if frappe.db.get_value(MR, n, "custom_bsp_managed"))


def lock_request(name):
    frappe.db.sql("select name from `tabMaterial Request` where name=%s for update", (name,))
    return frappe.get_doc(MR, name)


def order_line_key(row):
    return row.material_request_item or "additional:" + row.name


def append_additional_item(doc, request, values):
    item = access(frappe.get_doc("Item", values.get("item_code")))
    if item.disabled or not item.is_purchase_item:
        fail("Select an enabled purchasable Item.")
    uom = values.get("uom") or item.stock_uom
    warehouse = values.get("warehouse") or doc.get("set_warehouse")
    doc.append("items", dict(item_code=item.name, item_name=item.item_name,
        description=item.description or item.item_name,
        qty=number(values.get("qty"), "Additional item quantity"),
        rate=number(values.get("rate", 0), "Additional item rate", zero=True),
        uom=uom, stock_uom=item.stock_uom, conversion_factor=uom_factor(item.name, uom),
        warehouse=warehouse, project=request.get("custom_project"),
        schedule_date=doc.schedule_date or nowdate()))


def allocation(doc, request):
    """Serialize against the MR and use current reads, including draft reservations."""
    if request.docstatus != 1 or request.workflow_state != "Approved" or request.status in ("Stopped", "Cancelled"):
        fail("The purchase requisition must be approved and open.")
    if doc.company != request.company:
        fail("PO and PR company must match.")
    source = {r.name: r for r in request.items}
    # FOR UPDATE deliberately uses a current read under MariaDB REPEATABLE READ.
    reserved = frappe.db.sql("""
        select i.material_request_item, i.stock_qty, i.received_qty,
               i.conversion_factor, i.billed_amt, i.amount, p.status
        from `tabPurchase Order Item` i join `tabPurchase Order` p on p.name=i.parent
        where i.material_request=%s and p.name!=%s and p.docstatus<2
          and coalesce(p.custom_bsp_approval_state,'')!='Cancelled'
        order by p.name, i.name for update
    """, (request.name, doc.name or ""), as_dict=True)
    used = {}
    for row in reserved:
        used[row.material_request_item] = used.get(row.material_request_item, 0) + (
            closed_stock_qty(row) if row.status == "Closed" else flt(row.stock_qty))
    seen = set()
    for row in doc.items:
        if not row.material_request_item:
            # Additional items belong to this PO's header PR, but do not consume
            # or rewrite any of the approved PR's original item quantities.
            if row.material_request:
                fail("Additional items must not carry an unrelated Material Request link.")
            if row.item_code in {r.item_code for r in request.items}:
                fail("Select the matching PR line for an item already on this requisition.")
            item = frappe.get_cached_doc("Item", row.item_code)
            if item.disabled or not item.is_purchase_item:
                fail("Select an enabled purchasable Item.")
            number(row.qty, "Additional item quantity")
            if abs(flt(row.conversion_factor) - uom_factor(row.item_code, row.uom)) > 1e-9:
                fail("Select a configured purchase UOM for the additional item.")
            if (row.project or "") != (request.get("custom_project") or ""):
                fail("Additional items must use the purchase requisition's project.")
            if item.is_stock_item and not row.warehouse:
                fail("Select a receiving warehouse for the additional stock item.")
            if row.warehouse:
                warehouse = frappe.get_cached_doc("Warehouse", row.warehouse)
                if warehouse.company != request.company or warehouse.disabled or warehouse.is_group:
                    fail("Select an enabled receiving warehouse for the PR company.")
            continue
        ref = source.get(row.material_request_item)
        if not ref or row.material_request != request.name or ref.name in seen:
            fail("Every PO line must reference a different line of this purchase requisition.")
        seen.add(ref.name)
        if row.item_code != ref.item_code or abs(
                flt(row.conversion_factor) - uom_factor(row.item_code, row.uom)) > 1e-9:
            fail("The PO item and configured UOM conversion must match the approved PR scope.")
        quantity = number(row.qty, "PO quantity") * flt(row.conversion_factor)
        available = flt(ref.stock_qty) - used.get(ref.name, 0)
        if quantity > available + 1e-6:
            fail(f"Quantity for {ref.item_code} exceeds the unallocated PR quantity. "
                 f"Available: {max(0, available / flt(ref.conversion_factor))}.")
    if not doc.items:
        fail("Select a PR line or add an additional item.")


def validate_comparison(doc, request):
    data = parse(doc.custom_bsp_comparison)
    if not doc.custom_bsp_group:
        fail("Select a purchase material group.")
    if not text(doc.terms):
        fail("Payment terms are required.")
    if not doc.schedule_date:
        fail("Expected delivery is required.")
    for row in doc.items:
        number(row.rate, "PO unit price")
    if data.get("exception"):
        from bsgroup.procurement_controls import meaningful_reason
        if not meaningful_reason(data.get("explanation")):
            fail("Explain why three supplier quotations are unavailable using meaningful notes "
                 "of at least 15 characters.")
    else:
        quotes = data.get("quotes", [])
        if len(quotes) != 3 or len({q.get("supplier") for q in quotes}) != 3:
            fail("Provide quotations from three different suppliers.")
        if len({q.get("file") for q in quotes}) != 3:
            fail("Attach a separate quotation file for each supplier.")
        hashes = set()
        for quote in quotes:
            supplier = frappe.get_doc("Supplier", quote.get("supplier"))
            supplier.check_permission("read")
            if supplier.disabled:
                fail("A quotation supplier is disabled.")
            file_name = quote.get("file")
            if not file_name or not frappe.db.exists("File", file_name):
                fail("Upload the original quotation for each supplier.")
            file = frappe.get_doc("File", file_name)
            file.check_permission("read")
            if not file.is_private or file.attached_to_doctype != PO or file.attached_to_name != doc.name:
                fail("Quotation files must be private attachments on this Purchase Order.")
            digest = evidence(file)
            if digest in hashes:
                fail("Three quotations must contain three different documents; duplicate content is not allowed.")
            hashes.add(digest)
            for row in doc.items:
                number(quote.get("rates", {}).get(order_line_key(row)), "Quotation line rate")
        chosen = data.get("selected")
        if type(chosen) is not int or chosen not in range(3):
            fail("Choose one of the three supplier quotations.")
        if quotes[chosen]["supplier"] != doc.supplier:
            fail("The PO supplier must match the selected supplier quotation.")
    baseline = {r.name: flt(r.rate)/flt(r.conversion_factor or 1) for r in request.items}
    company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    number(doc.conversion_rate, "Currency conversion rate")
    if doc.currency == company_currency and flt(doc.conversion_rate) != 1:
        fail("The company-currency exchange rate must be 1.")
    for row in doc.items:
        key = order_line_key(row)
        additional = not row.material_request_item
        above = flt(row.rate)*flt(doc.conversion_rate)/flt(row.conversion_factor or 1) > baseline.get(row.material_request_item, 0) + 1e-6
        changed = not data.get("exception") and abs(flt(row.rate) - flt(
            data["quotes"][data["selected"]]["rates"][key])) > 1e-6
        if (additional or above or changed) and len(text(data.get("line_reasons", {}).get(key))) < 15:
            fail(f"Explain each additional item or price variance: {row.item_code} needs its own reason of at least 15 characters.")


def validate_order(doc, method=None):
    old = doc.get_doc_before_save()
    requests = managed_request_names(doc)
    was_managed = old and old.get("custom_bsp_managed")
    if not requests and not doc.get("custom_bsp_managed") and not was_managed:
        # Historical posted orders remain readable and reversible. New orders
        # and existing drafts must enter through an approved BS requisition.
        if old and old.docstatus == 1 and doc.docstatus in (1, 2):
            if doc.docstatus == 1 and encoded(po_values(old)) != encoded(po_values(doc)):
                fail("Historical Purchase Orders without a BS PR cannot be expanded or revised. "
                     "Create a new PO from an approved BS Purchase Requisition.")
            return
        fail("Every new Purchase Order must come from an approved BS Purchase Requisition. "
             "Create the PO from the approved PR in BS Procurement.")
    require_purchaser()
    if old and not was_managed:
        fail("An existing ordinary Purchase Order cannot be converted into a BS order.")
    if was_managed and (not doc.custom_bsp_managed
                        or old.custom_bsp_material_request != doc.custom_bsp_material_request):
        fail("The BS requisition link cannot be changed or removed.")
    if len(requests) != 1:
        fail("A BS Purchase Order must belong to exactly one BS purchase requisition.")
    request = lock_request(requests[0])
    access(request)
    doc.custom_bsp_managed = 1
    doc.custom_bsp_material_request = request.name
    if request.get("custom_project") and doc.project != request.custom_project:
        fail("The PO project must match its purchase requisition.")
    state = doc.custom_bsp_approval_state or "Draft"
    doc.custom_bsp_approval_state = state
    old_state = old.custom_bsp_approval_state if was_managed else "Draft"
    track_preparers(doc, old, state, old_state)
    protected(doc, old, ["history", "reason", "key", "comparison"])
    if state != old_state and not op():
        fail("Use BS Procurement to request, approve, reject or cancel this PO.")
    if not old and state != "Draft":
        fail("New purchase orders must start as Draft.")
    if old and old_state in ("Pending Approval", "Approved", "Cancelled"):
        if encoded(po_values(old)) != encoded(po_values(doc)):
            fail("This PO is locked. Reject it for changes, or cancel and amend an approved order.")
    if state == "Cancelled" and doc.docstatus == 0:
        if old_state not in ("Draft", "Rejected", "Cancelled"):
            fail("Only draft or rejected orders can be withdrawn.")
    else:
        if request.get("custom_bsp_source_snapshot"):
            from bsgroup.dcs.procurement import assert_source_current
            assert_source_current(request)
        allocation(doc, request)
    if state in ("Pending Approval", "Approved"):
        if request.get("custom_project"):
            from bsgroup.utils.project_cost_baseline import get_active_baseline
            if not get_active_baseline(request.custom_project):
                fail("An approved Project Cost Baseline is required before requesting or approving "
                     "this project's Purchase Order.")
        validate_comparison(doc, request)
        if state != old_state:
            validate_supplier_details(doc)
    if state == "Pending Approval" and old_state != state:
        if old_state not in ("Draft", "Rejected"):
            fail("Only draft or rejected orders can be sent for approval.")
        append_event(doc, state, po_values(doc))
    elif state in ("Approved", "Rejected") and state != old_state:
        if not manager() or old_state != "Pending Approval":
            fail("Purchase Manager approval is required.", frappe.PermissionError)
        approval_allowed(doc, throw=True)
        if state == "Rejected" and not (op() and op()[1]):
            fail("A rejection reason is required.")
        append_event(doc, state)
    elif state == "Cancelled" and old_state != state:
        append_event(doc, state)
    if doc.docstatus == 1 and state != "Approved":
        fail("The PO must be approved through BS Procurement before submission.")
    if state == "Approved" and doc.docstatus != 1:
        fail("Approved POs must be submitted standard Purchase Orders.")


def before_cancel(doc, method=None):
    if not doc.get("custom_bsp_managed"):
        return
    if not manager():
        fail("Purchase Manager access is required to cancel.", frappe.PermissionError)
    if not (op() and text(op()[1])):
        fail("A cancellation reason is required. Cancel through BS Procurement.")
    if doc.doctype == MR:
        lock_request(doc.name)
        linked = frappe.db.sql("""
            select p.name from `tabPurchase Order` p join `tabPurchase Order Item` i on i.parent=p.name
            where i.material_request=%s and p.docstatus<2
              and coalesce(p.custom_bsp_approval_state,'')!='Cancelled' limit 1 for update
        """, (doc.name,))
        if linked:
            fail("Cancel or withdraw the linked Purchase Orders before cancelling this requisition.")
        if doc.get("custom_bsp_source_snapshot"):
            # This backlink is historical evidence, not a downstream order.
            # Keep it on the submitted quotation when the PR is cancelled.
            doc.ignore_linked_doctypes = list(set(doc.get("ignore_linked_doctypes") or []) | {"Quotation"})
        append_event(doc, "Cancelled")
    else:
        lock_request(doc.custom_bsp_material_request)
        doc.custom_bsp_approval_state = "Cancelled"
        append_event(doc, "Cancelled")


def before_trash(doc, method=None):
    if doc.get("custom_bsp_managed"):
        fail("Keep the audit trail: withdraw or cancel BS Procurement records instead of deleting them.")


def before_print(doc, method=None, *args, **kwargs):
    if doc.get("custom_bsp_managed") and (
        doc.docstatus != 1 or doc.get("custom_bsp_approval_state") != "Approved"
    ):
        fail("Approve this BS Purchase Order before printing or generating its PDF.")


def guard_item_update(name):
    if frappe.db.get_value(PO, name, "custom_bsp_managed"):
        load(PO, name, "write")
        fail("BS Purchase Order items are protected. Edit a draft, or cancel and amend an approved PO.")


def protect_file(doc, method=None):
    """Once submitted for review, preserve the original quotation evidence."""
    before = doc.get_doc_before_save()
    target = before or doc
    if target.attached_to_doctype not in (MR, PO) or not target.attached_to_name:
        return
    if not frappe.db.get_value(target.attached_to_doctype, target.attached_to_name, "custom_bsp_managed"):
        return
    parent = frappe.get_doc(target.attached_to_doctype, target.attached_to_name)
    if target.attached_to_doctype == MR:
        from bsgroup.procurement_requests import file_references
        references = file_references(parse(parent.get("custom_bsp_request_evidence")))
        for event in history(parent):
            references |= file_references((event.get("snapshot") or {}).get("request_evidence"))
    else:
        references = [q.get("file") for q in parse(parent.custom_bsp_comparison).get("quotes", [])]
        # Earlier submission evidence remains protected after rejection/revision.
        for event in history(parent):
            snapshot = event.get("snapshot") or {}
            references += [q.get("file") for q in snapshot.get("comparison", {}).get("quotes", [])]
    if doc.name and doc.name in references and (method == "on_trash" or
            any(doc.has_value_changed(k) for k in ("file_url", "file_name", "content_hash", "file_size",
                  "is_private", "attached_to_name", "attached_to_doctype")) or doc.get("content")):
        fail("This file is procurement evidence. Upload a new file to revise it; keep the original for the audit trail.")


def normalize_comparison(data):
    data = parse(data)
    result = dict(exception=bool(data.get("exception")), explanation=text(data.get("explanation")),
                  selection_reason=text(data.get("selection_reason")), selected=data.get("selected"),
                  quotes=[])
    reasons = data.get("line_reasons") or {}
    if not isinstance(reasons, dict) or len(reasons) > 100:
        fail("Invalid per-line reasons.")
    result["line_reasons"] = {text(k, 140): text(v) for k, v in reasons.items()}
    quotes = data.get("quotes", [])
    if not isinstance(quotes, list) or len(quotes) > 3:
        fail("A comparison can have at most three supplier quotations.")
    for quote in quotes:
        rates = quote.get("rates", {})
        if not isinstance(rates, dict) or len(rates) > 100:
            fail("Invalid quotation rates.")
        result["quotes"].append(dict(supplier=text(quote.get("supplier"), 140),
                                    file=text(quote.get("file"), 140),
                                    rates={text(k,140): number(v, "Quotation rate", zero=True) for k,v in rates.items()}))
    return result


def creation_key(value):
    if not re.fullmatch(r"[a-zA-Z0-9-]{16,80}", str(value or "")):
        fail("Missing or invalid creation key. Refresh and try again.")
    return value


@frappe.whitelist(methods=["POST"])
@transaction_conflicts
def create_request(payload):
    require_purchaser()
    data = parse(payload)
    if data.get("quotation") or data.get("dcs"):
        fail("Use Send to Procurement for quotation/DCS requisitions and their awarded budget.")
    key = creation_key(data.get("key"))
    existing = frappe.db.get_value(MR, {"custom_bsp_key": key})
    if existing:
        return request_data(access(frappe.get_doc(MR, existing)))
    items = data.get("items", [])
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        fail("Enter between one and 100 requisition lines.")
    doc = frappe.new_doc(MR)
    from bsgroup.procurement_requests import normalize
    doc.update(dict(material_request_type="Purchase", company=data.get("company"),
                    schedule_date=data.get("schedule_date"), transaction_date=nowdate(),
                    custom_bsp_managed=1, custom_bsp_key=key,
                    custom_project=data.get("project"), custom_bsp_customer=data.get("customer"),
                    custom_bsp_customer_po=text(data.get("customer_po")),
                    custom_bsp_quotation=data.get("quotation"),
                    custom_deal_cost_sheet=data.get("dcs"),
                    custom_bsp_request_evidence=encoded(normalize(data.get("supporting"))),
                    title=text(data.get("title") or "Purchase", 140)))
    # Standard item master supplies description and UOM; no free-form fake items.
    for row in items:
        item = frappe.get_doc("Item", row.get("item_code"))
        item.check_permission("read")
        if item.disabled or not item.is_purchase_item:
            fail("Select enabled purchasable items.")
        uom = row.get("uom") or item.stock_uom
        doc.append("items", dict(item_code=item.name, item_name=item.item_name,
                   description=item.description or item.item_name,
                   qty=number(row.get("qty"), "Requested quantity"),
                   rate=number(row.get("rate", 0), "Budget rate", zero=True),
                   uom=uom, stock_uom=item.stock_uom, conversion_factor=uom_factor(item.name, uom),
                   warehouse=row.get("warehouse") or data.get("warehouse"),
                   project=data.get("project"), schedule_date=doc.schedule_date))
    with operation("create"):
        doc.insert()
    access(doc)
    return request_data(doc)


@frappe.whitelist(methods=["POST"])
@transaction_conflicts
def save_request_evidence(name, modified, payload):
    require_purchaser()
    doc = load(MR, name, "write", modified)
    if (not doc.custom_bsp_managed or doc.get("custom_bsp_source_snapshot") or doc.docstatus
            or doc.workflow_state not in ("Draft", "Rejected")):
        fail("Supporting documents can only be edited on draft or rejected manual PRs.")
    from bsgroup.procurement_requests import normalize
    doc.custom_bsp_request_evidence = encoded(normalize(payload))
    with operation("save-request-evidence"):
        doc.save()
    return request_data(doc)


@frappe.whitelist(methods=["POST"])
@transaction_conflicts
def request_action(name, modified, action, reason=""):
    require_purchaser()
    doc = load(MR, name, "write", modified)
    if not doc.custom_bsp_managed:
        fail("This requisition is not managed by BS Procurement.")
    if action not in ("Send for Approval", "Approve", "Reject", "Cancel"):
        fail("Invalid approval action.")
    if action in ("Reject", "Cancel") and not text(reason):
        fail("A rejection/cancellation reason is required.")
    if action in ("Approve", "Reject"):
        approval_allowed(doc, throw=True)
    with operation(action, reason):
        result = apply_workflow(doc, action)
    return request_data(result)


@frappe.whitelist(methods=["POST"])
@transaction_conflicts
def create_order(request, modified, supplier, lines, key, additional_items=None):
    require_purchaser()
    key = creation_key(key)
    existing = frappe.db.get_value(PO, {"custom_bsp_key": key})
    if existing:
        return order_data(access(frappe.get_doc(PO, existing)))
    source = load(MR, request, "read", modified)
    if not source.custom_bsp_managed:
        fail("Select a BS Procurement requisition.")
    lock_request(source.name)
    supplier_doc = access(frappe.get_doc("Supplier", supplier))
    if supplier_doc.disabled:
        fail("Select an enabled supplier.")
    quantities = parse(lines)
    additional = parse(additional_items, [])
    if (not isinstance(quantities, dict) or not isinstance(additional, list)
            or not quantities and not additional or len(quantities) + len(additional) > 100):
        fail("Select PR lines or add additional items, up to 100 lines per PO.")
    for row, qty in quantities.items():
        number(qty, "PO quantity")
        if row not in {i.name for i in source.items}:
            fail("Invalid requisition line.")
    from erpnext.stock.doctype.material_request.material_request import make_purchase_order
    if quantities:
        doc = make_purchase_order(source.name, args=dict(
            supplier=supplier, filtered_children=list(quantities), requested_qty=quantities))
    else:
        doc = frappe.new_doc(PO)
        doc.update(dict(company=source.company, supplier=supplier,
                        transaction_date=nowdate(), project=source.get("custom_project")))
    if {row.material_request_item for row in doc.items} != set(quantities):
        fail("One or more selected lines have no unallocated PR quantity. Refresh the requisition.")
    doc.custom_bsp_managed = 1
    doc.custom_bsp_material_request = source.name
    doc.custom_bsp_key = key
    doc.custom_bsp_approval_state = "Draft"
    doc.custom_bsp_comparison = encoded(normalize_comparison({}))
    doc.currency = frappe.get_cached_value("Company", source.company, "default_currency")
    doc.conversion_rate = 1
    doc.schedule_date = source.schedule_date or nowdate()
    for row in doc.items:
        row.schedule_date = max(str(row.schedule_date or nowdate()), nowdate())
    doc.schedule_date = max(str(doc.schedule_date), nowdate())
    for values in additional:
        if not isinstance(values, dict):
            fail("Invalid additional item.")
        append_additional_item(doc, source, values)
    if additional:
        doc.set_missing_values()
    # Check under the MR lock before ERPNext consumes a naming-series number.
    # A competing request then gets a useful allocation error, not a series race.
    allocation(doc, source)
    with operation("create"):
        doc.insert()
    return order_data(doc)


@frappe.whitelist(methods=["POST"])
@transaction_conflicts
def add_order_item(name, modified, item_code, qty, rate=0, uom=None, warehouse=None):
    require_purchaser()
    doc = load(PO, name, "write", modified)
    if not doc.custom_bsp_managed or doc.custom_bsp_approval_state not in ("Draft", "Rejected") or doc.docstatus:
        fail("Additional items can only be added to draft or rejected BS Purchase Orders.")
    source = access(lock_request(doc.custom_bsp_material_request))
    if len(doc.items) >= 100:
        fail("A PO can contain at most 100 lines.")
    append_additional_item(doc, source, dict(item_code=item_code, qty=qty,
                                           rate=rate, uom=uom, warehouse=warehouse))
    doc.set_missing_values()
    with operation("add item"):
        doc.save()
    return order_data(doc, source)


@frappe.whitelist(methods=["POST"])
@transaction_conflicts
def save_order(name, modified, payload):
    require_purchaser()
    doc = load(PO, name, "write", modified)
    if not doc.custom_bsp_managed or doc.custom_bsp_approval_state not in ("Draft", "Rejected") or doc.docstatus:
        fail("Only draft or rejected BS orders can be edited.")
    data = parse(payload)
    incoming = data.get("items", [])
    current = {order_line_key(r): r for r in doc.items}
    if not incoming or len(incoming) > 100:
        fail("Keep at least one PO line.")
    seen = set()
    rows = []
    for value in incoming:
        source = value.get("sourceId")
        if source not in current or source in seen:
            fail("Invalid or duplicate source line.")
        seen.add(source)
        row = current[source]
        row.qty = number(value.get("qty"), "PO quantity")
        row.rate = number(value.get("rate"), "PO unit price", zero=True)
        row.uom = value.get("uom") or row.uom
        row.conversion_factor = uom_factor(row.item_code, row.uom)
        row.schedule_date = data.get("delivery") or row.schedule_date
        rows.append(row)
    doc.set("items", rows)
    doc.terms = text(data.get("terms"))
    doc.schedule_date = data.get("delivery") or doc.schedule_date
    doc.custom_bsp_group = data.get("group")
    doc.custom_bsp_comparison = encoded(normalize_comparison(data.get("comparison")))
    if data.get("currency"):
        access(frappe.get_doc("Currency", data["currency"]))
        doc.currency = data["currency"]
        doc.conversion_rate = number(data.get("conversionRate", doc.conversion_rate), "Currency conversion rate")
    # Supplier is a standard master link, validated by ERPNext as well.
    if data.get("supplier") and data["supplier"] != doc.supplier:
        access(frappe.get_doc("Supplier", data["supplier"]))
        doc.supplier = data["supplier"]
        doc.supplier_address = None
        doc.contact_person = None
        doc.address_display = None
        doc.contact_display = None
        doc.contact_email = None
        doc.contact_mobile = None
        doc.run_method("set_missing_values")
    with operation("save"):
        doc.save()
    return order_data(doc)


@frappe.whitelist(methods=["POST"])
@transaction_conflicts
def order_action(name, modified, action, reason=""):
    require_purchaser()
    doc = load(PO, name, "write", modified)
    if not doc.custom_bsp_managed:
        fail("This is not a BS Procurement Purchase Order.")
    states = {"Send for Approval": "Pending Approval", "Approve": "Approved",
              "Reject": "Rejected", "Cancel": "Cancelled"}
    if action not in states:
        fail("Invalid PO action.")
    if action in ("Reject", "Cancel") and not text(reason):
        fail("A rejection/cancellation reason is required.")
    with operation(action, reason):
        if action == "Cancel" and doc.docstatus == 1:
            doc.cancel()
        else:
            doc.custom_bsp_approval_state = states[action]
            if action == "Approve":
                doc.submit()
            else:
                doc.save()
    return order_data(doc)


def order_data(doc, source=None):
    access(doc)
    source = source or access(frappe.get_doc(MR, doc.custom_bsp_material_request))
    baseline = {r.name: r for r in source.items}
    comparison = parse(doc.custom_bsp_comparison)
    quotes = comparison.get("quotes", [])
    quotes = quotes + [dict(supplier="", file="", rates={}) for _ in range(3-len(quotes))]
    files = {f.name: f for f in frappe.get_all("File",
        filters={"name": ["in", [q["file"] for q in quotes if q.get("file")] or [""]]},
        fields=["name", "file_name", "file_url"])}
    for q in quotes:
        f = files.get(q.get("file"))
        q["filename"], q["url"] = (f.file_name, f.file_url) if f else ("", "")
    state = "Cancelled" if doc.docstatus == 2 else doc.custom_bsp_approval_state or "Draft"
    editable = purchaser() and doc.has_permission("write") and state in ("Draft", "Rejected") and not doc.docstatus
    can_approve = manager() and state == "Pending Approval" and doc.has_permission("submit") and approval_allowed(doc)
    return dict(id=doc.name, modified=str(doc.modified), status=state,
                erpStatus="Withdrawn" if state == "Cancelled" and not doc.docstatus else doc.status,
                docstatus=doc.docstatus, request=source.name, company=doc.company,
                currency=doc.currency, conversionRate=doc.conversion_rate,
                companyCurrency=frappe.get_cached_value("Company", doc.company, "default_currency"),
                supplier=doc.supplier, group=doc.custom_bsp_group or "",
                contact=doc.contact_display or "", email=doc.contact_email or "",
                phone=doc.contact_mobile or "", address=doc.address_display or "",
                terms=doc.terms or "", delivery=str(doc.schedule_date or ""),
                net=doc.net_total, taxes=doc.total_taxes_and_charges, grand=doc.grand_total,
                na=bool(comparison.get("exception")), explanation=comparison.get("explanation",""),
                selectionReason=comparison.get("selection_reason",""),
                lineReasons=comparison.get("line_reasons", {}),
                selectedQuote=comparison.get("selected"), quotes=quotes,
                reason=doc.custom_bsp_reason or "", history=history(doc),
                editable=editable, canApprove=can_approve, approver=approver_details(),
                canCancel=editable or (manager() and doc.docstatus==1 and doc.has_permission("cancel")),
                items=[dict(sourceId=order_line_key(r), additional=not bool(r.material_request_item), item_code=r.item_code,
                            item_name=r.item_name, description=strip_html(r.description or r.item_name or ""), qty=r.qty, uom=r.uom,
                            rate=r.rate, conversionFactor=r.conversion_factor,
                            uoms=sorted({frappe.get_cached_doc("Item", r.item_code).stock_uom}
                                | {u.uom for u in frappe.get_cached_doc("Item", r.item_code).uoms if flt(u.conversion_factor)>0}),
                            uomFactors={frappe.get_cached_doc("Item", r.item_code).stock_uom: 1,
                                **{u.uom: flt(u.conversion_factor) for u in frappe.get_cached_doc("Item", r.item_code).uoms if flt(u.conversion_factor)>0}},
                            cost=(flt(baseline[r.material_request_item].rate)
                                 / flt(baseline[r.material_request_item].conversion_factor or 1)
                                 * flt(r.conversion_factor or 1) / flt(doc.conversion_rate or 1))
                                 if r.material_request_item in baseline else 0)
                       for r in doc.items])


def request_data(doc):
    access(doc)
    source = parse(doc.get("custom_bsp_source_snapshot"))
    from bsgroup.procurement_requests import support_data
    names = frappe.get_list(PO, filters={"custom_bsp_material_request":doc.name,
                                        "custom_bsp_managed":1}, pluck="name", limit_page_length=0,
                            order_by="creation asc") if frappe.has_permission(PO, "read") else []
    orders = [order_data(frappe.get_doc(PO, name), source=doc) for name in names]
    # Availability must include reservations in POs the user cannot open.
    reserved = frappe.db.sql("""
        select i.material_request_item, i.stock_qty, i.received_qty,
               i.conversion_factor, i.billed_amt, i.amount, p.status, p.docstatus
        from `tabPurchase Order Item` i join `tabPurchase Order` p on p.name=i.parent
        where i.material_request=%s and p.docstatus<2
          and coalesce(p.custom_bsp_approval_state,'')!='Cancelled'
    """, (doc.name,), as_dict=True)
    used, ordered = {}, {}
    for row in reserved:
        effective = closed_stock_qty(row) if row.status == "Closed" else flt(row.stock_qty)
        used[row.material_request_item] = used.get(row.material_request_item, 0) + effective
        if row.docstatus == 1:
            ordered[row.material_request_item] = ordered.get(row.material_request_item, 0) + effective
    actions = []
    if get_workflow_name(MR):
        actions = [t.action for t in get_transitions(doc) if has_approval_access(frappe.session.user, doc, t)
                   and (t.action not in ("Approve", "Reject") or approval_allowed(doc))]
    approval = "Cancelled" if doc.docstatus==2 else doc.workflow_state or "Draft"
    items = [dict(sourceId=r.name, item_code=r.item_code, item_name=r.item_name,
                  description=strip_html(r.description or r.item_name or ""),
                  qty=r.qty, uom=r.uom, cost=r.rate, ordered=ordered.get(r.name, 0)/flt(r.conversion_factor or 1),
                  reserved=used.get(r.name,0)/flt(r.conversion_factor or 1),
                  available=max(0,(flt(r.stock_qty)-used.get(r.name,0))/flt(r.conversion_factor or 1)))
             for r in doc.items]
    status = "Cancelled" if approval=="Cancelled" else "Not started"
    if approval=="Approved":
        if doc.status=="Stopped":
            status="Stopped"
        elif items and all(r["ordered"] >= r["qty"]-1e-6 for r in items):
            status="Fully ordered"
        elif any(r["ordered"] for r in items):
            status="Partially ordered"
        elif any(p["status"]=="Pending Approval" for p in orders):
            status="Awaiting PO approval"
        elif any(p["status"]!="Cancelled" for p in orders):
            status="Sourcing / PO preparation"
        else:
            status="Ready for procurement"
    prepare_reason = ("Mohan must approve this PR before a Purchase Order can be created."
        if approval != "Approved" or doc.docstatus != 1 else
        "This PR is stopped or cancelled." if doc.status in ("Stopped", "Cancelled") else
        "Purchase User or Purchase Manager access and Purchase Order creation permission are required."
        if not purchaser() or not frappe.has_permission(PO, "create") else "")
    return dict(id=doc.name, modified=str(doc.modified), person=doc.owner,
                company=doc.company, currency=frappe.get_cached_value("Company",doc.company,"default_currency"),
                project=doc.get("custom_project") or doc.title, customer=doc.get("custom_bsp_customer") or doc.customer or "",
                quotation=doc.get("custom_bsp_quotation") or "", dcs=doc.get("custom_deal_cost_sheet") or "",
                customerPO=doc.get("custom_bsp_customer_po") or "",
                customerPOFile=doc.get("custom_bsp_customer_po_file") or "",
                handoverRevision=source.get("costing", {}).get("revision", ""),
                handoverFiles=source.get("files", []),
                handoverResources=len(source.get("costing", {}).get("resources", [])),
                handoverCharges=len(source.get("costing", {}).get("additional_charges", [])),
                approval=approval, purchasing=status, erpStatus=doc.status, approver=approver_details(),
                reason=doc.get("custom_bsp_reason") or "", items=items, orders=orders,
                actions=actions, history=history(doc),
                supporting=support_data(doc), manual=not bool(source),
                canEditSupporting=not source and not doc.docstatus
                    and (doc.workflow_state or "Draft") in ("Draft", "Rejected")
                    and purchaser() and doc.has_permission("write"),
                canPrepare=not bool(prepare_reason), prepareReason=prepare_reason)


@frappe.whitelist()
def get_requests(start=0, page_length=50):
    if frappe.session.user == "Guest":
        fail("Please sign in.", frappe.PermissionError)
    from bsgroup.procurement_lists import list_requests
    return list_requests(start, page_length)


@frappe.whitelist()
def get_orders(start=0, page_length=50, search=""):
    from bsgroup.procurement_lists import list_orders
    return list_orders(start, page_length, search)


@frappe.whitelist()
def get_request(name):
    return request_data(load(MR, name))


@frappe.whitelist()
def pdf(name):
    doc = load(PO, name, "print")
    if not doc.custom_bsp_managed or doc.docstatus!=1 or doc.custom_bsp_approval_state!="Approved":
        fail("Only approved, submitted BS Purchase Orders can be issued as PDF.")
    from frappe.utils.print_format import download_pdf
    return download_pdf(PO, doc.name, format="Purchase Order Print Format",
                        no_letterhead=0, letterhead="Order Letterhead")
