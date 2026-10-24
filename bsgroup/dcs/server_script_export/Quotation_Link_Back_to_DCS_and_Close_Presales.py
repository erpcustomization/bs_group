# Quotation - Link Back to DCS and Close Presales
# Business transitions are unchanged: quotation/DCS/presales cross-links, the Quoted deal
# status, and the existing Presales Request status ladder. This hook holds no projection
# mapping of its own; the Deal Cost Sheet presales projection is refreshed through the
# canonical dcs_presales_sync endpoint, which is the documented fix for six historical
# projection mismatches.
# The synchronisation is a full fan-out over the Presales Request rather than a single
# sheet, because the status ladder above is a Presales Request level transition and every
# active linked sheet is affected by it. Cancelled siblings are skipped by the endpoint,
# unchanged siblings raise no event, and the whole fan-out shares one correlation id.
# The script is intentionally a single function. Frappe safe_exec gives DocType Event
# scripts a separate locals mapping, so a top level function is not visible from inside
# another function here; splitting this logic across two defs raises NameError at runtime.
def run(doc=doc):
    dcs = doc.custom_deal_cost_sheet
    if not dcs and doc.opportunity:
        rows = frappe.get_all('Deal Cost Sheet',
            filters={'opportunity': doc.opportunity, 'docstatus': 1},
            fields=['name'], order_by='creation desc', limit=1)
        if rows:
            dcs = rows[0].get('name')
            frappe.db.set_value('Quotation', doc.name, 'custom_deal_cost_sheet', dcs, update_modified=False)
    if not dcs:
        return
    frappe.db.set_value('Deal Cost Sheet', dcs, 'custom_quotation', doc.name, update_modified=False)
    cur = frappe.db.get_value('Deal Cost Sheet', dcs, 'custom_deal_status')
    if cur not in ['Won', 'Lost', 'Dropped / No Bid']:
        frappe.db.set_value('Deal Cost Sheet', dcs, 'custom_deal_status', 'Quoted', update_modified=False)
    pr = frappe.db.get_value('Deal Cost Sheet', dcs, 'presales_request')
    if not pr:
        return
    frappe.db.set_value('Quotation', doc.name, 'custom_presales_request', pr, update_modified=False)
    frappe.db.set_value('Presales Request', pr, 'custom_quotation', doc.name, update_modified=False)
    frappe.db.set_value('Presales Request', pr, 'custom_deal_cost_sheet', dcs, update_modified=False)
    frappe.db.set_value('Presales Request', pr, 'custom_deal_status', 'Quoted', update_modified=False)
    prd = frappe.db.get_value('Presales Request', pr, ['status', 'actual_hours'], as_dict=True)
    st = prd.get('status')
    if st not in ['Completed', 'Won', 'Lost', 'Cancelled']:
        if not prd.get('actual_hours'):
            if st not in ['Submitted to Sales']:
                frappe.db.set_value('Presales Request', pr, 'status', 'Ready for Quotation', update_modified=False)
        else:
            frappe.db.set_value('Presales Request', pr, 'status', 'Completed', update_modified=False)
            if not frappe.db.get_value('Presales Request', pr, 'completion_date'):
                frappe.db.set_value('Presales Request', pr, 'completion_date', frappe.utils.nowdate(), update_modified=False)

    # Canonical projection synchronisation, fanned out across the whole Presales Request.
    # This script owns the business transition only; all Deal Cost Sheet projection mapping
    # and calculation belongs to dcs_presales_sync. The fan-out is deliberate: the Presales
    # Request status ladder above is a Presales Request level transition, so every active
    # linked sheet must be refreshed, not just the one this quotation happens to point at.
    keep = frappe.response.get("message")
    sync = None
    try:
        frappe.call("dcs_presales_sync", presales_request=pr, source="quotation")
        sync = frappe.response.get("message")
    finally:
        frappe.response["message"] = keep
    if not sync:
        frappe.throw("Canonical presales synchronisation returned no payload. No Deal Cost Sheet projection value was written.")
    if sync.get("error"):
        frappe.throw(sync.get("error"))

run()
