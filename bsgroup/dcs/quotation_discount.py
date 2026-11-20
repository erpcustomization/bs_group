"""Net selling reconciliation, without changing any purchase-cost inputs."""
import math
import frappe
from frappe.utils import flt
from bsgroup.dcs.currency import money_round, money_tolerance


def preserve_rate_precision(quotation):
    """Unit rates may carry fractions of a cent; line totals remain currency rounded.

    Applied only to managed DCS quotations, without changing global metadata or
    purchasing precision. This retains agreed line amounts for large quantities.
    """
    rate_fields = {'rate', 'price_list_rate', 'net_rate', 'base_rate', 'base_net_rate', 'base_price_list_rate'}
    if not quotation.get('items'):
        return
    parent_precision = quotation.precision
    quotation.precision = lambda fieldname, parentfield=None: (
        max(9, parent_precision(fieldname, parentfield) or 0)
        if parentfield == 'items' and fieldname in rate_fields
        else parent_precision(fieldname, parentfield))
    for row in quotation.get('items') or []:
        original = row.precision
        row.precision = lambda fieldname, parentfield=None, original=original: (
            max(9, original(fieldname, parentfield) or 0) if fieldname in rate_fields
            else original(fieldname, parentfield))


def gross_selling(sheet):
    return money_round(sum(money_round(flt(r.qty) * flt(r.selling_rate), sheet.currency) for r in sheet.items)
        + sum(flt(r.get('selling_amount')) for r in sheet.get('addtional_charges') or []), sheet.currency)


def net_selling(gross, quotation, currency):
    percent = flt(quotation.get('additional_discount_percentage'))
    amount = flt(quotation.get('discount_amount'))
    if not all(math.isfinite(v) for v in (gross, percent, amount)) or percent < 0 or percent > 100 or amount < 0:
        frappe.throw('Quotation discount must be finite and non-negative, with percentage at most 100.')
    if (percent or amount) and quotation.get('apply_discount_on') != 'Net Total':
        frappe.throw('Save the quotation with discount applied on Net Total before revising costing.')
    discount = money_round(gross * percent / 100, currency) if percent else amount
    if discount > gross:
        frappe.throw('Quotation discount cannot exceed its selling total.')
    return money_round(gross - discount, currency)


def apply_to_calculated_sheet(sheet):
    """BOQ revisions retain the linked quote's amount or percentage discount."""
    from bsgroup.oman_quotation_flow import enabled
    if not enabled() or not sheet.get('custom_quotation'):
        return
    q = frappe.db.get_value('Quotation', sheet.custom_quotation,
        ['custom_deal_cost_sheet', 'docstatus', 'apply_discount_on', 'discount_amount', 'additional_discount_percentage'], as_dict=True)
    if q and q.custom_deal_cost_sheet == sheet.name and q.docstatus != 2:
        sheet.total_selling = net_selling(sheet.total_selling, q, sheet.currency)


def sync(quotation, sheet):
    """Called after native quotation calculation and BOQ validation, atomically."""
    from bsgroup.oman_quotation_flow import pilot, require_single_quote
    previous_doc = quotation.get_doc_before_save()
    if not pilot(quotation) or quotation.docstatus == 2 or (quotation.docstatus == 1 and (
        not previous_doc or previous_doc.docstatus != 0)):
        return
    expected = net_selling(gross_selling(sheet), quotation, sheet.currency)
    if abs(expected - flt(quotation.net_total)) > money_tolerance(sheet.currency):
        frappe.throw('The quotation net total does not match the DCS and discount. Review pricing before saving.')
    if abs(expected - flt(sheet.total_selling)) <= money_tolerance(sheet.currency) and abs(
        expected - flt(sheet.custom_working_total_selling if sheet.custom_dcs_revision_no else sheet.total_selling)) <= money_tolerance(sheet.currency):
        return
    if sheet.custom_award_state == 'Awarded' or sheet.custom_baseline_frozen:
        frappe.throw('An awarded costing sheet cannot be changed by a quotation discount.')
    require_single_quote(sheet)
    quotation.check_permission('write')
    sheet.check_permission('write')
    from bsgroup.api.dcs._common import CUSTOMER_SIDE
    if not set(frappe.get_roles()) & set(CUSTOMER_SIDE):
        frappe.throw('Only commercial users can change the quotation discount.', frappe.PermissionError)
    from bsgroup.dcs.baseline import ensure_baseline
    ensure_baseline(sheet.name, 'quotation_discount')
    sheet.reload()
    record_net_revision(sheet, expected, 'Quotation ' + quotation.name + ': discount reconciled to net selling value.')
    quotation.custom_dcs_revision_reference = sheet.custom_revision_reference


def record_net_revision(sheet, selling, reason):
    from bsgroup.api.dcs.negotiation import (pct, requirement, gate_for, state_for,
        rev_state_for, why_approval, why_gate, write_revision)
    from bsgroup.dcs.governance import record_governance_event
    cost, previous = flt(sheet.total_cost), flt(sheet.custom_working_total_selling)
    margin = pct(selling - cost, selling)
    concession = pct(flt(sheet.custom_baseline_selling) - selling, flt(sheet.custom_baseline_selling))
    req, gate = requirement(concession, margin), gate_for(margin)
    no = int(sheet.custom_dcs_revision_no or 0) + 1
    ref = write_revision(sheet.name, no, 'Customer', reason, cost, previous,
        pct(previous - cost, previous), flt(sheet.custom_concession_percent_from_baseline),
        cost, selling, margin, concession, 'Purchase costs unchanged.', req, rev_state_for(req), gate)
    if ref.startswith('COLLISION::'):
        frappe.throw('Could not record the discount revision. Refresh and retry.')
    values = dict(total_selling=selling, margin_value=selling-cost, margin_percent=margin,
        custom_working_total_selling=selling, custom_working_margin_percent=margin,
        custom_dcs_revision_no=no, custom_revision_reference=ref,
        custom_concession_percent_from_baseline=concession, custom_approval_state=state_for(req),
        custom_approval_required=req, custom_approval_reason=why_approval(concession, margin),
        custom_margin_gate=gate, custom_margin_gate_reason=why_gate(margin))
    before = {key: sheet.get(key) for key in values}
    # Frappe adds modified/modified_by to the supplied dict in place.
    # Keep the audited commercial change set separate from those timestamps.
    frappe.db.set_value('Deal Cost Sheet', sheet.name, dict(values))
    record_governance_event(sheet.name, 'DCS_QUOTATION_DISCOUNT_SYNC', action_label='Reconcile quotation net selling',
        source_endpoint='quotation_discount', reason=reason, revision_no=no, revision_reference=ref,
        changes=[dict(dt='Deal Cost Sheet',dn=sheet.name,field=k,old=before[k],new=v) for k,v in values.items()])
    sheet.reload()
