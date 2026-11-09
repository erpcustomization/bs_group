"""Opt-in Oman pilot. Draft quotations follow their DCS; terminal offers stay frozen.

Activation installs only the pilot's fields/options, never roles or purchasing rules.
All writes use existing document permissions and governed DCS/procurement services.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import inspect
import json

import frappe
from frappe.utils import cint, flt, now_datetime, today

OMAN_SITES = {"erp-om.k.frappe.cloud"}
FLAG = "bs_oman_quotation_flow"
SOURCE_PRINT_FORMAT = "Enterprise Quotation - Class A - OM"
PILOT_PRINT_FORMAT = "Enterprise Quotation - Oman Pilot"
TERMINAL = {"Won", "Lost"}
STAGES = {"Draft", "Sent", "Follow-up", "Delayed", "Cancelled", "Expired", "Won", "Lost"}
_operation = ContextVar("oman_quote_operation", default=None)


def enabled():
    return (getattr(frappe.local, "site", None) in OMAN_SITES
            and cint(frappe.defaults.get_global_default(FLAG)) == 1)


def pilot(q):
    previous = q.get_doc_before_save()
    return bool(enabled() and q.get("custom_deal_cost_sheet")
                and (q.docstatus == 0 or q.get("custom_oman_flow")
                     or (previous and previous.get("custom_oman_flow"))))


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
    q.add_comment("Info", f"Oman quotation R{cint(q.get('custom_oman_revision_no'))}: {label}")


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


def sync_draft(sheet):
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_deal_identity
    from bsgroup.dcs.currency import money_tolerance
    q = frappe.get_doc("Quotation", sheet.custom_quotation, for_update=True)
    q.check_permission("write")
    check_editable(q)
    if q.custom_deal_cost_sheet != sheet.name or quotation_deal_identity(sheet, q) or q.currency != sheet.currency:
        frappe.throw("The quotation identity or currency differs from this DCS. Revision was not saved.")
    snapshot(q, "Before DCS revision")
    rows = []
    for row in sheet.items:
        item = frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom"], as_dict=True)
        description = row.description or (row.item_name if row.exclude_item_name_and_brand else
            " - ".join(str(v) for v in (row.brand, row.item_code, row.item_name) if v)) or item.item_name
        rows.append(dict(item_code=row.item_code, item_name=row.item_name or item.item_name,
            brand=row.brand, uom=item.stock_uom, stock_uom=item.stock_uom, conversion_factor=1,
            description=description, custom_header=row.header,
            custom_exclude_item_name_and_brand=row.exclude_item_name_and_brand,
            qty=row.qty, custom_cost_rate=row.cost_rate, custom_selling_rate=row.selling_rate,
            price_list_rate=row.selling_rate, discount_percentage=0, rate=row.selling_rate))
    charges = sum(flt(r.get("selling_amount")) for r in sheet.addtional_charges or [])
    if charges:
        code = frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item")
        if not code:
            frappe.throw("Configure the existing DCS Additional Item before synchronising charges.")
        item = frappe.db.get_value("Item", code, ["item_name", "stock_uom"], as_dict=True)
        rows.append(dict(item_code=code, item_name=item.item_name, description=item.item_name,
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
    before = q.get_doc_before_save()
    if before and before.custom_pipeline_stage in TERMINAL:
        frappe.throw("Won and Lost pilot quotations are frozen; they cannot be edited or reopened.")
    if q.docstatus == 2:
        frappe.throw("Use the commercial Cancelled status; native cancellation is outside the editable pilot flow.")
    action = _operation.get()
    allowed = action and action[0] == q.name
    if before and before.docstatus == 0 and q.docstatus == 1 and (not allowed or action[1] != "status"):
        frappe.throw("Use Change Status → Won or Lost to finalise an Oman pilot quotation.")
    if before and before.docstatus == 1 and not before.get("custom_oman_flow"):
        frappe.throw("Historical submitted quotations cannot be enrolled in the draft pilot.")
    if before and before.get("custom_oman_flow") and not q.get("custom_oman_flow"):
        frappe.throw("The Oman quotation workflow flag cannot be cleared.")
    if not before and cint(q.get("custom_oman_revision_no")):
        frappe.throw("New quotations must start at revision R0.")
    if before and cint(q.get("custom_oman_revision_no")) != cint(before.get("custom_oman_revision_no")):
        if not allowed or action[1] != "revise":
            frappe.throw("Quotation revision numbers are managed by the DCS revision service.")
    if before and q.custom_pipeline_stage != before.custom_pipeline_stage and not allowed:
        frappe.throw("Use Change Status to preserve the Oman quotation and procurement controls.")
    q.custom_oman_flow = 1


def validate_stage(q):
    if not pilot(q):
        return False
    stage = q.custom_pipeline_stage or "Draft"
    if stage not in STAGES:
        frappe.throw("Invalid Oman quotation status.")
    before = q.get_doc_before_save()
    if before and before.custom_pipeline_stage in TERMINAL and before.custom_pipeline_stage != stage:
        frappe.throw("Won and Lost quotations cannot be reopened in the Oman pilot.")
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
        frappe.throw("The Oman pilot applies only to new/Draft quotations and quotations created through this pilot.")
    return q


@frappe.whitelist()
def context(quotation):
    q = frappe.get_doc("Quotation", quotation)
    q.check_permission("read")
    if not pilot(q):
        return {"enabled": False, "can_install": can_install()}
    from bsgroup.dcs.procurement import SEND_ROLES
    can_win = frappe.session.user == "Administrator" or bool(set(frappe.get_roles()) & SEND_ROLES)
    complete = not any(d._get_missing_mandatory_fields() for d in [q] + q.get_all_children())
    return dict(enabled=True, revision=cint(q.get("custom_oman_revision_no")),
        editable=q.docstatus == 0 and q.custom_pipeline_stage not in TERMINAL,
        can_write=frappe.has_permission("Quotation", "write", doc=q),
        can_print=frappe.has_permission("Quotation", "print", doc=q),
        ready_to_convert=complete,
        can_win=can_win, statuses=[s for s in ("Sent", "Delayed", "Cancelled", "Lost", "Won") if s != "Won" or can_win])


def can_install():
    return getattr(frappe.local, "site", None) in OMAN_SITES and frappe.session.user == "Administrator" and not enabled()


@frappe.whitelist()
def dcs_context(dcs):
    sheet = frappe.get_doc("Deal Cost Sheet", dcs)
    sheet.check_permission("read")
    active = enabled()
    name = linked_quotation(sheet) if active else sheet.custom_quotation
    q = frappe.get_doc("Quotation", name) if active and name else None
    managed = bool(q and pilot(q))
    return dict(enabled=active, can_install=can_install(), quotation=name,
        auto_sync=managed, terminal=bool(managed and q.custom_pipeline_stage in TERMINAL))


@frappe.whitelist()
def won_context(quotation):
    q = _quotation(quotation, write=True)
    check_editable(q)
    from bsgroup.dcs.procurement import SEND_ROLES, source_items, handover_warehouses, send_to_procurement
    if frappe.session.user != "Administrator" and not set(frappe.get_roles()) & SEND_ROLES:
        frappe.throw("Only the existing commercial-authority roles can record Won and send to Procurement.", frappe.PermissionError)
    sheet = frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet)
    sheet.check_permission("write")
    result = dict(required_by=today(), warehouses=handover_warehouses(sheet.company),
        stock_items=any(r["is_stock_item"] for r in source_items(sheet)))
    # The Oman bench predates UAE's optional Project handover extension.
    # Honour that extension when present, without silently installing it in Oman.
    result["project_required"] = "project_modules" in inspect.signature(send_to_procurement).parameters
    if result["project_required"]:
        from bsgroup.project_handover import context as project_context
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
    snapshot(q, "Status changed to " + stage)
    return result


@frappe.whitelist(methods=["POST"])
def convert_pdf(quotation, expected_modified):
    q = _quotation(quotation, lock=True)
    q.check_permission("print")
    if str(q.modified) != str(expected_modified):
        frappe.throw("The quotation changed. Save and reload before converting to PDF.")
    if q.docstatus == 0:
        q._validate_mandatory()
    from bsgroup.dcs.quotation_control import validate_position
    validate_position(frappe.get_doc("Deal Cost Sheet", q.custom_deal_cost_sheet), q)
    pdf = render_pdf(q)
    name = f"{q.name}-R{cint(q.get('custom_oman_revision_no'))}-{now_datetime().strftime('%Y%m%d%H%M%S%f')}.pdf"
    file = frappe.get_doc(dict(doctype="File", file_name=name, content=pdf, is_private=1,
        attached_to_doctype="Quotation", attached_to_name=q.name)).insert(ignore_permissions=True)
    snapshot(q, "PDF issued: " + file.name)
    return dict(file_url=file.file_url, revision=cint(q.get("custom_oman_revision_no")))


def render_pdf(q, no_letterhead=None):
    """Use Oman's approved customer format and its configured PDF generator."""
    if not frappe.db.exists("Print Format", PILOT_PRINT_FORMAT):
        frappe.throw("The Oman pilot print format is not installed. Ask Administrator to complete pilot setup.")
    letterhead = q.get("letter_head") or frappe.db.get_value("Letter Head", {"is_default": 1, "disabled": 0}, "name")
    return frappe.get_print("Quotation", q.name, PILOT_PRINT_FORMAT, as_pdf=True,
        letterhead=letterhead, no_letterhead=(not bool(letterhead)) if no_letterhead is None else no_letterhead)


