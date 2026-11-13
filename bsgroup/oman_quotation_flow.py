"""Opt-in Oman pilot. Draft quotations follow their DCS; terminal offers stay frozen.

Activation installs only the pilot's fields/options, never roles or purchasing rules.
All writes use existing document permissions and governed DCS/procurement services.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import inspect
import json

import frappe
from frappe.utils import cint, flt, now_datetime, today

OMAN_SITES = {"erp-om.k.frappe.cloud"}
UAE_SITES = {"erp-bitssecureit.u.frappe.cloud"}
UAE_FLAG = "bs_uae_quotation_flow"
FLAG = "bs_oman_quotation_flow"
SOURCE_PRINT_FORMAT = "Enterprise Quotation - Class A - OM"
PILOT_PRINT_FORMAT = "Enterprise Quotation - Oman Pilot"
PDF_TEMPLATE_FIELD = "custom_oman_pdf_template"
TERMINAL = {"Won", "Lost"}
STAGES = {"Draft", "Sent", "Follow-up", "Delayed", "Cancelled", "Expired", "Won", "Lost"}
_operation = ContextVar("oman_quote_operation", default=None)


def enabled():
    site = getattr(frappe.local, "site", None)
    flag = UAE_FLAG if site in UAE_SITES else FLAG if site in OMAN_SITES else None
    return bool(flag and cint(frappe.defaults.get_global_default(flag)) == 1)


def uae():
    return getattr(frappe.local, "site", None) in UAE_SITES


def setup_authorised():
    if uae():
        return frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles()
    return getattr(frappe.local, "site", None) in OMAN_SITES and frappe.session.user == "Administrator"


def print_formats():
    return ("EnterPrise Quotation 3", "Enterprise Quotation - UAE Workflow") if uae() else (SOURCE_PRINT_FORMAT, PILOT_PRINT_FORMAT)


def template_selection_enabled():
    return enabled()


def validate_pdf_template(template):
    if template == "Standard":
        return template
    settings = frappe.db.get_value("Print Format", template, ["doc_type", "disabled"], as_dict=True) if template else None
    if not settings or settings.doc_type != "Quotation" or cint(settings.disabled):
        frappe.throw("Choose an enabled Quotation template before creating the PDF.")
    return template


@frappe.whitelist()
def pdf_templates(quotation):
    q = _quotation(quotation)
    q.check_permission("print")
    if not template_selection_enabled():
        frappe.throw("Quotation template selection is not enabled on this site.")
    templates = ["Standard"] + frappe.get_all("Print Format", filters={"doc_type": "Quotation", "disabled": 0},
        pluck="name", order_by="name asc")
    selected = q.get(PDF_TEMPLATE_FIELD) or print_formats()[1]
    return dict(templates=templates, selected=selected if selected in templates else "")


def active_quotes(sheet):
    return frappe.get_all("Quotation", filters={"custom_deal_cost_sheet": sheet.name,
        "docstatus": ["!=", 2]}, pluck="name")


def require_single_quote(sheet):
    if len(active_quotes(sheet)) > 1:
        frappe.throw("This DCS has multiple active quotations. Review and resolve the existing quotation links before creating, revising or finalising a quotation. No records were changed.")


def pilot(q):
    previous = q.get_doc_before_save()
    return bool(enabled() and q.get("custom_deal_cost_sheet")
                and (q.docstatus == 0 or q.get("custom_oman_flow")
                     or (previous and previous.get("custom_oman_flow"))))


def before_validate(q, method=None):
    """Choose the tax-exclusive basis before ERPNext calculates amounts.

    Keep the entered percentage / amount and let the native tax engine allocate
    the discount and recalculate VAT, currency conversions and rounding.
    Historical submitted offers retain their saved financial position.
    """
    if not pilot(q) or q.docstatus == 2:
        return
    previous = q.get_doc_before_save()
    if previous and previous.docstatus != 0:
        return
    if q.docstatus != 0 and not previous:
        return
    q.apply_discount_on = "Net Total"


def discount_basis_ready(q):
    return (q.docstatus != 0 or not (
        flt(q.get("discount_amount")) or flt(q.get("additional_discount_percentage")))
        or q.get("apply_discount_on") == "Net Total")


def require_net_discount(q, method=None, print_settings=None):
    if pilot(q) and not discount_basis_ready(q):
        frappe.throw("Save this quotation to apply its discount before VAT, then review the totals before creating a PDF.")


@contextmanager
def operation(q, action):
    token = _operation.set((q.name, action))
    try:
        yield
    finally:
        _operation.reset(token)


def check_editable(q):
    if q.docstatus != 0 or q.custom_pipeline_stage in TERMINAL:
        frappe.throw("Only an open Draft quotation can be revised. Won, Lost and submitted quotations are frozen.")
    if q.get("custom_bsp_material_request") or q.get("custom_purchase_request"):
        frappe.throw("This quotation was already handed over to Procurement.")


def snapshot(q, label):
    # Version is the native private audit store. Snapshots retain the complete
    # quotation, including terms/taxes, rather than only the changed BOQ values.
    frappe.get_doc(dict(doctype="Version", ref_doctype="Quotation", docname=q.name,
        data=frappe.as_json({"changed": [], "added": [], "removed": [], "row_changed": [], "oman_quotation_revision": {
            "revision": cint(q.get("custom_oman_revision_no")), "event": label,
            "dcs_revision": q.get("custom_dcs_revision_reference"),
            "quotation": q.as_dict()}}))).insert(ignore_permissions=True)
    q.add_comment("Info", f"Quotation R{cint(q.get('custom_oman_revision_no'))}: {label}")


def ensure_draft(sheet):
    """DCS row lock makes concurrent submit/retry/create actions idempotent."""
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import (
        _create_quotation, quotation_deal_identity, refuse_stale_quotation_source)
    sheet = frappe.get_doc("Deal Cost Sheet", sheet.name, for_update=True)
    refuse_stale_quotation_source(sheet)
    names = frappe.get_all("Quotation", filters={"custom_deal_cost_sheet": sheet.name,
        "docstatus": ["!=", 2]}, pluck="name")
    if len(names) > 1:
        frappe.throw("This DCS already has multiple quotations. Review its existing links before using the Oman flow.")
    name = sheet.custom_quotation or (names[0] if names else None)
    if name:
        q = frappe.get_doc("Quotation", name, for_update=True)
        q.check_permission("read")
        if q.docstatus == 2 or q.custom_deal_cost_sheet != sheet.name or quotation_deal_identity(sheet, q):
            frappe.throw("The existing quotation link does not match this DCS. No new quotation was created.")
        if names and names[0] != name:
            frappe.throw("The DCS quotation links conflict. No new quotation was created.")
    else:
        name = _create_quotation(sheet)
        q = frappe.get_doc("Quotation", name)
        snapshot(q, "Created from submitted DCS")
    if sheet.custom_quotation != name:
        frappe.db.set_value("Deal Cost Sheet", sheet.name, "custom_quotation", name)
        sheet.custom_quotation = name
    return name


def dcs_submitted(doc, method=None):
    if enabled():
        ensure_draft(doc)


def linked_quotation(sheet, strict=False):
    if uae() and len(active_quotes(sheet)) > 1:
        if strict:
            require_single_quote(sheet)
        return None
    if sheet.custom_quotation:
        return sheet.custom_quotation
    names = frappe.get_all("Quotation", filters={"custom_deal_cost_sheet": sheet.name,
        "docstatus": ["!=", 2]}, pluck="name")
    if len(names) > 1:
        if strict:
            frappe.throw("This DCS has multiple quotations and no current quotation link. Review the links before revising; no quotation was changed.")
        return None
    return names[0] if names else None


def guard_dcs_revision(sheet, attach=False):
    if not enabled():
        return False
    name = linked_quotation(sheet, strict=True)
    if not name:
        return False
    q = frappe.get_doc("Quotation", name, for_update=True)
    if pilot(q):
        check_editable(q)
        if attach:
            from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_deal_identity
            q.check_permission("write")
            if q.custom_deal_cost_sheet != sheet.name or quotation_deal_identity(sheet, q):
                frappe.throw("The existing quotation does not match this DCS. Its link was not changed.")
            if not sheet.custom_quotation:
                frappe.db.set_value("Deal Cost Sheet", sheet.name, "custom_quotation", name)
                sheet.custom_quotation = name
        return True
    return False


def sync_draft(sheet, previous_sheet=None):
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_deal_identity
    from bsgroup.dcs.currency import money_tolerance
    q = frappe.get_doc("Quotation", sheet.custom_quotation, for_update=True)
    q.check_permission("write")
    check_editable(q)
    if q.custom_deal_cost_sheet != sheet.name or quotation_deal_identity(sheet, q) or q.currency != sheet.currency:
        frappe.throw("The quotation identity or currency differs from this DCS. Revision was not saved.")
    snapshot(q, "Before DCS revision")
    from bsgroup import oman_item_description as descriptions
    wording = descriptions.preserved_wording(q, previous_sheet or sheet)
    rows = []
    for row in sheet.items:
        item = frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom"], as_dict=True)
        description = row.description or (row.item_name if row.exclude_item_name_and_brand else
            " - ".join(str(v) for v in (row.brand, row.item_code, row.item_name) if v)) or item.item_name
        customer_text = wording.get(row.name)
        use_costing = customer_text[2] if customer_text and customer_text[0] == row.item_code else 1
        rows.append(dict(item_code=row.item_code, item_name=row.item_name or item.item_name,
            brand=row.brand, uom=item.stock_uom, stock_uom=item.stock_uom, conversion_factor=1,
            description=description, custom_header=row.header,
            custom_oman_dcs_row=row.name,
            custom_oman_client_description=customer_text[1] if customer_text and customer_text[0] == row.item_code else "",
            custom_oman_use_costing_description=use_costing,
            custom_oman_use_co_description=0 if use_costing else 1,
            custom_exclude_item_name_and_brand=row.exclude_item_name_and_brand,
            qty=row.qty, custom_cost_rate=row.cost_rate, custom_selling_rate=row.selling_rate,
            price_list_rate=row.selling_rate, discount_percentage=0, rate=row.selling_rate))
    charges = sum(flt(r.get("selling_amount")) for r in sheet.addtional_charges or [])
    if charges:
        code = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
        if not code:
            frappe.throw("Configure the existing DCS Additional Item before synchronising charges.")
        item = frappe.db.get_value("Item", code, ["item_name", "stock_uom"], as_dict=True)
        customer_text = wording.get(descriptions.ADDITIONAL)
        use_costing = customer_text[2] if customer_text and customer_text[0] == code else 1
        rows.append(dict(item_code=code, item_name=item.item_name, description=item.item_name,
            custom_oman_dcs_row=descriptions.ADDITIONAL,
            custom_oman_client_description=customer_text[1] if customer_text and customer_text[0] == code else "",
            custom_oman_use_costing_description=use_costing,
            custom_oman_use_co_description=0 if use_costing else 1,
            qty=1, uom=item.stock_uom, stock_uom=item.stock_uom, conversion_factor=1,
            rate=charges, price_list_rate=charges, discount_percentage=0))
    q.set("items", rows)
    q.custom_oman_flow = 1
    q.custom_oman_revision_no = cint(q.get("custom_oman_revision_no")) + 1
    q.flags.ignore_mandatory = True  # Incomplete commercial details remain a Draft.
    with operation(q, "revise"):
        q.save()
    if abs(flt(q.total) - flt(sheet.total_selling)) > money_tolerance(sheet.currency):
        frappe.throw("Quotation discounts or pricing rules changed the DCS total. The revision was not saved.")
    snapshot(q, "After DCS revision")
    return f"Quotation {q.name} updated in place · R{q.custom_oman_revision_no}."


def validate(q, method=None):
    if not pilot(q):
        return
    if uae():
        sheet = frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet, for_update=True)
        require_single_quote(sheet)
        if q.is_new() and active_quotes(sheet):
            frappe.throw("A quotation already exists for this DCS. Open the existing quotation; use Revise Costing Sheet for changes.")
    before = q.get_doc_before_save()
    if before and before.custom_pipeline_stage in TERMINAL:
        frappe.throw("Won and Lost quotations are frozen; they cannot be edited or reopened.")
    if q.docstatus == 2:
        frappe.throw("Use the commercial Cancelled status; native cancellation is outside the editable pilot flow.")
    action = _operation.get()
    allowed = action and action[0] == q.name
    if before and before.docstatus == 0 and q.docstatus == 1 and (not allowed or action[1] != "status"):
        frappe.throw("Use Change Status → Won or Lost to finalise an managed quotation.")
    if before and before.docstatus == 1 and not before.get("custom_oman_flow"):
        frappe.throw("Historical submitted quotations cannot be enrolled in the draft pilot.")
    if before and before.get("custom_oman_flow") and not q.get("custom_oman_flow"):
        frappe.throw("The Quotation workflow flag cannot be cleared.")
    if not before and cint(q.get("custom_oman_revision_no")):
        frappe.throw("New quotations must start at revision R0.")
    if before and cint(q.get("custom_oman_revision_no")) != cint(before.get("custom_oman_revision_no")):
        if not allowed or action[1] != "revise":
            frappe.throw("Quotation revision numbers are managed by the DCS revision service.")
    if before and q.custom_pipeline_stage != before.custom_pipeline_stage and not allowed:
        frappe.throw("Use Change Status to preserve the quotation and procurement controls.")
    q.custom_oman_flow = 1
    from bsgroup.oman_item_description import prepare
    prepare(q)


def validate_stage(q):
    if not pilot(q):
        return False
    stage = q.custom_pipeline_stage or "Draft"
    if stage not in STAGES:
        frappe.throw("Invalid quotation status.")
    before = q.get_doc_before_save()
    if before and before.custom_pipeline_stage in TERMINAL and before.custom_pipeline_stage != stage:
        frappe.throw("Won and Lost quotations cannot be reopened in this workflow.")
    if stage in TERMINAL and q.docstatus != 1:
        frappe.throw("The quotation must pass native submission checks before Won or Lost is recorded.")
    if stage in {"Lost", "Cancelled", "Delayed"} and not (q.custom_lost_reason or "").strip():
        frappe.throw("A reason is required for Lost, Delayed or Cancelled.")
    q.custom_won_date = today() if stage == "Won" else None
    q.custom_lost_date = today() if stage in {"Lost", "Cancelled"} else None
    if stage not in {"Lost", "Cancelled", "Delayed"}:
        q.custom_lost_reason = None
    return True


def guard_cancel(q, method=None):
    if pilot(q):
        frappe.throw("Use the commercial Cancelled status for editable quotations. Won and Lost quotations remain frozen.")


def _quotation(name, write=False, lock=False):
    q = frappe.get_doc("Quotation", name, for_update=lock)
    q.check_permission("write" if write else "read")
    if not pilot(q):
        frappe.throw("This workflow applies only to new/Draft quotations and quotations created through this workflow.")
    if uae() and (write or lock):
        require_single_quote(frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet))
    return q


@frappe.whitelist()
def context(quotation):
    q = frappe.get_doc("Quotation", quotation)
    q.check_permission("read")
    if not pilot(q):
        return {"enabled": False, "can_install": can_install(), "workflow_label": "UAE Quotation Workflow" if uae() else "Oman Quotation Pilot"}
    conflict = uae() and len(active_quotes(frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet))) > 1
    from bsgroup.dcs.procurement import SEND_ROLES
    can_win = frappe.session.user == "Administrator" or bool(set(frappe.get_roles()) & SEND_ROLES)
    complete = not any(d._get_missing_mandatory_fields() for d in [q] + q.get_all_children())
    from bsgroup import oman_item_description as descriptions
    client_descriptions = descriptions.managed(q)
    missing_descriptions = descriptions.missing_rows(q)
    complete = complete and not missing_descriptions
    pdf_issues = []
    if any(d._get_missing_mandatory_fields() for d in [q] + q.get_all_children()):
        pdf_issues.append("Complete the required quotation fields before preparing the PDF.")
    if missing_descriptions:
        pdf_issues.append("Choose Item Description (Costing), or enter CO wording only if you choose CO Item Description, for line(s): "
            + ", ".join(map(str, missing_descriptions)) + ". CO Description is optional.")
    if not discount_basis_ready(q):
        pdf_issues.append("Save the quotation so the discount is applied before VAT.")
    return dict(enabled=True, revision=cint(q.get("custom_oman_revision_no")),
        editable=q.docstatus == 0 and q.custom_pipeline_stage not in TERMINAL and not conflict,
        conflict=conflict,
        can_write=frappe.has_permission("Quotation", "write", doc=q),
        can_print=frappe.has_permission("Quotation", "print", doc=q),
        ready_to_convert=complete and discount_basis_ready(q) and not conflict,
        discount_before_vat=True,
        show_standard_terms=uae(),
        save_feedback=True, pdf_issues=pdf_issues,
        choose_pdf_template=template_selection_enabled(),
        client_descriptions=client_descriptions,
        can_install_descriptions=setup_authorised() and (not descriptions.enabled()
            or not frappe.db.exists("Custom Field", "Quotation Item-" + descriptions.COSTING)),
        can_win=can_win, statuses=[s for s in ("Sent", "Delayed", "Cancelled", "Lost", "Won") if s != "Won" or can_win])


def can_install():
    return setup_authorised() and not enabled()


@frappe.whitelist()
def dcs_context(dcs):
    sheet = frappe.get_doc("Deal Cost Sheet", dcs)
    sheet.check_permission("read")
    active = enabled()
    conflict = bool(active and uae() and len(active_quotes(sheet)) > 1)
    name = linked_quotation(sheet) if active else sheet.custom_quotation
    q = frappe.get_doc("Quotation", name) if active and name else None
    managed = bool(q and pilot(q))
    return dict(enabled=active, can_install=can_install(), quotation=name, conflict=conflict,
        workflow_label="UAE Quotation Workflow" if uae() else "Oman Quotation Pilot",
        auto_sync=managed, terminal=bool(managed and q.custom_pipeline_stage in TERMINAL))


@frappe.whitelist()
def won_context(quotation):
    q = _quotation(quotation, write=True)
    check_editable(q)
    from bsgroup.dcs.procurement import SEND_ROLES, source_items, handover_warehouses, send_to_procurement
    if frappe.session.user != "Administrator" and not set(frappe.get_roles()) & SEND_ROLES:
        frappe.throw("Sales or commercial-manager access to this deal is required to record Won and send to Procurement.", frappe.PermissionError)
    sheet = frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet)
    sheet.check_permission("write")
    result = dict(required_by=today(), warehouses=handover_warehouses(sheet.company),
        stock_items=any(r["is_stock_item"] for r in source_items(sheet)))
    # The Oman bench predates UAE's optional Project handover extension.
    # Honour that extension when present, without silently installing it in Oman.
    result["project_required"] = "project_modules" in inspect.signature(send_to_procurement).parameters
    if result["project_required"]:
        from bsgroup.project_handover import context as project_context, sales_handover
        with sales_handover(q, sheet):
            result.update(project_context(q, sheet))
    return result


@frappe.whitelist(methods=["POST"])
def change_status(quotation, stage, expected_modified, reason=None, schedule_date=None,
                  warehouse=None, project_modules=None, project_details=None,
                  customer_po=None, customer_po_reference=None):
    from bsgroup.dcs.presales_lineage import atomic_lifecycle
    return atomic_lifecycle(lambda: _change_status(quotation, stage, expected_modified,
        reason, schedule_date, warehouse, project_modules, project_details, customer_po, customer_po_reference))


def _change_status(quotation, stage, expected_modified, reason=None, schedule_date=None,
                   warehouse=None, project_modules=None, project_details=None,
                   customer_po=None, customer_po_reference=None):
    q = _quotation(quotation, write=True, lock=True)
    # Successful duplicate Won requests reuse the existing requisition. Never
    # re-award, regenerate evidence or create another purchasing request.
    if stage == "Won" and q.custom_pipeline_stage == "Won" and q.get("custom_bsp_material_request"):
        return dict(quotation=q.name, requisition=q.custom_bsp_material_request, already_sent=True)
    check_editable(q)
    if str(q.modified) != str(expected_modified):
        frappe.throw("The quotation changed. Reload it before changing status.")
    if stage not in {"Sent", "Delayed", "Cancelled", "Lost", "Won"}:
        frappe.throw("Choose a valid quotation status.")
    if stage == "Won":
        won_context(q.name)  # Keep the same role and source restrictions.
    q.custom_oman_flow = 1
    with operation(q, "status"):
        if stage == "Won":
            q.custom_customer_po = customer_po or q.custom_customer_po
            q.custom_customer_po_reference = customer_po_reference or q.custom_customer_po_reference
        if stage in TERMINAL:
            q.check_permission("submit")
            q.submit()  # Includes DCS approval, mandatory fields and stale-position checks.
            if uae():
                # Native valuation can exceed the database's decimal precision.
                # Start the status-only save from what submit actually persisted.
                q.reload()
        q.custom_pipeline_stage = stage
        q.custom_lost_reason = reason
        q.save()
    result = dict(quotation=q.name, status=stage)
    if stage == "Won":
        from bsgroup.dcs.procurement import send_to_procurement
        args = dict(quotation=q.name, schedule_date=schedule_date, warehouse=warehouse)
        if "project_modules" in inspect.signature(send_to_procurement).parameters:
            args.update(project_modules=project_modules, project_details=project_details)
        sent = send_to_procurement(**args)
        result["requisition"] = sent["name"]
        result["project"] = sent.get("project")
    snapshot(q, "Status changed to " + stage)
    return result


@frappe.whitelist(methods=["POST"])
def convert_pdf(quotation, expected_modified, template=None):
    q = _quotation(quotation, lock=True)
    q.check_permission("print")
    if str(q.modified) != str(expected_modified):
        frappe.throw("The quotation changed. Save and reload before converting to PDF.")
    require_net_discount(q)
    if q.docstatus == 0:
        q._validate_mandatory()
    from bsgroup.dcs.quotation_control import validate_position
    validate_position(frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet), q)
    if template_selection_enabled():
        validate_pdf_template(template)
    elif template:
        frappe.throw("Quotation template selection is not enabled on this site.")
    pdf = render_pdf(q, template=template)
    name = f"{q.name}-R{cint(q.get('custom_oman_revision_no'))}-{now_datetime().strftime('%Y%m%d%H%M%S%f')}.pdf"
    file = frappe.get_doc(dict(doctype="File", file_name=name, content=pdf, is_private=1,
        attached_to_doctype="Quotation", attached_to_name=q.name)).insert(ignore_permissions=True)
    if template_selection_enabled():
        # This is PDF output metadata, not a change to the commercial position.
        # Preserve the saved revision/timestamp and reuse it for procurement's PDF.
        frappe.db.set_value("Quotation", q.name, PDF_TEMPLATE_FIELD, template, update_modified=False)
        q.set(PDF_TEMPLATE_FIELD, template)
    snapshot(q, "PDF issued: " + file.name + ("; template: " + template if template else ""))
    return dict(file_url=file.file_url, revision=cint(q.get("custom_oman_revision_no")), template=template)


def render_pdf(q, no_letterhead=None, template=None):
    """Render the selected format without changing stored costing descriptions."""
    from bsgroup.oman_item_description import require_client_wording, managed, PARENT, FIELD, COSTING, visible_text
    require_client_wording(q)
    if managed(q):
        q.set(PARENT, 1)
    target_format = print_formats()[1]
    if template_selection_enabled():
        target_format = validate_pdf_template(template or q.get(PDF_TEMPLATE_FIELD) or target_format)
        if managed(q):
            q = deepcopy(q)
            for row in q.items:
                wording = row.description if cint(row.get(COSTING)) else row.get(FIELD)
                row.description = wording
                if not cint(row.get(COSTING)):
                    # Older formats use item_name/item_code directly. Only this
                    # print copy is changed, so CO never exposes the costing code.
                    row.item_name = visible_text(wording)
                    row.item_code = ""
    elif not frappe.db.exists("Print Format", target_format):
        frappe.throw("The quotation workflow print format is not installed. Complete workflow setup.")
    letterhead = q.get("letter_head") or frappe.db.get_value("Letter Head", {"is_default": 1, "disabled": 0}, "name")
    return frappe.get_print("Quotation", q.name, target_format, as_pdf=True, doc=q,
        letterhead=letterhead, no_letterhead=(not bool(letterhead)) if no_letterhead is None else no_letterhead)


def install_print_format():
    # Clone the live approved format; retain all readiness checks, branding,
    # margins and generator settings. Historical offers keep the original.
    source_format, target_format = print_formats()
    if frappe.db.exists("Print Format", target_format):
        return
    source = frappe.get_doc("Print Format", source_format)
    if source.doc_type != "Quotation" or source.disabled:
        frappe.throw("The approved Enterprise quotation format must be enabled before pilot setup.")
    old_revision = '{%- set rev = doc.name.split("-")|last if doc.amended_from else "0" -%}'
    old_row = '+ ([("Revision", rev)] if doc.amended_from else [])'
    if (source.html or "").count(old_revision) != 1 or source.html.count(old_row) != 1:
        frappe.throw("The Enterprise template revision layout changed. Review it before enabling the pilot.")
    target = frappe.copy_doc(source)
    target.name = target_format
    target.standard = "No"
    target.custom_format = 1
    target.html = source.html.replace(old_revision,
        '{%- set rev = (doc.get("custom_oman_revision_no") or 0) if doc.get("custom_oman_flow") or doc.docstatus == 0 else (doc.name.split("-")|last if doc.amended_from else "0") -%}')
    target.html = target.html.replace(old_row,
        '+ ([("Revision", rev)] if doc.get("custom_oman_flow") or doc.docstatus == 0 or doc.amended_from else [])')
    target.insert(ignore_permissions=True)


def install_pdf_action():
    # Preserve the site's readiness diagnostics; replace only its old PDF button
    # for pilot forms, whose Save/Convert action archives the actual revision.
    if uae():
        return
    name = "Quotation Readiness - Class A OM"
    if not frappe.db.exists("Client Script", name):
        return
    script = frappe.get_doc("Client Script", name)
    if "frm.__oman_quotation_pilot" in script.script:
        return
    old = "if (frm.is_new()) return;\n\t\tfrm.add_custom_button(__('Download Enterprise PDF')"
    if script.script.count(old) != 1:
        frappe.throw("The Oman PDF button script changed. Review it before enabling the pilot.")
    script.script = script.script.replace(old,
        "if (frm.is_new() || frm.__oman_quotation_pilot) return;\n\t\tfrm.add_custom_button(__('Download Enterprise PDF')")
    script.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def install():
    if not setup_authorised():
        frappe.throw("Workflow setup requires the site's authorised administrator.", frappe.PermissionError)
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Quotation": [
        dict(fieldname="custom_oman_flow", label="Managed quotation workflow", fieldtype="Check", read_only=1, hidden=1),
        dict(fieldname="custom_oman_revision_no", label="Quotation Revision", fieldtype="Int", default="0", read_only=1),
    ]})
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    options = frappe.get_meta("Quotation").get_field("custom_pipeline_stage").options.splitlines()
    if "Delayed" not in options:
        make_property_setter("Quotation", "custom_pipeline_stage", "options", "\n".join(options + ["Delayed"]), "Text")
    install_print_format()
    install_pdf_action()
    frappe.defaults.set_global_default(UAE_FLAG if uae() else FLAG, 1)
    if uae():
        from bsgroup.oman_item_description import install as install_descriptions
        install_descriptions()
    frappe.clear_cache()
    return dict(enabled=True, site=frappe.local.site, roles_changed=False, historical_submitted_quotes_changed=False)
