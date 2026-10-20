"""Add BS controls to standard ERPNext documents. Safe to rerun."""
import frappe
import hashlib
from pathlib import Path
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    def field(name, label, kind="Data", **kw):
        return dict(fieldname="custom_bsp_" + name, label=label,
                    fieldtype=kind, insert_after="amended_from", **kw)

    common = [
        field("managed", "BS Procurement", "Check", read_only=1, default="0", print_hide=1),
        field("key", "BS creation key", hidden=1, read_only=1, unique=1, print_hide=1),
        field("history", "BS approval history", "Long Text", hidden=1,
              read_only=1, allow_on_submit=1, print_hide=1),
        field("reason", "BS decision reason", "Small Text", read_only=1,
              allow_on_submit=1, print_hide=1),
        field("preparers", "BS preparation participants", "Long Text", read_only=1,
              hidden=1, allow_on_submit=1, print_hide=1, no_copy=1),
    ]
    create_custom_fields({
        "Material Request": common + [
            field("customer", "Sales Customer", "Link", options="Customer"),
            field("quotation", "Sales Quotation", "Link", options="Quotation"),
            field("customer_po", "Customer PO reference"),
            field("customer_po_file", "Customer PO attachment", "Attach"),
            field("source_snapshot", "Sales handover evidence", "Long Text",
                  read_only=1, hidden=1, print_hide=1),
            field("request_evidence", "PR quotations and invoice copies", "Long Text",
                  read_only=1, hidden=1, print_hide=1, no_copy=1),
        ],
        "Material Request Item": [
            dict(fieldname="custom_bsp_dcs_item", label="Source DCS item",
                 fieldtype="Data", insert_after="item_code", read_only=1, hidden=1, print_hide=1),
        ],
        "Quotation": [
            dict(fieldname="custom_bsp_material_request", label="Purchase Requisition",
                 fieldtype="Link", options="Material Request", insert_after="custom_customer_po",
                 read_only=1, allow_on_submit=1, no_copy=1),
        ],
        "Payment Entry": [
            dict(fieldname="custom_bsp_settlement_sources", label="BS settlement source history",
                 fieldtype="Long Text", insert_after="amended_from", hidden=1,
                 read_only=1, allow_on_submit=1, print_hide=1, no_copy=1),
        ],
        "Purchase Invoice": [
            field("managed", "BS Procurement", "Check", read_only=1, default="0", print_hide=1),
            field("approved_by", "Payment Order approved by", "Link", options="User",
                  read_only=1, no_copy=1, print_hide=1),
            field("approved_on", "Payment Order approved on", "Datetime",
                  read_only=1, no_copy=1, print_hide=1),
            field("preparers", "BS preparation participants", "Long Text", read_only=1,
                  hidden=1, allow_on_submit=1, print_hide=1, no_copy=1),
        ],
        "Purchase Order": common + [
            field("material_request", "BS Purchase Requisition", "Link",
                  options="Material Request", read_only=1),
            field("approval_state", "BS approval status", "Select", read_only=1,
                  options="\nDraft\nPending Approval\nRejected\nApproved\nCancelled",
                  allow_on_submit=1),
            field("comparison", "BS quotation comparison", "Long Text",
                  hidden=1, read_only=1, print_hide=1),
            field("group", "Purchase material group", "Select",
                  options="\nHardware\nSoftware\nProfessional Services"),
        ],
    }, update=True)
    frappe.clear_cache(doctype="Material Request")
    frappe.clear_cache(doctype="Purchase Order")
    # Existing invoice views may predate the managed flag. Recover their real
    # BS PO lineage without inventing or backdating approval evidence.
    frappe.db.sql("""update `tabPurchase Invoice` p
        join `tabPurchase Invoice Item` i on i.parent=p.name
        join `tabPurchase Order` po on po.name=i.purchase_order
        set p.custom_bsp_managed=1 where po.custom_bsp_managed=1
          and coalesce(p.custom_bsp_managed,0)=0""")
    frappe.clear_cache(doctype="Purchase Invoice")
    install_approver_role()
    scope_request_transitions()
    scope_request_transitions("Purchase Invoice")
    route_pending_request_actions()
    route_pending_request_actions("Purchase Invoice")
    lock_supplier_exceptions()
    name = "BS Procurement Purchase Order"
    template = Path(frappe.get_app_path("bsgroup", "templates", "bs_procurement_purchase_order.html")).read_text()
    fmt = frappe.get_doc("Print Format", name) if frappe.db.exists("Print Format", name) else frappe.new_doc("Print Format")
    digest = lambda value: hashlib.sha256((value or "").replace("\r\n", "\n").encode()).hexdigest()
    previous = frappe.defaults.get_global_default("bs_procurement_print_format_hash")
    shipped_v1 = {
        "c0663f636cf9a266b969b591526a2c727aa879faf53b508cb24fcdfd5e9d5747",
        # The installed v1 has Frappe's trailing whitespace normalization.
        "777d80997d71f7f709e21a6f096794a18f20d4b876c5abc165a5f7fd4b3f7eea",
    }
    if fmt.is_new() or digest(fmt.html) in shipped_v1 | {previous, digest(template)}:
        fmt.update(dict(name=name, doc_type="Purchase Order", module="BS Group", standard="No",
                        custom_format=1, print_format_type="Jinja", html=template,
                        disabled=0, print_format_builder=0))
        fmt.save()
        frappe.defaults.set_global_default("bs_procurement_print_format_hash", digest(fmt.reload().html))
    else:
        frappe.logger("bsgroup").warning("Preserved customised BS Procurement Purchase Order print format")
    enforce_policy()
    install_payment_source_index()