def install_print_format():
    # Clone the live approved format; retain all readiness checks, branding,
    # margins and generator settings. Historical offers keep the original.
    if frappe.db.exists("Print Format", PILOT_PRINT_FORMAT):
        return
    source = frappe.get_doc("Print Format", SOURCE_PRINT_FORMAT)
    if source.doc_type != "Quotation" or source.disabled:
        frappe.throw("The approved Oman Enterprise quotation format must be enabled before pilot setup.")
    old_revision = '{%- set rev = doc.name.split("-")|last if doc.amended_from else "0" -%}'
    old_row = '+ ([("Revision", rev)] if doc.amended_from else [])'
    if (source.html or "").count(old_revision) != 1 or source.html.count(old_row) != 1:
        frappe.throw("The Oman Enterprise template revision layout changed. Review it before enabling the pilot.")
    target = frappe.copy_doc(source)
    target.name = PILOT_PRINT_FORMAT
    target.standard = "No"
    target.html = source.html.replace(old_revision,
        '{%- set rev = (doc.get("custom_oman_revision_no") or 0) if doc.get("custom_oman_flow") or doc.docstatus == 0 else (doc.name.split("-")|last if doc.amended_from else "0") -%}')
    target.html = target.html.replace(old_row,
        '+ ([("Revision", rev)] if doc.get("custom_oman_flow") or doc.docstatus == 0 or doc.amended_from else [])')
    target.insert(ignore_permissions=True)


def install_pdf_action():
    # Preserve the site's readiness diagnostics; replace only its old PDF button
    # for pilot forms, whose Save/Convert action archives the actual revision.
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
    if getattr(frappe.local, "site", None) not in OMAN_SITES or frappe.session.user != "Administrator":
        frappe.throw("Only Administrator on the Oman site can enable this pilot.", frappe.PermissionError)
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({"Quotation": [
        dict(fieldname="custom_oman_flow", label="Oman quotation pilot", fieldtype="Check", read_only=1, hidden=1),
        dict(fieldname="custom_oman_revision_no", label="Quotation Revision", fieldtype="Int", default="0", read_only=1),
    ]})
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    options = frappe.get_meta("Quotation").get_field("custom_pipeline_stage").options.splitlines()
    if "Delayed" not in options:
        make_property_setter("Quotation", "custom_pipeline_stage", "options", "\n".join(options + ["Delayed"]), "Text")
    install_print_format()
    install_pdf_action()
    frappe.defaults.set_global_default(FLAG, 1)
    frappe.clear_cache()
    return dict(enabled=True, site=frappe.local.site, roles_changed=False, historical_submitted_quotes_changed=False)