def enforce_policy():
    """The required app policy is reproducible on every deployment."""
    settings = {
        "Buying Settings": dict(po_required="Yes", pr_required="Yes", maintain_same_rate=1,
                                maintain_same_rate_action="Stop", role_to_override_stop_action=None),
        "Accounts Settings": dict(over_billing_allowance=0, role_allowed_to_over_bill=None),
        "Stock Settings": dict(over_delivery_receipt_allowance=0, role_allowed_to_over_deliver_receive=None),
        "BS Group Settings": dict(cost_overrun_policy="Block"),
    }
    for doctype, values in settings.items():
        doc = frappe.get_single(doctype)
        if any(doc.get(k) != v for k, v in values.items()):
            doc.update(values)
            doc.save()


def scope_request_transitions(doctype="Material Request"):
    """Scope BS sending and Mohan's decisions; preserve ordinary MR rules."""
    from bsgroup.procurement_controls import APPROVER_ROLE
    name = frappe.db.get_value("Workflow", {"document_type": doctype, "is_active": 1})
    if not name:
        return
    workflow = frappe.get_doc("Workflow", name)
    changed = False
    for row in list(workflow.transitions):
        send = row.action == "Send for Approval" and row.next_state == "Pending Approval"
        decision = row.action in ("Approve", "Reject") and row.state == "Pending Approval"
        if not (send or decision):
            continue
        if "custom_bsp_managed" in (row.condition or ""):
            continue
        original = row.condition
        copy = {k: row.get(k) for k in ("state", "action", "next_state", "allowed", "transition_tasks")}
        copy.update(allow_self_approval=1,
                    condition=f"({original}) and doc.custom_bsp_managed" if original else "doc.custom_bsp_managed")
        if decision:
            copy["allowed"] = APPROVER_ROLE
        workflow.append("transitions", copy)
        row.condition = f"({original}) and not doc.custom_bsp_managed" if original else "not doc.custom_bsp_managed"
        changed = True
    if changed:
        workflow.save()


def install_approver_role():
    """Assign the dedicated routing role without changing account activation."""
    from bsgroup.procurement_controls import APPROVER_ROLE, PROCUREMENT_APPROVER
    if not frappe.db.exists("Role", APPROVER_ROLE):
        frappe.get_doc(dict(doctype="Role", role_name=APPROVER_ROLE, desk_access=1)).insert()
    if frappe.db.exists("User", PROCUREMENT_APPROVER):
        user = frappe.get_doc("User", PROCUREMENT_APPROVER)
        if APPROVER_ROLE not in {r.role for r in user.roles}:
            user.append("roles", dict(role=APPROVER_ROLE))
            user.send_welcome_email = 0
            user.save()


def route_pending_request_actions(doctype="Material Request"):
    """Reroute already-open BS PR reviews; preserve completed approval history."""
    from bsgroup.procurement_controls import APPROVER_ROLE
    if doctype not in ("Material Request", "Purchase Invoice"):
        return
    names = frappe.db.sql(f"""
        select a.name from `tabWorkflow Action` a
        join `tab{doctype}` r on r.name=a.reference_name
        where a.reference_doctype=%s and a.status='Open'
          and a.workflow_state='Pending Approval'
          and r.custom_bsp_managed=1 and r.workflow_state='Pending Approval' and r.docstatus=0
    """, (doctype,), pluck=True)
    for name in names:
        action = frappe.get_doc("Workflow Action", name)
        if {r.role for r in action.permitted_roles} != {APPROVER_ROLE}:
            action.set("permitted_roles", [dict(role=APPROVER_ROLE)])
            action.save(ignore_permissions=True)


def lock_supplier_exceptions():
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter
    from bsgroup.procurement_payments import SUPPLIER_EXCEPTIONS
    for field in SUPPLIER_EXCEPTIONS:
        frappe.db.sql(f"update `tabSupplier` set `{field}`=0 where coalesce(`{field}`,0)!=0")
        make_property_setter("Supplier", field, "read_only", 1, "Check")
        make_property_setter("Supplier", field, "default", "0", "Data")
    frappe.clear_cache(doctype="Supplier")


def install_payment_source_index():
    """Indexed audit associations, maintained by server hooks; never client writable."""
    if not frappe.db.exists("DocType", "BS Payment Source"):
        frappe.get_doc(dict(doctype="DocType", name="BS Payment Source", module="BS Group",
            custom=1, autoname="hash", track_changes=0,
            fields=[
                dict(fieldname="payment_entry", label="Payment Entry", fieldtype="Data", reqd=1, search_index=1),
                dict(fieldname="purchase_invoice", label="Purchase Invoice", fieldtype="Data", reqd=1, search_index=1),
                dict(fieldname="company", label="Company", fieldtype="Link", options="Company", reqd=1),
            ], permissions=[dict(role="System Manager", read=1)])).insert(ignore_permissions=True)
    frappe.db.add_unique("BS Payment Source", ["payment_entry", "purchase_invoice"], "unique_payment_invoice")
    # Backfill only real saved server history and current Payment Entry references.
    from bsgroup.procurement_accounts import sync_payment_index
    names = frappe.db.sql("""select distinct name from `tabPayment Entry`
        where custom_bsp_settlement_sources is not null and custom_bsp_settlement_sources != ''""", pluck=True)
    for name in names:
        sync_payment_index(frappe.get_doc("Payment Entry", name))
